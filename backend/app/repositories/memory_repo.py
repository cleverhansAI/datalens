from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from app.models.schemas import AnnotationRecord, Dataset, ImageRecord


@dataclass
class DatasetBundle:
    dataset: Dataset
    images: list[ImageRecord] = field(default_factory=list)
    annotations: list[AnnotationRecord] = field(default_factory=list)


class MemoryRepository:
    def __init__(self) -> None:
        self.datasets: dict[str, DatasetBundle] = {}

    def create_dataset(
        self,
        name: str,
        source_uri: str,
        images: list[ImageRecord],
        annotations: list[AnnotationRecord],
        progress_callback: Callable[[float, str], None] | None = None
    ) -> Dataset:
        dataset_id = str(uuid4())
        dataset = Dataset(
            id=dataset_id,
            name=name,
            source_uri=source_uri,
            created_at=datetime.now(tz=UTC),
            image_count=len(images),
            annotation_count=len(annotations)
        )
        if progress_callback:
            progress_callback(0.9, "Storing dataset in memory")
        self.datasets[dataset_id] = DatasetBundle(
            dataset=dataset,
            images=images,
            annotations=annotations
        )
        if progress_callback:
            progress_callback(1.0, "Dataset ingestion complete")
        return dataset

    def get_dataset_bundle(self, dataset_id: str) -> DatasetBundle:
        if dataset_id not in self.datasets:
            raise KeyError(f"Dataset not found: {dataset_id}")
        return self.datasets[dataset_id]

    def list_datasets(self) -> list[Dataset]:
        return [bundle.dataset for bundle in self.datasets.values()]


repo = MemoryRepository()
