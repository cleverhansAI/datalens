from __future__ import annotations

import os
import threading

from app.repositories.duckdb_repo import DatasetBundle, DuckDBRepository

__all__ = ["DatasetBundle", "close_repo", "get_repo", "repo", "set_repo"]

_repo: DuckDBRepository | object | None = None
_lock = threading.Lock()


def get_repo():
    global _repo
    if _repo is None:
        with _lock:
            if _repo is None:
                _repo = _open_default()
    return _repo


def set_repo(repository) -> None:
    global _repo
    _repo = repository


def close_repo() -> None:
    active = _repo
    if active is not None and hasattr(active, "close"):
        active.close()


def _open_default():
    configured = os.environ.get("DATALENS_METADATA_DB_URL")
    if configured:
        return DuckDBRepository(configured)
    from app.core.workspace import resolve_workspace
    from app.repositories.project_store import ProjectStore

    return ProjectStore(resolve_workspace())


class _RepoProxy:
    def __getattr__(self, name: str):
        return getattr(get_repo(), name)


repo = _RepoProxy()
