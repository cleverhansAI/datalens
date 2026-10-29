from __future__ import annotations

import os
import socket
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn
from app.core.assets import bundled_ui_dir
from app.core.workspace import (
    clear_server_lock,
    read_running_server,
    remember_workspace,
    resolve_workspace,
    write_server_lock,
    write_session,
)
from app.repositories import set_repo
from app.repositories.project_store import ProjectStore

HOST = "127.0.0.1"


def serve(
    *,
    coco_json: str | None = None,
    image_root: str | None = None,
    dataset_name: str | None = None,
    port: int | None = None,
    idle_timeout_minutes: int = 30,
    open_browser: bool = True
) -> None:
    workspace = resolve_workspace()
    running = read_running_server(workspace.data_root)
    if running is not None:
        url = f"http://{running.host}:{running.port}"
        if coco_json:
            _import_on_running_server(
                url,
                coco_json=coco_json,
                image_root=image_root,
                dataset_name=dataset_name
            )
        print(f"DataLens is already running at {url}", flush=True)
        if open_browser:
            _open_browser(url)
        return

    store = ProjectStore(workspace)
    set_repo(store)
    try:
        if coco_json:
            dataset = _import_dataset(coco_json, image_root, dataset_name)
            write_session(workspace.data_root, {"dataset_id": dataset.id, "view": None})
        remember_workspace(workspace)
        selected_port = port if port is not None else _free_port()
        write_server_lock(workspace.data_root, os.getpid(), HOST, selected_port)
        _run_until_stopped(
            workspace_data=workspace.data_root,
            port=selected_port,
            idle_timeout_minutes=idle_timeout_minutes,
            open_browser=open_browser
        )
    finally:
        clear_server_lock(workspace.data_root, os.getpid())
        store.close()


def _import_dataset(coco_json: str, image_root: str | None, dataset_name: str | None):
    from app.models.schemas import DatasetCreateRequest, StorageOptions
    from app.services.dataset_service import dataset_service

    source = str(Path(coco_json).expanduser().resolve())
    root = str(Path(image_root).expanduser().resolve()) if image_root else None
    name = dataset_name or Path(source).stem
    try:
        return dataset_service.create(
            DatasetCreateRequest(
                name=name,
                coco_json_path=source,
                storage=StorageOptions(protocol="file", image_root=root)
            )
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def _import_on_running_server(
    url: str,
    *,
    coco_json: str,
    image_root: str | None,
    dataset_name: str | None
) -> None:
    import httpx

    from datalens.client import DataLensClient

    source = str(Path(coco_json).expanduser().resolve())
    root = str(Path(image_root).expanduser().resolve()) if image_root else None
    name = dataset_name or Path(source).stem
    client = DataLensClient(api_base=f"{url}/api/v1")
    dataset = client.create_dataset(name=name, coco_json_path=source, image_root=root)
    with httpx.Client(timeout=30, trust_env=False) as http:
        response = http.put(
            f"{url}/api/v1/session",
            json={"dataset_id": dataset["id"], "view": None}
        )
        response.raise_for_status()


def _run_until_stopped(
    *,
    workspace_data: Path,
    port: int,
    idle_timeout_minutes: int,
    open_browser: bool
) -> None:
    from app.main import app

    url = f"http://{HOST}:{port}"
    timeout_seconds = max(idle_timeout_minutes, 0) * 60
    app.state.last_activity = time.monotonic()
    config = uvicorn.Config(app, host=HOST, port=port, log_level="info")
    server = uvicorn.Server(config)
    if timeout_seconds > 0:
        threading.Thread(
            target=_watch_idle,
            args=(server, timeout_seconds),
            daemon=True
        ).start()
    ui_dir = bundled_ui_dir()
    print(f"DataLens is running at {url}", flush=True)
    print(f"Project data: {workspace_data}", flush=True)
    if timeout_seconds > 0:
        print(f"Idle timeout: {idle_timeout_minutes} minutes. Press Ctrl+C to stop.", flush=True)
    else:
        print("Idle timeout is disabled. Press Ctrl+C to stop.", flush=True)
    if ui_dir is None:
        print("The web UI is not bundled, so only the API is available.", flush=True)
    elif open_browser:
        threading.Thread(target=_open_when_ready, args=(server, url), daemon=True).start()
    try:
        server.run()
    finally:
        clear_server_lock(workspace_data, os.getpid())


def _watch_idle(server: uvicorn.Server, timeout_seconds: int) -> None:
    from app.main import app

    while not server.should_exit:
        time.sleep(2)
        last_activity = getattr(app.state, "last_activity", time.monotonic())
        if time.monotonic() - last_activity >= timeout_seconds:
            print("DataLens idle timeout reached. Saving and stopping.", flush=True)
            server.should_exit = True
            return


def _open_when_ready(server: uvicorn.Server, url: str) -> None:
    deadline = time.time() + 30
    while time.time() < deadline and not server.should_exit:
        if _is_healthy(f"{url}/health"):
            _open_browser(url)
            return
        time.sleep(0.2)


def _open_browser(url: str) -> None:
    try:
        webbrowser.open(url)
    except webbrowser.Error:
        print(f"Open {url} in a browser.")


def _is_healthy(url: str) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=0.5) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])
