from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from app.core.workspace import (
    clear_server_lock,
    find_project_root,
    pid_alive,
    read_running_server,
    remember_workspace,
    resolve_workspace,
    write_server_lock,
)
from app.main import app
from app.models.schemas import (
    AnnotationRecord,
    DatasetCreateRequest,
    ImageRecord,
    StorageOptions,
    ViewSpec,
)
from app.repositories.project_store import ProjectStore
from app.services.dataset_service import dataset_service


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname = \"demo\"\n", encoding="utf-8")
    return project


def test_workspace_uses_project_directory_and_falls_back_to_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    project = _project(tmp_path)
    nested = project / "src" / "pkg"
    nested.mkdir(parents=True)
    workspace = resolve_workspace(nested)
    assert find_project_root(nested) == project
    assert workspace.project_root == project
    assert workspace.data_root == project / ".datalens"
    assert workspace.user_home == tmp_path / "xdg" / "datalens"

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    fallback = resolve_workspace(scratch)
    assert fallback.project_root is None
    assert fallback.data_root == fallback.user_home


def test_recent_projects_and_server_lock(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    workspace = resolve_workspace(_project(tmp_path))
    remember_workspace(workspace)
    remember_workspace(workspace)
    recent = json.loads((workspace.user_home / "recent.json").read_text(encoding="utf-8"))
    assert len(recent["projects"]) == 1
    assert recent["projects"][0]["path"] == str(workspace.project_root)

    write_server_lock(workspace.data_root, os.getpid(), "127.0.0.1", 4321)
    assert read_running_server(workspace.data_root) is not None
    assert pid_alive(os.getpid())
    clear_server_lock(workspace.data_root, os.getpid())
    assert read_running_server(workspace.data_root) is None

    write_server_lock(workspace.data_root, 2_000_000_000, "127.0.0.1", 1)
    assert read_running_server(workspace.data_root) is None


def test_project_store_reopens_saved_dataset_without_loading_every_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    project = _project(tmp_path)
    image = project / "images" / "a.jpg"
    image.parent.mkdir()
    image.write_bytes(b"image")
    workspace = resolve_workspace(project)
    store = ProjectStore(workspace)
    dataset = store.create_dataset(
        name="demo",
        source_uri=str(project / "annotations.json"),
        images=[
            ImageRecord(
                id=1,
                file_path=str(image),
                directory_name="images",
                width=10,
                height=10,
                aspect_ratio=1.0
            )
        ],
        annotations=[
            AnnotationRecord(
                id=1,
                image_id=1,
                class_id=1,
                class_name="car",
                bbox_xywh=(0.0, 0.0, 4.0, 4.0),
                area=16.0,
                aspect_ratio=1.0
            )
        ]
    )
    saved = store.create_saved_view(
        dataset_id=dataset.id,
        name="cars",
        description="Cars",
        spec=ViewSpec(filters=[{"field": "class", "operator": "eq", "value": "car"}], page=1, page_size=10)
    )
    store.close()

    reopened = ProjectStore(workspace)
    assert reopened._connections == {}
    listed = reopened.list_datasets()
    assert reopened._connections == {}
    assert listed[0].id == dataset.id
    bundle = reopened.get_dataset_bundle(dataset.id)
    assert bundle.images[0].file_path == str(image.resolve())
    assert reopened.get_saved_view(saved.id).name == "cars"
    db_path = workspace.data_root / "datasets" / dataset.id / "catalog.duckdb"
    reopened.close()
    with duckdb.connect(str(db_path), read_only=True) as connection:
        stored_path = connection.execute("SELECT file_path FROM images").fetchone()[0]
    assert stored_path == "images/a.jpg"


def test_unchanged_coco_file_reuses_the_saved_dataset(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    project = _project(tmp_path)
    image_root = project / "images"
    image_root.mkdir()
    coco_path = project / "annotations.json"
    coco_path.write_text(
        json.dumps(
            {
                "images": [{"id": 1, "file_name": "a.jpg", "width": 8, "height": 8}],
                "annotations": [],
                "categories": []
            }
        ),
        encoding="utf-8"
    )
    store = ProjectStore(resolve_workspace(project))
    monkeypatch.setattr("app.services.dataset_service.repo", store)
    request = DatasetCreateRequest(
        name="coco",
        coco_json_path=str(coco_path),
        storage=StorageOptions(protocol="file", image_root=str(image_root))
    )
    first = dataset_service.create(request)
    second = dataset_service.create(request)
    assert second.id == first.id
    assert len(store.list_datasets()) == 1

    coco_path.write_text(coco_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    third = dataset_service.create(request)
    assert third.id != first.id
    store.close()


def test_session_round_trip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    store = ProjectStore(resolve_workspace(_project(tmp_path)))
    from app import repositories

    previous = repositories._repo
    repositories.set_repo(store)
    try:
        client = TestClient(app)
        empty = client.get("/api/v1/session")
        assert empty.status_code == 200
        assert empty.json()["dataset_id"] is None
        saved = client.put(
            "/api/v1/session",
            json={
                "dataset_id": "dataset-1",
                "view": {"filters": [], "group_by": "class", "page": 1, "page_size": 20}
            }
        )
        assert saved.status_code == 200
        loaded = client.get("/api/v1/session")
        assert loaded.json()["dataset_id"] == "dataset-1"
        assert loaded.json()["view"]["group_by"] == "class"
    finally:
        repositories.set_repo(previous)
        store.close()
