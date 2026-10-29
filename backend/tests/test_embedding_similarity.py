from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq

from app.models.schemas import (
    AnnotationRecord,
    EmbeddingModelSpec,
    EmbeddingRunRequest,
    FilterClause,
    ImageRecord,
    ViewSpec,
)
from app.repositories import repo
from app.services.embedding_service import embedding_service


def test_embedding_similarity_pairs_exist() -> None:
    dataset = repo.create_dataset(
        name="emb-test",
        source_uri="emb.json",
        images=[
            ImageRecord(id=1001, file_path="/tmp/a.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0),
            ImageRecord(id=1002, file_path="/tmp/b.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0)
        ],
        annotations=[]
    )
    run = embedding_service.run(
        EmbeddingRunRequest(
            dataset_id=dataset.id,
            model=EmbeddingModelSpec(provider="custom", model_id="deterministic-test", mode="image", batch_size=2)
        )
    )
    pairs = embedding_service.find_similar_pairs(run.id, threshold=-1.0)
    assert len(pairs) >= 1


def test_embedding_run_only_uses_active_view() -> None:
    dataset = repo.create_dataset(
        name="emb-view-test",
        source_uri="emb-view.json",
        images=[
            ImageRecord(id=2001, file_path="/tmp/a.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0),
            ImageRecord(id=2002, file_path="/tmp/b.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0),
            ImageRecord(id=2003, file_path="/tmp/c.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0)
        ],
        annotations=[
            AnnotationRecord(
                id=1,
                image_id=2001,
                class_id=1,
                class_name="cat",
                bbox_xywh=(0.0, 0.0, 16.0, 16.0),
                area=256.0,
                aspect_ratio=1.0
            ),
            AnnotationRecord(
                id=2,
                image_id=2002,
                class_id=2,
                class_name="dog",
                bbox_xywh=(0.0, 0.0, 16.0, 16.0),
                area=256.0,
                aspect_ratio=1.0
            )
        ]
    )
    run = embedding_service.run(
        EmbeddingRunRequest(
            dataset_id=dataset.id,
            model=EmbeddingModelSpec(provider="custom", model_id="deterministic-view", mode="image", batch_size=2),
            view=ViewSpec(
                filters=[FilterClause(field="class", operator="eq", value="cat")],
                page=1,
                page_size=10
            )
        )
    )

    projection = embedding_service.get_projection(run.id)

    assert run.config["image_count"] == 1
    assert [point["entity_id"] for point in projection["points"]] == [2001]


def test_projection_points_include_cluster_ids() -> None:
    dataset = repo.create_dataset(
        name="emb-projection-test",
        source_uri="emb-projection.json",
        images=[
            ImageRecord(id=3001, file_path="/tmp/1.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0),
            ImageRecord(id=3002, file_path="/tmp/2.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0),
            ImageRecord(id=3003, file_path="/tmp/3.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0),
            ImageRecord(id=3004, file_path="/tmp/4.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0),
            ImageRecord(id=3005, file_path="/tmp/5.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0),
            ImageRecord(id=3006, file_path="/tmp/6.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0)
        ],
        annotations=[]
    )
    run = embedding_service.run(
        EmbeddingRunRequest(
            dataset_id=dataset.id,
            model=EmbeddingModelSpec(provider="custom", model_id="deterministic-projection", mode="image", batch_size=6),
            view=ViewSpec(page=1, page_size=6)
        )
    )

    projection = embedding_service.get_projection(run.id)

    assert len(projection["points"]) == 6
    assert projection["cluster_count"] >= 1
    assert all("cluster_id" in point for point in projection["points"])


def test_embedding_ignores_page_size_and_flushes_float32_batches() -> None:
    dataset = repo.create_dataset(
        name="emb-flush-test",
        source_uri="emb-flush.json",
        images=[
            ImageRecord(id=4001, file_path="/tmp/1.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0),
            ImageRecord(id=4002, file_path="/tmp/2.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0),
            ImageRecord(id=4003, file_path="/tmp/3.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0)
        ],
        annotations=[]
    )
    previous_flush_rows = embedding_service._flush_rows
    embedding_service._flush_rows = 1
    try:
        run = embedding_service.run(
            EmbeddingRunRequest(
                dataset_id=dataset.id,
                model=EmbeddingModelSpec(provider="custom", model_id="deterministic-flush", mode="image", batch_size=2),
                view=ViewSpec(page=1, page_size=1)
            )
        )
    finally:
        embedding_service._flush_rows = previous_flush_rows

    table = pq.read_table(run.artifact_path)
    assert run.config["image_count"] == 3
    assert table.num_rows == 3
    assert pa.types.is_fixed_size_list(table.column("vector").type)
    assert table.column("vector").type.value_type == pa.float32()
    assert pq.ParquetFile(run.artifact_path).metadata.num_row_groups == 3
    assert {point["entity_id"] for point in embedding_service.get_projection(run.id)["points"]} == {4001, 4002, 4003}


def test_embedding_progress_counts_every_batch() -> None:
    dataset = repo.create_dataset(
        name="emb-progress-test",
        source_uri="emb-progress.json",
        images=[
            ImageRecord(id=5001, file_path="/tmp/1.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0),
            ImageRecord(id=5002, file_path="/tmp/2.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0),
            ImageRecord(id=5003, file_path="/tmp/3.jpg", directory_name="tmp", width=64, height=64, aspect_ratio=1.0)
        ],
        annotations=[]
    )
    updates: list[tuple[float, int | None, int | None, str]] = []

    def record(progress: float, message: str, completed: int | None = None, total: int | None = None) -> None:
        updates.append((progress, completed, total, message))

    embedding_service.run(
        EmbeddingRunRequest(
            dataset_id=dataset.id,
            model=EmbeddingModelSpec(provider="custom", model_id="deterministic-progress", mode="image", batch_size=2),
            view=ViewSpec(page=1, page_size=1)
        ),
        progress_callback=record
    )

    assert updates[0] == (0.0, 0, 3, "Loading embedding model")
    assert updates[1] == (2 / 3, 2, 3, "Embedded 2 of 3 images")
    assert updates[2] == (1.0, 3, 3, "Embedded 3 of 3 images")
    assert updates[-1][1:] == (3, 3, "Embedding run complete for 3 images")
