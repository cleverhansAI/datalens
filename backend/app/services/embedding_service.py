from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from app.core.config import settings
from app.embeddings.adapters import EmbeddingAdapterRegistry
from app.models.schemas import EmbeddingRunRequest, RunRecord, ViewSpec
from app.repositories import repo
from app.services.view_service import view_service


class EmbeddingService:
    _flush_rows = 1024

    def __init__(self) -> None:
        self._registry = EmbeddingAdapterRegistry()

    def _output_dir(self, dataset_id: str, model_id: str, run_id: str) -> Path:
        embedding_dir = getattr(repo, "embedding_dir", None)
        if callable(embedding_dir):
            return Path(embedding_dir(dataset_id)) / model_id / run_id
        return Path(settings.embedding_dir) / dataset_id / model_id / run_id

    def run(
        self,
        request: EmbeddingRunRequest,
        progress_callback: Callable[[float, str], None] | None = None
    ) -> RunRecord:
        resolved_spec = view_service.resolve_spec(
            request.dataset_id,
            view_spec=request.view,
            saved_view_id=request.saved_view_id
        )
        model_id = request.model.model_id
        provider_name = request.model.provider
        provider = self._registry.resolve(provider_name)
        mode = request.model.mode
        config = {
            "provider": provider_name,
            "model_id": model_id,
            "mode": mode,
            "batch_size": request.model.batch_size
        }
        run_record = repo.create_run_record(
            dataset_id=request.dataset_id,
            saved_view_id=request.saved_view_id,
            run_type="embedding",
            status="running",
            config=config,
            view_spec=resolved_spec
        )
        targets = self._image_targets(request.dataset_id, resolved_spec)
        image_count = len(targets)
        out_dir = self._output_dir(request.dataset_id, model_id, run_record.id)
        os.makedirs(out_dir, exist_ok=True)
        parquet_path = out_dir / "vectors.parquet"
        writer: pq.ParquetWriter | None = None
        try:
            self._emit_progress(progress_callback, 0, image_count, "Loading embedding model")
            vector_dim = 0
            if image_count == 0:
                _write_empty_parquet(parquet_path)
            else:
                batch_size = self._batch_size(provider, request.model.batch_size)
                buffer = _VectorBuffer(self._flush_rows)
                schema: pa.Schema | None = None
                for start in range(0, image_count, batch_size):
                    chunk = targets[start:start + batch_size]
                    vectors = np.asarray(
                        provider.embed_images([path for _, path in chunk], model_id),
                        dtype=np.float32
                    )
                    if vectors.ndim == 1:
                        vectors = vectors.reshape(1, -1)
                    if len(vectors) != len(chunk):
                        raise RuntimeError(
                            f"Embedding batch returned {len(vectors)} vectors for {len(chunk)} images"
                        )
                    vector_dim = int(vectors.shape[1])
                    if schema is None:
                        schema = _vector_schema(vector_dim)
                        writer = pq.ParquetWriter(parquet_path, schema)
                    image_ids = np.asarray([image_id for image_id, _ in chunk], dtype=np.int64)
                    for ready_ids, ready_vectors in buffer.add(image_ids, vectors):
                        _write_vector_batch(
                            writer,
                            schema,
                            ready_ids,
                            ready_vectors,
                            model_id=model_id,
                            provider_name=provider_name,
                            run_id=run_record.id
                        )
                    index = start + len(chunk)
                    self._emit_progress(
                        progress_callback,
                        index,
                        image_count,
                        f"Embedded {index} of {image_count} images"
                    )
                leftover = buffer.finish()
                if leftover is not None and writer is not None and schema is not None:
                    _write_vector_batch(
                        writer,
                        schema,
                        leftover[0],
                        leftover[1],
                        model_id=model_id,
                        provider_name=provider_name,
                        run_id=run_record.id
                    )
                if writer is not None:
                    writer.close()
                    writer = None
            self._emit_progress(
                progress_callback,
                image_count,
                image_count,
                "Building similarity index"
            )
            index_path = self._write_faiss_index_from_parquet(parquet_path, out_dir)
            artifact_paths = {"parquet": str(parquet_path)}
            if index_path is not None:
                artifact_paths["faiss_index"] = index_path
            run_record = repo.update_run_record(
                run_record.id,
                status="done",
                config={
                    **config,
                    "dim": vector_dim,
                    "image_count": image_count
                },
                artifact_path=str(parquet_path),
                artifact_paths=artifact_paths,
                error_message=None
            )
            self._emit_progress(
                progress_callback,
                image_count,
                image_count,
                f"Embedding run complete for {image_count} images"
            )
            return run_record
        except Exception as exc:
            if writer is not None:
                writer.close()
            parquet_path.unlink(missing_ok=True)
            repo.update_run_record(run_record.id, status="failed", error_message=str(exc))
            raise

    def list_runs(self, dataset_id: str) -> list[RunRecord]:
        return repo.list_runs(dataset_id, run_type="embedding")

    def get_projection(self, run_id: str) -> dict[str, object]:
        run = self._get_embedding_run(run_id)
        entity_ids, vectors = _load_embedding_matrix(self._parquet_path_for_run(run))
        if len(entity_ids) == 0:
            return {"run_id": run_id, "cluster_count": 0, "points": []}

        projection = self._project_vectors(vectors)
        cluster_ids = self._cluster_points(projection)
        path_by_id = self._image_paths(run.dataset_id)
        points = []
        for index in range(len(entity_ids)):
            point: dict[str, object] = {
                "entity_id": int(entity_ids[index]),
                "x": float(projection[index, 0]),
                "y": float(projection[index, 1]),
                "cluster_id": int(cluster_ids[index])
            }
            file_path = path_by_id.get(int(entity_ids[index]))
            if file_path:
                point["file_path"] = file_path
            points.append(point)
        return {
            "run_id": run_id,
            "cluster_count": len(set(cluster_ids.tolist())),
            "points": points
        }

    def find_similar_pairs(self, run_id: str, threshold: float = 0.98, limit: int = 100) -> list[dict]:
        run = self._get_embedding_run(run_id)
        entity_ids, vectors = _load_embedding_matrix(self._parquet_path_for_run(run))
        if len(entity_ids) == 0:
            return []

        vectors = _l2_normalize(vectors)
        pairs: list[dict] = []
        index_path = self._index_path_for_run(run)
        if index_path:
            try:
                import faiss  # type: ignore

                index = faiss.read_index(index_path)
                scores, neighbors = index.search(np.ascontiguousarray(vectors), min(10, len(vectors)))
                for i in range(len(vectors)):
                    for j, score in zip(neighbors[i], scores[i], strict=False):
                        if i == j or j < 0:
                            continue
                        if float(score) >= threshold:
                            pair = tuple(sorted((int(entity_ids[i]), int(entity_ids[j]))))
                            pairs.append({"pair": pair, "score": float(score)})
                            if len(pairs) >= limit:
                                return pairs
                return self._dedupe_pairs(pairs)[:limit]
            except Exception:
                pass

        similarity = vectors @ vectors.T
        for i in range(similarity.shape[0]):
            for j in range(i + 1, similarity.shape[1]):
                score = float(similarity[i, j])
                if score >= threshold:
                    pairs.append(
                        {"pair": (int(entity_ids[i]), int(entity_ids[j])), "score": score}
                    )
                    if len(pairs) >= limit:
                        return pairs
        return pairs

    def latest_run_for_dataset(self, dataset_id: str) -> RunRecord | None:
        return repo.latest_run(dataset_id, run_type="embedding")

    def _emit_progress(
        self,
        callback: Callable[..., None] | None,
        completed: int,
        total: int,
        message: str
    ) -> None:
        if callback is None:
            return
        progress = 1.0 if total == 0 else completed / total
        try:
            callback(progress, message, completed, total)
        except TypeError:
            callback(progress, message)

    def _image_targets(self, dataset_id: str, spec: ViewSpec) -> list[tuple[int, str]]:
        list_targets = getattr(repo, "list_image_targets", None)
        if callable(list_targets):
            return list_targets(dataset_id, spec)
        view = view_service.resolve(dataset_id, spec)
        return [(image.id, image.file_path) for image in view.images]

    def _image_paths(self, dataset_id: str) -> dict[int, str]:
        image_paths = getattr(repo, "image_file_paths", None)
        if not callable(image_paths):
            return {}
        return image_paths(dataset_id)

    def _batch_size(self, provider: object, requested: int) -> int:
        resolver = getattr(provider, "embed_batch_size", None)
        if callable(resolver):
            return max(1, int(resolver(requested)))
        return max(1, requested)

    def _write_faiss_index_from_parquet(self, parquet_path: Path, out_dir: Path) -> str | None:
        if not parquet_path.is_file():
            return None
        try:
            import faiss  # type: ignore
        except Exception:
            return None
        try:
            index = None
            parquet_file = pq.ParquetFile(parquet_path)
            for batch in parquet_file.iter_batches(batch_size=self._flush_rows, columns=["vector"]):
                vectors = _l2_normalize(_vectors_from_arrow(batch.column("vector")))
                if vectors.size == 0:
                    continue
                if index is None:
                    index = faiss.IndexFlatIP(int(vectors.shape[1]))
                index.add(np.ascontiguousarray(vectors, dtype=np.float32))
            if index is None:
                return None
            index_path = out_dir / "faiss.index"
            faiss.write_index(index, str(index_path))
            return str(index_path)
        except Exception:
            return None

    def _dedupe_pairs(self, pairs: list[dict]) -> list[dict]:
        seen: set[tuple[int, int]] = set()
        out: list[dict] = []
        for item in pairs:
            pair = tuple(sorted(item["pair"]))
            if pair in seen:
                continue
            seen.add(pair)
            out.append({"pair": pair, "score": item["score"]})
        return out

    def _project_vectors(self, vectors: np.ndarray) -> np.ndarray:
        if len(vectors) == 0:
            return np.zeros((0, 2), dtype=np.float32)
        if len(vectors) == 1:
            return np.zeros((1, 2), dtype=np.float32)

        centered = vectors - vectors.mean(axis=0, keepdims=True)
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        components = centered @ vh[:2].T
        if components.shape[1] == 1:
            components = np.concatenate(
                [components, np.zeros((components.shape[0], 1), dtype=components.dtype)],
                axis=1
            )
        return components[:, :2].astype(np.float32)

    def _cluster_points(self, points: np.ndarray) -> np.ndarray:
        point_count = len(points)
        if point_count == 0:
            return np.zeros((0,), dtype=np.int32)
        if point_count < 6:
            return np.zeros((point_count,), dtype=np.int32)

        cluster_count = min(8, max(2, int(np.sqrt(point_count / 2))))
        sorted_indices = np.argsort(points[:, 0], kind="stable")
        seed_positions = np.linspace(0, point_count - 1, cluster_count, dtype=int)
        centroids = points[sorted_indices[seed_positions]].copy()
        labels = np.zeros((point_count,), dtype=np.int32)

        for _ in range(24):
            distances = ((points[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
            next_labels = distances.argmin(axis=1).astype(np.int32)
            if np.array_equal(next_labels, labels):
                break
            labels = next_labels
            for cluster_index in range(cluster_count):
                cluster_points = points[labels == cluster_index]
                if len(cluster_points) == 0:
                    centroids[cluster_index] = points[sorted_indices[cluster_index % point_count]]
                else:
                    centroids[cluster_index] = cluster_points.mean(axis=0)

        unique_labels, counts = np.unique(labels, return_counts=True)
        ordered_labels = unique_labels[np.argsort(-counts)]
        remapped = np.zeros_like(labels)
        for mapped_label, original_label in enumerate(ordered_labels):
            remapped[labels == original_label] = mapped_label
        return remapped.astype(np.int32)

    def _get_embedding_run(self, run_id: str) -> RunRecord:
        run = repo.get_run_record(run_id)
        if run.run_type != "embedding":
            raise KeyError(f"Run is not an embedding run: {run_id}")
        return run

    def _parquet_path_for_run(self, run: RunRecord) -> str:
        parquet_path = run.artifact_paths.get("parquet", run.artifact_path or "")
        if not parquet_path:
            raise KeyError(f"Embedding parquet artifact missing for run {run.id}")
        return parquet_path

    def _index_path_for_run(self, run: RunRecord) -> str | None:
        return run.artifact_paths.get("faiss_index")


class _VectorBuffer:
    def __init__(self, flush_rows: int) -> None:
        self.flush_rows = max(1, flush_rows)
        self.ids = np.empty((self.flush_rows,), dtype=np.int64)
        self.vectors: np.ndarray | None = None
        self.filled = 0

    def add(self, ids: np.ndarray, vectors: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
        ready: list[tuple[np.ndarray, np.ndarray]] = []
        offset = 0
        count = len(ids)
        while offset < count:
            if self.vectors is None:
                self.vectors = np.empty((self.flush_rows, int(vectors.shape[1])), dtype=np.float32)
            space = self.flush_rows - self.filled
            take = min(space, count - offset)
            end = self.filled + take
            self.ids[self.filled:end] = ids[offset:offset + take]
            self.vectors[self.filled:end] = vectors[offset:offset + take]
            self.filled = end
            offset += take
            if self.filled == self.flush_rows:
                ready.append(self._take())
        return ready

    def finish(self) -> tuple[np.ndarray, np.ndarray] | None:
        if self.filled == 0 or self.vectors is None:
            return None
        return self._take()

    def _take(self) -> tuple[np.ndarray, np.ndarray]:
        ids = self.ids[:self.filled].copy()
        vectors = self.vectors[:self.filled].copy()
        self.filled = 0
        return ids, vectors


def _vector_schema(dim: int) -> pa.Schema:
    return pa.schema(
        [
            ("entity_type", pa.string()),
            ("entity_id", pa.int64()),
            ("model_id", pa.string()),
            ("provider", pa.string()),
            ("run_id", pa.string()),
            ("vector", pa.list_(pa.float32(), dim))
        ]
    )


def _write_empty_parquet(path: Path) -> None:
    schema = pa.schema(
        [
            ("entity_type", pa.string()),
            ("entity_id", pa.int64()),
            ("model_id", pa.string()),
            ("provider", pa.string()),
            ("run_id", pa.string()),
            ("vector", pa.list_(pa.float32()))
        ]
    )
    pq.write_table(pa.Table.from_pylist([], schema=schema), path)


def _write_vector_batch(
    writer: pq.ParquetWriter,
    schema: pa.Schema,
    ids: np.ndarray,
    vectors: np.ndarray,
    *,
    model_id: str,
    provider_name: str,
    run_id: str
) -> None:
    count = len(ids)
    flat = pa.array(np.ascontiguousarray(vectors, dtype=np.float32).reshape(-1), type=pa.float32())
    vector_array = pa.FixedSizeListArray.from_arrays(flat, int(vectors.shape[1]))
    batch = pa.record_batch(
        [
            pa.array(["image"] * count, type=pa.string()),
            pa.array(ids, type=pa.int64()),
            pa.array([model_id] * count, type=pa.string()),
            pa.array([provider_name] * count, type=pa.string()),
            pa.array([run_id] * count, type=pa.string()),
            vector_array
        ],
        schema=schema
    )
    writer.write_batch(batch)


def _load_embedding_matrix(path: str) -> tuple[np.ndarray, np.ndarray]:
    parquet_file = pq.ParquetFile(path)
    if parquet_file.metadata is None or parquet_file.metadata.num_rows == 0:
        return np.zeros((0,), dtype=np.int64), np.zeros((0, 0), dtype=np.float32)
    ids: list[np.ndarray] = []
    vectors: list[np.ndarray] = []
    for batch in parquet_file.iter_batches(batch_size=1024, columns=["entity_id", "vector"]):
        ids.append(batch.column("entity_id").to_numpy(zero_copy_only=False).astype(np.int64, copy=False))
        vectors.append(_vectors_from_arrow(batch.column("vector")))
    return np.concatenate(ids), np.vstack(vectors)


def _vectors_from_arrow(column: pa.Array | pa.ChunkedArray) -> np.ndarray:
    values = column.combine_chunks() if isinstance(column, pa.ChunkedArray) else column
    if len(values) == 0:
        return np.zeros((0, 0), dtype=np.float32)
    if pa.types.is_fixed_size_list(values.type):
        width = values.type.list_size
        flat = values.values.to_numpy(zero_copy_only=False)
        return np.asarray(flat, dtype=np.float32).reshape(len(values), width)
    rows = values.to_pylist()
    return np.asarray(rows, dtype=np.float32)


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    if vectors.size == 0:
        return vectors.astype(np.float32, copy=False)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return (vectors / np.clip(norms, a_min=1e-8, a_max=None)).astype(np.float32)


embedding_service = EmbeddingService()
