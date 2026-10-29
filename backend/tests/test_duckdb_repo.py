from __future__ import annotations

from pathlib import Path

from app.models.schemas import AnnotationRecord, FilterClause, ImageRecord, ViewSpec
from app.repositories.duckdb_repo import DuckDBRepository


def test_duckdb_repo_create_and_read(tmp_path: Path) -> None:
    repo = DuckDBRepository(str(tmp_path / "repo.duckdb"))
    dataset = repo.create_dataset(
        name="demo",
        source_uri="demo.json",
        images=[
            ImageRecord(id=1, file_path="/tmp/a.jpg", directory_name="tmp", width=100, height=100, aspect_ratio=1.0)
        ],
        annotations=[
            AnnotationRecord(
                id=1,
                image_id=1,
                class_id=1,
                class_name="car",
                bbox_xywh=(0.0, 0.0, 10.0, 10.0),
                area=100.0,
                aspect_ratio=1.0
            )
        ]
    )
    fetched = repo.get_dataset_bundle(dataset.id)
    assert fetched.dataset.name == "demo"
    assert len(fetched.images) == 1
    assert len(fetched.annotations) == 1


def test_duckdb_repo_reports_batched_insert_progress(tmp_path: Path) -> None:
    repo = DuckDBRepository(str(tmp_path / "repo_progress.duckdb"))
    repo._insert_batch_size = 2
    updates: list[tuple[float, str]] = []

    repo.create_dataset(
        name="progress-demo",
        source_uri="demo.json",
        images=[
            ImageRecord(id=1, file_path="/tmp/a.jpg", directory_name="tmp", width=100, height=100, aspect_ratio=1.0)
        ],
        annotations=[
            AnnotationRecord(
                id=index,
                image_id=1,
                class_id=1,
                class_name="car",
                bbox_xywh=(0.0, 0.0, 10.0, 10.0),
                area=100.0,
                aspect_ratio=1.0
            )
            for index in range(1, 6)
        ],
        progress_callback=lambda progress, message: updates.append((progress, message))
    )

    assert any(message == "Writing annotations to the database 0 of 5" for _, message in updates)
    assert any(message == "Writing annotations to the database 2 of 5" for _, message in updates)
    assert any(message == "Writing annotations to the database 4 of 5" for _, message in updates)
    assert any(message == "Writing annotations to the database 5 of 5" for _, message in updates)
    assert updates[-1] == (1.0, "Dataset ingestion complete")


def test_duckdb_repo_saved_views_and_runs_round_trip(tmp_path: Path) -> None:
    repo = DuckDBRepository(str(tmp_path / "repo_saved.duckdb"))
    dataset = repo.create_dataset(name="saved-demo", source_uri="saved.json", images=[], annotations=[])

    saved_view = repo.create_saved_view(
        dataset_id=dataset.id,
        name="cars",
        description="Only cars",
        spec=ViewSpec(filters=[{"field": "class", "operator": "eq", "value": "car"}], group_by="class", page=1, page_size=100)
    )
    updated_view = repo.update_saved_view(saved_view.id, description="Only car annotations")

    run = repo.create_run_record(
        dataset_id=dataset.id,
        saved_view_id=saved_view.id,
        run_type="embedding",
        status="running",
        config={"model_id": "clip"},
        view_spec=updated_view.spec
    )
    finished_run = repo.update_run_record(
        run.id,
        status="done",
        artifact_path="/tmp/vectors.parquet",
        artifact_paths={"parquet": "/tmp/vectors.parquet"}
    )

    saved_views = repo.list_saved_views(dataset.id)
    runs = repo.list_runs(dataset.id, run_type="embedding")

    assert saved_views[0].description == "Only car annotations"
    assert repo.get_saved_view(saved_view.id).name == "cars"
    assert finished_run.artifact_paths["parquet"] == "/tmp/vectors.parquet"
    assert runs[0].id == run.id
    assert repo.latest_run(dataset.id, run_type="embedding") is not None


def test_list_image_targets_applies_filters_and_ignores_paging(tmp_path: Path) -> None:
    repo = DuckDBRepository(str(tmp_path / "targets.duckdb"))
    dataset = repo.create_dataset(
        name="targets",
        source_uri="targets.json",
        images=[
            ImageRecord(id=1, file_path="/data/a.jpg", directory_name="a", width=10, height=10, aspect_ratio=1.0),
            ImageRecord(id=2, file_path="/data/b.jpg", directory_name="b", width=10, height=10, aspect_ratio=1.0),
            ImageRecord(id=3, file_path="/data/c.jpg", directory_name="b", width=10, height=10, aspect_ratio=1.0)
        ],
        annotations=[
            AnnotationRecord(
                id=1,
                image_id=1,
                class_id=1,
                class_name="cat",
                bbox_xywh=(0.0, 0.0, 10.0, 10.0),
                area=100.0,
                aspect_ratio=1.0
            ),
            AnnotationRecord(
                id=2,
                image_id=2,
                class_id=2,
                class_name="dog",
                bbox_xywh=(0.0, 0.0, 40.0, 10.0),
                area=400.0,
                aspect_ratio=4.0
            ),
            AnnotationRecord(
                id=3,
                image_id=3,
                class_id=1,
                class_name="cat",
                bbox_xywh=(0.0, 0.0, 12.0, 8.0),
                area=96.0,
                aspect_ratio=1.5
            )
        ]
    )

    targets = repo.list_image_targets(
        dataset.id,
        ViewSpec(
            filters=[
                FilterClause(field="directory", operator="eq", value="b"),
                FilterClause(field="class", operator="eq", value="cat"),
                FilterClause(field="bbox_width", operator="lte", value=20)
            ],
            page=1,
            page_size=1
        )
    )

    assert targets == [(3, "/data/c.jpg")]
    assert repo.image_file_paths(dataset.id)[3] == "/data/c.jpg"
