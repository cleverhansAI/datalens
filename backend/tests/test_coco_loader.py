from __future__ import annotations

import json
from pathlib import Path

from app.loaders.coco_loader import CocoDatasetLoader


def test_coco_loader_validate_and_load(tmp_path: Path) -> None:
    coco = {
        "images": [{"id": 1, "file_name": "images/sample.jpg", "width": 800, "height": 600}],
        "annotations": [{"id": 10, "image_id": 1, "category_id": 1, "bbox": [10, 20, 30, 40]}],
        "categories": [{"id": 1, "name": "car"}]
    }
    coco_path = tmp_path / "sample.json"
    coco_path.write_text(json.dumps(coco), encoding="utf-8")

    loader = CocoDatasetLoader()
    result = loader.validate(str(coco_path), {"protocol": "file", "options": {}})
    assert result.valid
    progress_updates: list[tuple[float, str]] = []
    loaded = loader.load(
        str(coco_path),
        {"protocol": "file", "image_root": "/tmp/data", "options": {}},
        progress_callback=lambda progress, message: progress_updates.append((progress, message))
    )
    assert loaded.dataset_name == "sample"
    assert len(loaded.images) == 1
    assert len(loaded.annotations) == 1
    assert loaded.images[0].directory_name == "images"
    assert progress_updates[0] == (0.05, "Reading COCO JSON")
    assert progress_updates[-1] == (0.8, "Prepared dataset records")
