from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
from typing import Any

from app.loaders.base import DatasetLoadResult, DatasetLoader, ValidationResult
from app.models.schemas import AnnotationRecord, ImageRecord
from app.storage.fsspec_adapter import StorageAdapter


class CocoDatasetLoader(DatasetLoader):
    def can_load(self, source: str) -> bool:
        return source.endswith(".json")

    def validate(self, source: str, options: dict[str, Any]) -> ValidationResult:
        storage = StorageAdapter(protocol=options.get("protocol", "file"), options=options.get("options"))
        if not storage.exists(source):
            return ValidationResult(valid=False, errors=[f"COCO file not found: {source}"])
        try:
            with storage.open(source, "r") as f:
                payload = json.load(f)
        except Exception as exc:
            return ValidationResult(valid=False, errors=[f"Invalid COCO JSON: {exc}"])

        required = {"images", "annotations", "categories"}
        missing = required.difference(set(payload.keys()))
        if missing:
            return ValidationResult(valid=False, errors=[f"Missing keys: {sorted(missing)}"])
        return ValidationResult(valid=True)

    def load(
        self,
        source: str,
        options: dict[str, Any],
        progress_callback: Callable[[float, str], None] | None = None
    ) -> DatasetLoadResult:
        if progress_callback:
            progress_callback(0.05, "Reading COCO JSON")
        storage = StorageAdapter(protocol=options.get("protocol", "file"), options=options.get("options"))
        image_root = options.get("image_root")
        with storage.open(source, "r") as f:
            payload = json.load(f)

        image_count = len(payload["images"])
        annotation_count = len(payload["annotations"])
        if progress_callback:
            progress_callback(
                0.1,
                f"Loaded COCO JSON ({image_count} images, {annotation_count} annotations)"
            )

        categories = {cat["id"]: cat.get("name", f"class_{cat['id']}") for cat in payload["categories"]}
        images: list[ImageRecord] = []
        annotations: list[AnnotationRecord] = []
        image_step = max(1, image_count // 20) if image_count else 1
        annotation_step = max(1, annotation_count // 20) if annotation_count else 1

        for index, image in enumerate(payload["images"], start=1):
            file_path = storage.join(image_root, image["file_name"])
            width = int(image.get("width", 0))
            height = int(image.get("height", 0))
            aspect_ratio = float(width / height) if height > 0 else 0.0
            images.append(
                ImageRecord(
                    id=int(image["id"]),
                    file_path=file_path,
                    directory_name=StorageAdapter.last_directory_name(file_path),
                    width=width,
                    height=height,
                    aspect_ratio=aspect_ratio
                )
            )
            if progress_callback and (index == image_count or index == 1 or index % image_step == 0):
                progress_callback(
                    0.1 + (0.25 * index / max(image_count, 1)),
                    f"Prepared image metadata {index} of {image_count}"
                )

        for index, ann in enumerate(payload["annotations"], start=1):
            x, y, w, h = [float(v) for v in ann.get("bbox", [0, 0, 0, 0])]
            area = float(ann.get("area", w * h))
            aspect_ratio = float(w / h) if h > 0 else 0.0
            class_id = int(ann["category_id"])
            annotations.append(
                AnnotationRecord(
                    id=int(ann["id"]),
                    image_id=int(ann["image_id"]),
                    class_id=class_id,
                    class_name=categories.get(class_id, f"class_{class_id}"),
                    bbox_xywh=(x, y, w, h),
                    area=area,
                    aspect_ratio=aspect_ratio
                )
            )
            if progress_callback and (index == annotation_count or index == 1 or index % annotation_step == 0):
                progress_callback(
                    0.35 + (0.45 * index / max(annotation_count, 1)),
                    f"Prepared annotations {index} of {annotation_count}"
                )

        dataset_name = Path(source).stem
        if progress_callback:
            progress_callback(0.8, "Prepared dataset records")
        return DatasetLoadResult(
            dataset_name=dataset_name,
            source_uri=source,
            images=images,
            annotations=annotations
        )
