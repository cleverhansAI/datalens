from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class StorageOptions(BaseModel):
    protocol: str = "file"
    image_root: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class DatasetCreateRequest(BaseModel):
    name: str
    coco_json_path: str
    storage: StorageOptions = Field(default_factory=StorageOptions)


class Dataset(BaseModel):
    id: str
    name: str
    source_uri: str
    created_at: datetime
    image_count: int = 0
    annotation_count: int = 0


class ImageRecord(BaseModel):
    id: int
    file_path: str
    directory_name: str
    width: int
    height: int
    aspect_ratio: float
    avg_hue: float | None = None
    phash: str | None = None


class AnnotationRecord(BaseModel):
    id: int
    image_id: int
    class_id: int
    class_name: str
    bbox_xywh: tuple[float, float, float, float]
    area: float
    aspect_ratio: float


class FilterClause(BaseModel):
    field: str
    operator: Literal["eq", "neq", "in", "gte", "lte", "contains"]
    value: Any


class ViewSpec(BaseModel):
    filters: list[FilterClause] = Field(default_factory=list)
    group_by: str | None = None
    sort_by: str | None = None
    sort_desc: bool = False
    page: int = 1
    page_size: int = 50


class ViewQueryRequest(BaseModel):
    spec: ViewSpec | None = None
    saved_view_id: str | None = None


class GroupCount(BaseModel):
    key: str
    count: int


class ViewResult(BaseModel):
    total: int
    total_annotations: int = 0
    class_distribution: dict[str, int] = Field(default_factory=dict)
    groups: list[GroupCount] = Field(default_factory=list)
    avg_width: float = 0
    avg_height: float = 0
    avg_aspect_ratio: float = 0
    images: list[ImageRecord] = Field(default_factory=list)
    annotations: list[AnnotationRecord] = Field(default_factory=list)


class SavedView(BaseModel):
    id: str
    dataset_id: str
    name: str
    description: str = ""
    spec: ViewSpec = Field(default_factory=ViewSpec)
    created_at: datetime
    updated_at: datetime


class SavedViewCreateRequest(BaseModel):
    name: str
    description: str = ""
    spec: ViewSpec = Field(default_factory=ViewSpec)


class SavedViewUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    spec: ViewSpec | None = None


class EmbeddingModelSpec(BaseModel):
    provider: Literal["torch", "hf", "custom"] = "hf"
    model_id: str
    mode: Literal["image", "crop", "both"] = "image"
    batch_size: int = 32


class EmbeddingRunRequest(BaseModel):
    dataset_id: str
    model: EmbeddingModelSpec
    view: ViewSpec | None = None
    saved_view_id: str | None = None


class ExportViewRequest(BaseModel):
    view: ViewSpec | None = None
    saved_view_id: str | None = None


class RunRecord(BaseModel):
    id: str
    dataset_id: str
    saved_view_id: str | None = None
    run_type: str
    status: Literal["queued", "running", "done", "failed"] = "queued"
    config: dict[str, Any] = Field(default_factory=dict)
    view_spec: ViewSpec | None = None
    artifact_path: str | None = None
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class TaskStatus(BaseModel):
    task_id: str
    state: Literal["queued", "running", "done", "failed"] = "queued"
    progress: float = 0.0
    completed: int | None = None
    total: int | None = None
    message: str = ""
    result: dict[str, Any] | None = None


class SessionState(BaseModel):
    dataset_id: str | None = None
    view: ViewSpec | None = None
