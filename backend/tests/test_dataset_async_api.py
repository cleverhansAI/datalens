from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from datetime import UTC, datetime
from uuid import uuid4

test_db_path = Path(tempfile.gettempdir()) / f"datalens-test-{uuid4()}.db"
os.environ["DATALENS_METADATA_DB_URL"] = f"sqlite:///{test_db_path}"

from fastapi.testclient import TestClient

from app.api.v1 import datasets as datasets_api
from app.main import app
from app.models.schemas import Dataset, ImageRecord
from app.repositories import repo


def test_create_dataset_async_reports_progress(monkeypatch) -> None:
    def fake_create(request, progress_callback=None) -> Dataset:
        assert progress_callback is not None
        progress_callback(0.3, "Loading images")
        progress_callback(0.8, "Writing dataset")
        return Dataset(
            id="dataset-1",
            name=request.name,
            source_uri=request.coco_json_path,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            image_count=12,
            annotation_count=34
        )

    monkeypatch.setattr(datasets_api.dataset_service, "create", fake_create)

    client = TestClient(app)
    response = client.post(
        "/api/v1/datasets/async",
        json={
            "name": "async-dataset",
            "coco_json_path": "/tmp/sample.json",
            "storage": {"protocol": "file", "image_root": None, "options": {}}
        }
    )
    assert response.status_code == 200
    task_id = response.json()["task_id"]

    deadline = time.time() + 2.0
    status: dict[str, object] | None = None
    while time.time() < deadline:
        status_response = client.get(f"/api/v1/tasks/{task_id}")
        assert status_response.status_code == 200
        status = status_response.json()
        if status["state"] == "done":
            break
        time.sleep(0.01)

    assert status is not None
    assert status["state"] == "done"
    assert status["result"]["id"] == "dataset-1"
    assert status["result"]["name"] == "async-dataset"


def test_saved_view_crud_api() -> None:
    dataset = repo.create_dataset(
        name="view-dataset",
        source_uri="view.json",
        images=[
            ImageRecord(id=1, file_path="/tmp/a.jpg", directory_name="tmp", width=100, height=100, aspect_ratio=1.0)
        ],
        annotations=[]
    )
    client = TestClient(app)
    create_response = client.post(
        f"/api/v1/views/{dataset.id}/saved",
        json={
            "name": "cars",
            "description": "Only cars",
            "spec": {"filters": [{"field": "class", "operator": "eq", "value": "car"}], "page": 1, "page_size": 50}
        }
    )
    assert create_response.status_code == 200
    saved_view_id = create_response.json()["id"]

    list_response = client.get(f"/api/v1/views/{dataset.id}/saved")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == saved_view_id

    update_response = client.patch(f"/api/v1/views/saved/{saved_view_id}", json={"description": "Updated"})
    assert update_response.status_code == 200
    assert update_response.json()["description"] == "Updated"

    delete_response = client.delete(f"/api/v1/views/saved/{saved_view_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"ok": True}
