from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunningServer:
    pid: int
    host: str
    port: int


@dataclass(frozen=True)
class Workspace:
    project_root: Path | None
    data_root: Path
    user_home: Path


def user_data_home() -> Path:
    configured = os.environ.get("XDG_DATA_HOME")
    if configured:
        return Path(configured).expanduser().resolve() / "datalens"
    return Path.home() / ".local" / "share" / "datalens"


def find_project_root(start: Path) -> Path | None:
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").is_file():
            return candidate
    return None


def resolve_workspace(start: Path | None = None) -> Workspace:
    origin = (start or Path.cwd()).expanduser().resolve()
    project_root = find_project_root(origin)
    home = user_data_home()
    if project_root is None:
        return Workspace(project_root=None, data_root=home, user_home=home)
    return Workspace(project_root=project_root, data_root=project_root / ".datalens", user_home=home)


def store_path(path: Path, project_root: Path | None) -> str:
    if project_root is not None:
        try:
            return path.resolve().relative_to(project_root.resolve()).as_posix()
        except ValueError:
            return str(path.resolve())
    return str(path.resolve())


def store_user_path(value: str, project_root: Path | None) -> str:
    if "://" in value:
        return value
    return store_path(Path(value).expanduser(), project_root)


def load_stored_path(stored: str, project_root: Path | None) -> str:
    if not stored:
        return ""
    if "://" in stored:
        return stored
    path = Path(stored)
    if path.is_absolute() or project_root is None:
        return str(path)
    return str((project_root / path).resolve())


def file_fingerprint(source: str, image_root: str | None, project_root: Path | None) -> dict[str, object] | None:
    if "://" in source:
        return None
    path = Path(source).expanduser()
    if not path.is_file():
        return None
    resolved = path.resolve()
    stat = resolved.stat()
    stored_root = ""
    if image_root:
        stored_root = store_user_path(image_root, project_root)
    return {
        "path": store_path(resolved, project_root),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "image_root": stored_root
    }


def fingerprints_match(saved: dict[str, object], current: dict[str, object], project_root: Path | None) -> bool:
    if int(saved.get("size", -1)) != int(current.get("size", -2)):
        return False
    if int(saved.get("mtime_ns", -1)) != int(current.get("mtime_ns", -2)):
        return False
    saved_path = load_stored_path(str(saved.get("path", "")), project_root)
    current_path = load_stored_path(str(current.get("path", "")), project_root)
    if saved_path != current_path:
        return False
    saved_root = load_stored_path(str(saved.get("image_root", "")), project_root)
    current_root = load_stored_path(str(current.get("image_root", "")), project_root)
    return saved_root == current_root


def remember_workspace(workspace: Workspace) -> None:
    path = workspace.project_root or workspace.data_root
    entry = {
        "path": str(path),
        "name": path.name or "datalens",
        "opened_at": _now_iso()
    }
    recent_path = workspace.user_home / "recent.json"
    recent_path.parent.mkdir(parents=True, exist_ok=True)
    projects: list[dict[str, str]] = []
    if recent_path.is_file():
        try:
            payload = json.loads(recent_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        raw_projects = payload.get("projects", []) if isinstance(payload, dict) else []
        if isinstance(raw_projects, list):
            projects = [item for item in raw_projects if isinstance(item, dict) and item.get("path") != entry["path"]]
    projects.insert(0, entry)
    _write_json(recent_path, {"projects": projects[:20]})


def read_session(data_root: Path) -> dict[str, object]:
    path = data_root / "session.json"
    if not path.is_file():
        return {"dataset_id": None, "view": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"dataset_id": None, "view": None}
    if not isinstance(payload, dict):
        return {"dataset_id": None, "view": None}
    return {"dataset_id": payload.get("dataset_id"), "view": payload.get("view")}


def write_session(data_root: Path, payload: dict[str, object]) -> None:
    data_root.mkdir(parents=True, exist_ok=True)
    _write_json(
        data_root / "session.json",
        {"dataset_id": payload.get("dataset_id"), "view": payload.get("view")}
    )


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_server_lock(data_root: Path) -> RunningServer | None:
    path = data_root / "server.lock"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return RunningServer(pid=int(payload["pid"]), host=str(payload["host"]), port=int(payload["port"]))
    except (KeyError, TypeError, ValueError):
        return None


def read_running_server(data_root: Path) -> RunningServer | None:
    running = read_server_lock(data_root)
    if running is None or not pid_alive(running.pid):
        return None
    return running


def write_server_lock(data_root: Path, pid: int, host: str, port: int) -> None:
    data_root.mkdir(parents=True, exist_ok=True)
    _write_json(data_root / "server.lock", {"pid": pid, "host": host, "port": port})


def clear_server_lock(data_root: Path, pid: int) -> None:
    current = read_server_lock(data_root)
    if current is not None and current.pid == pid:
        lock_path = data_root / "server.lock"
        if lock_path.exists():
            lock_path.unlink()


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(tz=UTC).isoformat()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)
