from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import fsspec


class StorageAdapter:
    def __init__(self, protocol: str = "file", options: dict[str, Any] | None = None) -> None:
        self.protocol = protocol
        self.options = options or {}
        self.fs = fsspec.filesystem(protocol, **self.options)

    def exists(self, path: str) -> bool:
        return self.fs.exists(path)

    def open(self, path: str, mode: str = "rb"):
        return self.fs.open(path, mode)

    def join(self, root: str | None, rel_path: str) -> str:
        if rel_path.startswith("s3://") or rel_path.startswith("file://"):
            return rel_path
        if root is None:
            return rel_path
        parsed = urlparse(root)
        if parsed.scheme in {"s3", "file"}:
            return f"{root.rstrip('/')}/{rel_path.lstrip('/')}"
        return str(Path(root) / rel_path)

    @staticmethod
    def last_directory_name(path: str) -> str:
        clean = path.replace("\\", "/")
        parent = os.path.dirname(clean)
        if parent == "":
            return "root"
        return parent.rstrip("/").split("/")[-1]
