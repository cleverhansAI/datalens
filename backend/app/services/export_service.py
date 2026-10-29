from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from app.models.schemas import ViewSpec
from app.repositories import repo
from app.services.view_service import view_service


class ExportService:
    def export_view_to_coco(
        self,
        dataset_id: str,
        spec: ViewSpec | None = None,
        *,
        saved_view_id: str | None = None,
        target_dir: str = "artifacts"
    ) -> str:
        result = view_service.resolve(dataset_id, spec, saved_view_id=saved_view_id)
        dataset = repo.get_dataset_bundle(dataset_id).dataset
        os.makedirs(target_dir, exist_ok=True)
        ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
        out_path = Path(target_dir) / f"{dataset.name}_{ts}.json"
        images = [
            {
                "id": image.id,
                "file_name": image.file_path,
                "width": image.width,
                "height": image.height
            }
            for image in result.images
        ]
        annotations = [
            {
                "id": ann.id,
                "image_id": ann.image_id,
                "category_id": ann.class_id,
                "bbox": list(ann.bbox_xywh),
                "area": ann.area
            }
            for ann in result.annotations
        ]
        cat_map = {(ann.class_id, ann.class_name) for ann in result.annotations}
        categories = [{"id": class_id, "name": class_name} for class_id, class_name in sorted(cat_map)]
        with out_path.open("w", encoding="utf-8") as f:
            json.dump({"images": images, "annotations": annotations, "categories": categories}, f, indent=2)
        return str(out_path)


export_service = ExportService()
