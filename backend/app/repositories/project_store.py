from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.workspace import (
    Workspace,
    file_fingerprint,
    fingerprints_match,
    load_stored_path,
    store_user_path,
)
from app.models.schemas import (
    AnnotationRecord,
    Dataset,
    ImageRecord,
    RunRecord,
    SavedView,
    ViewSpec,
)
from app.repositories.duckdb_repo import DuckDBRepository


class ProjectStore:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.data_root = workspace.data_root
        self.data_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connections: dict[str, DuckDBRepository] = {}
        self._catalog = self._read_catalog()

    def close(self) -> None:
        with self._lock:
            for repository in self._connections.values():
                repository.close()
            self._connections.clear()

    def embedding_dir(self, dataset_id: str) -> Path:
        path = self._dataset_dir(dataset_id) / "embeddings"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def create_dataset(
        self,
        name: str,
        source_uri: str,
        images: list[ImageRecord],
        annotations: list[AnnotationRecord],
        progress_callback=None,
        dataset_id: str | None = None
    ) -> Dataset:
        dataset_id = dataset_id or str(uuid4())
        stored_source = store_user_path(source_uri, self.workspace.project_root)
        stored_images = [
            image.model_copy(
                update={"file_path": store_user_path(image.file_path, self.workspace.project_root)}
            )
            for image in images
        ]
        dataset = self._open(dataset_id).create_dataset(
            name=name,
            source_uri=stored_source,
            images=stored_images,
            annotations=annotations,
            progress_callback=progress_callback,
            dataset_id=dataset_id
        )
        entry = self._entry_from_dataset(dataset, image_root="", fingerprint=None)
        with self._lock:
            self._catalog["datasets"] = [
                item for item in self._catalog["datasets"] if item["id"] != dataset.id
            ]
            self._catalog["datasets"].append(entry)
            self._write_catalog()
            self._write_meta(entry)
        return dataset

    def list_datasets(self) -> list[Dataset]:
        with self._lock:
            entries = sorted(
                self._catalog["datasets"],
                key=lambda item: str(item.get("created_at", "")),
                reverse=True
            )
        return [self._dataset_from_entry(entry) for entry in entries]

    def find_by_source(self, source: str, image_root: str | None) -> Dataset | None:
        current = file_fingerprint(source, image_root, self.workspace.project_root)
        if current is None:
            return None
        with self._lock:
            matches = [
                entry
                for entry in self._catalog["datasets"]
                if isinstance(entry.get("fingerprint"), dict)
                and fingerprints_match(entry["fingerprint"], current, self.workspace.project_root)
            ]
        if not matches:
            return None
        matches.sort(key=lambda entry: str(entry.get("created_at", "")), reverse=True)
        return self._dataset_from_entry(matches[0])

    def write_fingerprint(self, dataset_id: str, source: str, image_root: str | None) -> None:
        fingerprint = file_fingerprint(source, image_root, self.workspace.project_root)
        if fingerprint is None:
            return
        with self._lock:
            for entry in self._catalog["datasets"]:
                if entry["id"] != dataset_id:
                    continue
                entry["fingerprint"] = fingerprint
                entry["image_root"] = fingerprint["image_root"]
                self._write_catalog()
                self._write_meta(entry)
                return

    def get_dataset_bundle(self, dataset_id: str):
        bundle = self._open(dataset_id).get_dataset_bundle(dataset_id)
        images = [self._public_image(image) for image in bundle.images]
        return type(bundle)(dataset=bundle.dataset, images=images, annotations=bundle.annotations)

    def list_image_targets(self, dataset_id: str, spec: ViewSpec) -> list[tuple[int, str]]:
        self._require_dataset(dataset_id)
        rows = self._open(dataset_id).list_image_targets(dataset_id, spec)
        return [(image_id, self._public_path(path)) for image_id, path in rows]

    def image_file_paths(self, dataset_id: str) -> dict[int, str]:
        self._require_dataset(dataset_id)
        paths = self._open(dataset_id).image_file_paths(dataset_id)
        return {image_id: self._public_path(path) for image_id, path in paths.items()}

    def create_saved_view(self, *, dataset_id: str, name: str, description: str, spec: ViewSpec) -> SavedView:
        saved_view = self._open(dataset_id).create_saved_view(
            dataset_id=dataset_id,
            name=name,
            description=description,
            spec=spec
        )
        with self._lock:
            self._catalog["saved_views"][saved_view.id] = dataset_id
            self._write_catalog()
        return saved_view

    def list_saved_views(self, dataset_id: str) -> list[SavedView]:
        return self._open(dataset_id).list_saved_views(dataset_id)

    def get_saved_view(self, saved_view_id: str) -> SavedView:
        dataset_id = self._dataset_for_saved_view(saved_view_id)
        return self._open(dataset_id).get_saved_view(saved_view_id)

    def update_saved_view(
        self,
        saved_view_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        spec: ViewSpec | None = None
    ) -> SavedView:
        dataset_id = self._dataset_for_saved_view(saved_view_id)
        return self._open(dataset_id).update_saved_view(
            saved_view_id,
            name=name,
            description=description,
            spec=spec
        )

    def delete_saved_view(self, saved_view_id: str) -> None:
        dataset_id = self._dataset_for_saved_view(saved_view_id)
        self._open(dataset_id).delete_saved_view(saved_view_id)
        with self._lock:
            self._catalog["saved_views"].pop(saved_view_id, None)
            self._write_catalog()

    def create_run_record(self, *, dataset_id: str, run_type: str, config: dict, **kwargs) -> RunRecord:
        run = self._open(dataset_id).create_run_record(
            dataset_id=dataset_id,
            run_type=run_type,
            config=config,
            **kwargs
        )
        with self._lock:
            self._catalog["runs"][run.id] = dataset_id
            self._write_catalog()
        return run

    def get_run_record(self, run_id: str) -> RunRecord:
        dataset_id = self._dataset_for_run(run_id)
        return self._open(dataset_id).get_run_record(run_id)

    def update_run_record(self, run_id: str, **kwargs) -> RunRecord:
        dataset_id = self._dataset_for_run(run_id)
        return self._open(dataset_id).update_run_record(run_id, **kwargs)

    def list_runs(self, dataset_id: str, run_type: str | None = None) -> list[RunRecord]:
        return self._open(dataset_id).list_runs(dataset_id, run_type=run_type)

    def latest_run(self, dataset_id: str, run_type: str | None = None) -> RunRecord | None:
        return self._open(dataset_id).latest_run(dataset_id, run_type=run_type)

    def _open(self, dataset_id: str) -> DuckDBRepository:
        with self._lock:
            existing = self._connections.get(dataset_id)
            if existing is not None:
                return existing
            path = self._dataset_dir(dataset_id) / "catalog.duckdb"
            path.parent.mkdir(parents=True, exist_ok=True)
            repository = DuckDBRepository(str(path))
            self._connections[dataset_id] = repository
            return repository

    def _dataset_dir(self, dataset_id: str) -> Path:
        return self.data_root / "datasets" / dataset_id

    def _dataset_for_saved_view(self, saved_view_id: str) -> str:
        dataset_id = self._catalog["saved_views"].get(saved_view_id)
        if not isinstance(dataset_id, str):
            raise KeyError(f"Saved view not found: {saved_view_id}")
        return dataset_id

    def _dataset_for_run(self, run_id: str) -> str:
        dataset_id = self._catalog["runs"].get(run_id)
        if not isinstance(dataset_id, str):
            raise KeyError(f"Run not found: {run_id}")
        return dataset_id

    def _entry_from_dataset(
        self,
        dataset: Dataset,
        *,
        image_root: str,
        fingerprint: dict[str, object] | None
    ) -> dict[str, object]:
        return {
            "id": dataset.id,
            "name": dataset.name,
            "source_uri": dataset.source_uri,
            "created_at": dataset.created_at.isoformat(),
            "image_count": dataset.image_count,
            "annotation_count": dataset.annotation_count,
            "image_root": image_root,
            "fingerprint": fingerprint
        }

    def _dataset_from_entry(self, entry: dict[str, object]) -> Dataset:
        created_at = datetime.fromisoformat(str(entry["created_at"]))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return Dataset(
            id=str(entry["id"]),
            name=str(entry["name"]),
            source_uri=str(entry["source_uri"]),
            created_at=created_at,
            image_count=int(entry.get("image_count", 0)),
            annotation_count=int(entry.get("annotation_count", 0))
        )

    def _require_dataset(self, dataset_id: str) -> None:
        if not any(str(entry.get("id")) == dataset_id for entry in self._catalog["datasets"]):
            raise KeyError(f"Dataset not found: {dataset_id}")

    def _public_path(self, path: str) -> str:
        if "://" in path:
            return path
        return load_stored_path(path, self.workspace.project_root)

    def _public_image(self, image: ImageRecord) -> ImageRecord:
        return image.model_copy(update={"file_path": self._public_path(image.file_path)})

    def _read_catalog(self) -> dict[str, object]:
        path = self.data_root / "catalog.json"
        catalog: dict[str, object] = {"datasets": [], "saved_views": {}, "runs": {}}
        if not path.is_file():
            return catalog
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return catalog
        if not isinstance(payload, dict):
            return catalog
        datasets = payload.get("datasets")
        saved_views = payload.get("saved_views")
        runs = payload.get("runs")
        if isinstance(datasets, list):
            catalog["datasets"] = [item for item in datasets if isinstance(item, dict)]
        if isinstance(saved_views, dict):
            catalog["saved_views"] = {str(key): str(value) for key, value in saved_views.items()}
        if isinstance(runs, dict):
            catalog["runs"] = {str(key): str(value) for key, value in runs.items()}
        return catalog

    def _write_catalog(self) -> None:
        path = self.data_root / "catalog.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self._catalog, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _write_meta(self, entry: dict[str, object]) -> None:
        path = self._dataset_dir(str(entry["id"])) / "meta.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(entry, indent=2), encoding="utf-8")
        temporary.replace(path)
