from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

import duckdb

from app.models.schemas import (
    AnnotationRecord,
    Dataset,
    FilterClause,
    ImageRecord,
    RunRecord,
    SavedView,
    ViewSpec,
)


@dataclass
class DatasetBundle:
    dataset: Dataset
    images: list[ImageRecord] = field(default_factory=list)
    annotations: list[AnnotationRecord] = field(default_factory=list)


class DuckDBRepository:
    _insert_batch_size = 10000

    def __init__(self, db_url: str) -> None:
        self._lock = threading.RLock()
        self._conn = duckdb.connect(self._resolve_path(db_url))
        self._create_tables()

    def close(self) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute("CHECKPOINT")
            self._conn.close()
            self._conn = None

    def _resolve_path(self, db_url: str) -> str:
        if db_url.startswith("sqlite:///"):
            # Reuse config key while storing in DuckDB file.
            db_path = db_url.replace("sqlite:///", "")
        else:
            db_path = db_url
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        return db_path

    def _create_tables(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS datasets (
                    id VARCHAR PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    source_uri VARCHAR NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    image_count INTEGER NOT NULL,
                    annotation_count INTEGER NOT NULL
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS images (
                    dataset_id VARCHAR NOT NULL,
                    id BIGINT NOT NULL,
                    file_path VARCHAR NOT NULL,
                    directory_name VARCHAR NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    aspect_ratio DOUBLE NOT NULL,
                    avg_hue DOUBLE,
                    phash VARCHAR
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS annotations (
                    dataset_id VARCHAR NOT NULL,
                    id BIGINT NOT NULL,
                    image_id BIGINT NOT NULL,
                    class_id INTEGER NOT NULL,
                    class_name VARCHAR NOT NULL,
                    bbox_x DOUBLE NOT NULL,
                    bbox_y DOUBLE NOT NULL,
                    bbox_w DOUBLE NOT NULL,
                    bbox_h DOUBLE NOT NULL,
                    area DOUBLE NOT NULL,
                    aspect_ratio DOUBLE NOT NULL
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_views (
                    id VARCHAR PRIMARY KEY,
                    dataset_id VARCHAR NOT NULL,
                    name VARCHAR NOT NULL,
                    description VARCHAR NOT NULL,
                    spec_json VARCHAR NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id VARCHAR PRIMARY KEY,
                    dataset_id VARCHAR NOT NULL,
                    saved_view_id VARCHAR,
                    run_type VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    config_json VARCHAR NOT NULL,
                    view_spec_json VARCHAR,
                    artifact_path VARCHAR,
                    artifact_paths_json VARCHAR NOT NULL,
                    error_message VARCHAR,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                );
                """
            )

    def create_dataset(
        self,
        name: str,
        source_uri: str,
        images: list[ImageRecord],
        annotations: list[AnnotationRecord],
        progress_callback: Callable[[float, str], None] | None = None,
        dataset_id: str | None = None
    ) -> Dataset:
        dataset_id = dataset_id or str(uuid4())
        created_at = datetime.now(tz=UTC).replace(tzinfo=None)
        dataset = Dataset(
            id=dataset_id,
            name=name,
            source_uri=source_uri,
            created_at=datetime.now(tz=UTC),
            image_count=len(images),
            annotation_count=len(annotations)
        )
        if progress_callback:
            progress_callback(0.84, "Creating dataset entry")
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO datasets (id, name, source_uri, created_at, image_count, annotation_count)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [dataset_id, name, source_uri, created_at, len(images), len(annotations)]
            )
            if images:
                self._insert_records_in_batches(
                    """
                    INSERT INTO images (dataset_id, id, file_path, directory_name, width, height, aspect_ratio, avg_hue, phash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    records=images,
                    row_builder=lambda img: [
                        dataset_id,
                        img.id,
                        img.file_path,
                        img.directory_name,
                        img.width,
                        img.height,
                        img.aspect_ratio,
                        img.avg_hue,
                        img.phash
                    ],
                    progress_callback=progress_callback,
                    progress_start=0.84,
                    progress_end=0.9,
                    progress_message="Writing images to the database"
                )
            if annotations:
                self._insert_records_in_batches(
                    """
                    INSERT INTO annotations
                    (dataset_id, id, image_id, class_id, class_name, bbox_x, bbox_y, bbox_w, bbox_h, area, aspect_ratio)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    records=annotations,
                    row_builder=lambda ann: [
                        dataset_id,
                        ann.id,
                        ann.image_id,
                        ann.class_id,
                        ann.class_name,
                        ann.bbox_xywh[0],
                        ann.bbox_xywh[1],
                        ann.bbox_xywh[2],
                        ann.bbox_xywh[3],
                        ann.area,
                        ann.aspect_ratio
                    ],
                    progress_callback=progress_callback,
                    progress_start=0.9,
                    progress_end=1.0,
                    progress_message="Writing annotations to the database"
                )
        if progress_callback:
            progress_callback(1.0, "Dataset ingestion complete")
        return dataset

    def _insert_records_in_batches(
        self,
        sql: str,
        *,
        records: list[ImageRecord] | list[AnnotationRecord],
        row_builder: Callable[[ImageRecord | AnnotationRecord], list],
        progress_callback: Callable[[float, str], None] | None,
        progress_start: float,
        progress_end: float,
        progress_message: str
    ) -> None:
        total = len(records)
        if total == 0:
            return
        if progress_callback:
            progress_callback(progress_start, f"{progress_message} 0 of {total}")
        for start in range(0, total, self._insert_batch_size):
            batch = records[start : start + self._insert_batch_size]
            self._conn.executemany(sql, [row_builder(record) for record in batch])
            if progress_callback:
                completed = start + len(batch)
                progress = progress_start + ((progress_end - progress_start) * completed / total)
                progress_callback(progress, f"{progress_message} {completed} of {total}")

    def list_datasets(self) -> list[Dataset]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, name, source_uri, created_at, image_count, annotation_count
                FROM datasets
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [
            Dataset(
                id=row[0],
                name=row[1],
                source_uri=row[2],
                created_at=row[3].replace(tzinfo=UTC),
                image_count=row[4],
                annotation_count=row[5]
            )
            for row in rows
        ]

    def create_saved_view(
        self,
        *,
        dataset_id: str,
        name: str,
        description: str,
        spec: ViewSpec
    ) -> SavedView:
        saved_view_id = str(uuid4())
        now = datetime.now(tz=UTC).replace(tzinfo=None)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO saved_views (id, dataset_id, name, description, spec_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [saved_view_id, dataset_id, name, description, self._dump_json(spec.model_dump(mode="json")), now, now]
            )
        return SavedView(
            id=saved_view_id,
            dataset_id=dataset_id,
            name=name,
            description=description,
            spec=spec,
            created_at=now.replace(tzinfo=UTC),
            updated_at=now.replace(tzinfo=UTC)
        )

    def list_saved_views(self, dataset_id: str) -> list[SavedView]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, dataset_id, name, description, spec_json, created_at, updated_at
                FROM saved_views
                WHERE dataset_id = ?
                ORDER BY updated_at DESC, created_at DESC
                """,
                [dataset_id]
            ).fetchall()
        return [self._saved_view_from_row(row) for row in rows]

    def get_saved_view(self, saved_view_id: str) -> SavedView:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, dataset_id, name, description, spec_json, created_at, updated_at
                FROM saved_views
                WHERE id = ?
                """,
                [saved_view_id]
            ).fetchone()
        if row is None:
            raise KeyError(f"Saved view not found: {saved_view_id}")
        return self._saved_view_from_row(row)

    def update_saved_view(
        self,
        saved_view_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        spec: ViewSpec | None = None
    ) -> SavedView:
        current = self.get_saved_view(saved_view_id)
        updated_name = name if name is not None else current.name
        updated_description = description if description is not None else current.description
        updated_spec = spec if spec is not None else current.spec
        updated_at = datetime.now(tz=UTC).replace(tzinfo=None)
        with self._lock:
            self._conn.execute(
                """
                UPDATE saved_views
                SET name = ?, description = ?, spec_json = ?, updated_at = ?
                WHERE id = ?
                """,
                [
                    updated_name,
                    updated_description,
                    self._dump_json(updated_spec.model_dump(mode="json")),
                    updated_at,
                    saved_view_id
                ]
            )
        return SavedView(
            id=current.id,
            dataset_id=current.dataset_id,
            name=updated_name,
            description=updated_description,
            spec=updated_spec,
            created_at=current.created_at,
            updated_at=updated_at.replace(tzinfo=UTC)
        )

    def delete_saved_view(self, saved_view_id: str) -> None:
        self.get_saved_view(saved_view_id)
        with self._lock:
            self._conn.execute("DELETE FROM saved_views WHERE id = ?", [saved_view_id])

    def create_run_record(
        self,
        *,
        dataset_id: str,
        run_type: str,
        config: dict,
        saved_view_id: str | None = None,
        view_spec: ViewSpec | None = None,
        status: str = "queued",
        artifact_path: str | None = None,
        artifact_paths: dict[str, str] | None = None,
        error_message: str | None = None
    ) -> RunRecord:
        run_id = str(uuid4())
        now = datetime.now(tz=UTC).replace(tzinfo=None)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO runs (
                    id, dataset_id, saved_view_id, run_type, status, config_json, view_spec_json,
                    artifact_path, artifact_paths_json, error_message, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    run_id,
                    dataset_id,
                    saved_view_id,
                    run_type,
                    status,
                    self._dump_json(config),
                    self._dump_json(view_spec.model_dump(mode="json")) if view_spec is not None else None,
                    artifact_path,
                    self._dump_json(artifact_paths or {}),
                    error_message,
                    now,
                    now
                ]
            )
        return RunRecord(
            id=run_id,
            dataset_id=dataset_id,
            saved_view_id=saved_view_id,
            run_type=run_type,
            status=status,
            config=config,
            view_spec=view_spec,
            artifact_path=artifact_path,
            artifact_paths=artifact_paths or {},
            error_message=error_message,
            created_at=now.replace(tzinfo=UTC),
            updated_at=now.replace(tzinfo=UTC)
        )

    def get_run_record(self, run_id: str) -> RunRecord:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, dataset_id, saved_view_id, run_type, status, config_json, view_spec_json,
                       artifact_path, artifact_paths_json, error_message, created_at, updated_at
                FROM runs
                WHERE id = ?
                """,
                [run_id]
            ).fetchone()
        if row is None:
            raise KeyError(f"Run not found: {run_id}")
        return self._run_record_from_row(row)

    def update_run_record(
        self,
        run_id: str,
        *,
        status: str | None = None,
        config: dict | None = None,
        saved_view_id: str | None = None,
        view_spec: ViewSpec | None = None,
        artifact_path: str | None = None,
        artifact_paths: dict[str, str] | None = None,
        error_message: str | None = None
    ) -> RunRecord:
        current = self.get_run_record(run_id)
        updated_at = datetime.now(tz=UTC).replace(tzinfo=None)
        next_record = RunRecord(
            id=current.id,
            dataset_id=current.dataset_id,
            saved_view_id=saved_view_id if saved_view_id is not None else current.saved_view_id,
            run_type=current.run_type,
            status=status if status is not None else current.status,
            config=config if config is not None else current.config,
            view_spec=view_spec if view_spec is not None else current.view_spec,
            artifact_path=artifact_path if artifact_path is not None else current.artifact_path,
            artifact_paths=artifact_paths if artifact_paths is not None else current.artifact_paths,
            error_message=error_message if error_message is not None else current.error_message,
            created_at=current.created_at,
            updated_at=updated_at.replace(tzinfo=UTC)
        )
        with self._lock:
            self._conn.execute(
                """
                UPDATE runs
                SET saved_view_id = ?, status = ?, config_json = ?, view_spec_json = ?, artifact_path = ?,
                    artifact_paths_json = ?, error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                [
                    next_record.saved_view_id,
                    next_record.status,
                    self._dump_json(next_record.config),
                    self._dump_json(next_record.view_spec.model_dump(mode="json"))
                    if next_record.view_spec is not None
                    else None,
                    next_record.artifact_path,
                    self._dump_json(next_record.artifact_paths),
                    next_record.error_message,
                    updated_at,
                    run_id
                ]
            )
        return next_record

    def list_runs(self, dataset_id: str, run_type: str | None = None) -> list[RunRecord]:
        query = """
            SELECT id, dataset_id, saved_view_id, run_type, status, config_json, view_spec_json,
                   artifact_path, artifact_paths_json, error_message, created_at, updated_at
            FROM runs
            WHERE dataset_id = ?
        """
        params: list[str] = [dataset_id]
        if run_type is not None:
            query += " AND run_type = ?"
            params.append(run_type)
        query += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._run_record_from_row(row) for row in rows]

    def latest_run(self, dataset_id: str, run_type: str | None = None) -> RunRecord | None:
        runs = self.list_runs(dataset_id, run_type=run_type)
        if not runs:
            return None
        return runs[0]

    def list_image_targets(self, dataset_id: str, spec: ViewSpec) -> list[tuple[int, str]]:
        with self._lock:
            self._require_dataset(dataset_id)
            where_sql, params = _image_target_where(spec)
            order_sql = _image_target_order(spec)
            rows = self._conn.execute(
                f"""
                SELECT images.id, images.file_path
                FROM images
                WHERE images.dataset_id = ?
                {where_sql}
                {order_sql}
                """,
                [dataset_id, *params]
            ).fetchall()
        return [(int(row[0]), str(row[1])) for row in rows]

    def image_file_paths(self, dataset_id: str) -> dict[int, str]:
        with self._lock:
            self._require_dataset(dataset_id)
            rows = self._conn.execute(
                """
                SELECT id, file_path
                FROM images
                WHERE dataset_id = ?
                """,
                [dataset_id]
            ).fetchall()
        return {int(row[0]): str(row[1]) for row in rows}

    def _require_dataset(self, dataset_id: str) -> None:
        row = self._conn.execute(
            "SELECT 1 FROM datasets WHERE id = ?",
            [dataset_id]
        ).fetchone()
        if row is None:
            raise KeyError(f"Dataset not found: {dataset_id}")

    def get_dataset_bundle(self, dataset_id: str) -> DatasetBundle:
        with self._lock:
            dataset_row = self._conn.execute(
                """
                SELECT id, name, source_uri, created_at, image_count, annotation_count
                FROM datasets
                WHERE id = ?
                """,
                [dataset_id]
            ).fetchone()
            if dataset_row is None:
                raise KeyError(f"Dataset not found: {dataset_id}")

            image_rows = self._conn.execute(
                """
                SELECT id, file_path, directory_name, width, height, aspect_ratio, avg_hue, phash
                FROM images
                WHERE dataset_id = ?
                ORDER BY id
                """,
                [dataset_id]
            ).fetchall()
            ann_rows = self._conn.execute(
                """
                SELECT id, image_id, class_id, class_name, bbox_x, bbox_y, bbox_w, bbox_h, area, aspect_ratio
                FROM annotations
                WHERE dataset_id = ?
                ORDER BY id
                """,
                [dataset_id]
            ).fetchall()

        dataset = Dataset(
            id=dataset_row[0],
            name=dataset_row[1],
            source_uri=dataset_row[2],
            created_at=dataset_row[3].replace(tzinfo=UTC),
            image_count=dataset_row[4],
            annotation_count=dataset_row[5]
        )
        images = [
            ImageRecord(
                id=row[0],
                file_path=row[1],
                directory_name=row[2],
                width=row[3],
                height=row[4],
                aspect_ratio=row[5],
                avg_hue=row[6],
                phash=row[7]
            )
            for row in image_rows
        ]
        annotations = [
            AnnotationRecord(
                id=row[0],
                image_id=row[1],
                class_id=row[2],
                class_name=row[3],
                bbox_xywh=(row[4], row[5], row[6], row[7]),
                area=row[8],
                aspect_ratio=row[9]
            )
            for row in ann_rows
        ]
        return DatasetBundle(dataset=dataset, images=images, annotations=annotations)

    def _saved_view_from_row(self, row: tuple) -> SavedView:
        spec_data = self._load_json(row[4], {})
        return SavedView(
            id=row[0],
            dataset_id=row[1],
            name=row[2],
            description=row[3],
            spec=ViewSpec.model_validate(spec_data),
            created_at=row[5].replace(tzinfo=UTC),
            updated_at=row[6].replace(tzinfo=UTC)
        )

    def _run_record_from_row(self, row: tuple) -> RunRecord:
        view_spec = None
        if row[6]:
            view_spec = ViewSpec.model_validate(self._load_json(row[6], {}))
        return RunRecord(
            id=row[0],
            dataset_id=row[1],
            saved_view_id=row[2],
            run_type=row[3],
            status=row[4],
            config=self._load_json(row[5], {}),
            view_spec=view_spec,
            artifact_path=row[7],
            artifact_paths=self._load_json(row[8], {}),
            error_message=row[9],
            created_at=row[10].replace(tzinfo=UTC),
            updated_at=row[11].replace(tzinfo=UTC)
        )

    def _dump_json(self, payload: dict[str, object]) -> str:
        return json.dumps(payload, separators=(",", ":"))

    def _load_json(self, payload: str | None, default: dict[str, object]) -> dict[str, object]:
        if not payload:
            return default
        return json.loads(payload)


_IMAGE_FILTER_COLUMNS = {
    "directory": "images.directory_name",
    "id": "images.id"
}
_ANNOTATION_FILTER_COLUMNS = {
    "class": "annotations.class_name",
    "area": "annotations.area",
    "bbox_width": "annotations.bbox_w",
    "bbox_height": "annotations.bbox_h"
}
_SORT_COLUMNS = {
    "id": "images.id",
    "file_path": "images.file_path",
    "directory_name": "images.directory_name",
    "width": "images.width",
    "height": "images.height",
    "aspect_ratio": "images.aspect_ratio"
}


def _image_target_where(spec: ViewSpec) -> tuple[str, list[object]]:
    params: list[object] = []
    clauses: list[str] = []
    for clause in spec.filters:
        column = _IMAGE_FILTER_COLUMNS.get(clause.field)
        if column is None:
            continue
        sql = _filter_sql(column, clause, params)
        if sql is not None:
            clauses.append(sql)

    annotation_clauses: list[str] = []
    for clause in spec.filters:
        column = _ANNOTATION_FILTER_COLUMNS.get(clause.field)
        if column is None:
            continue
        sql = _filter_sql(column, clause, params)
        if sql is not None:
            annotation_clauses.append(sql)
    if annotation_clauses:
        joined = " AND ".join(annotation_clauses)
        clauses.append(
            "EXISTS ("
            "SELECT 1 FROM annotations "
            "WHERE annotations.dataset_id = images.dataset_id "
            "AND annotations.image_id = images.id "
            f"AND {joined})"
        )
    if not clauses:
        return "", params
    return "AND " + " AND ".join(clauses), params


def _image_target_order(spec: ViewSpec) -> str:
    column = _SORT_COLUMNS.get(spec.sort_by or "")
    if column is None:
        return "ORDER BY images.id ASC"
    direction = "DESC" if spec.sort_desc else "ASC"
    return f"ORDER BY {column} {direction}, images.id ASC"


def _filter_sql(column: str, clause: FilterClause, params: list[object]) -> str | None:
    if clause.operator == "eq":
        params.append(clause.value)
        return f"{column} = ?"
    if clause.operator == "neq":
        params.append(clause.value)
        return f"{column} <> ?"
    if clause.operator == "gte":
        params.append(clause.value)
        return f"{column} >= ?"
    if clause.operator == "lte":
        params.append(clause.value)
        return f"{column} <= ?"
    if clause.operator == "in":
        values = list(clause.value) if isinstance(clause.value, (list, tuple)) else [clause.value]
        if not values:
            return "1 = 0"
        params.extend(values)
        placeholders = ", ".join("?" for _ in values)
        return f"{column} IN ({placeholders})"
    if clause.operator == "contains":
        params.append(_like_contains(str(clause.value)))
        return f"lower(CAST({column} AS VARCHAR)) LIKE ? ESCAPE '\\'"
    return None


def _like_contains(value: str) -> str:
    escaped = value.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
