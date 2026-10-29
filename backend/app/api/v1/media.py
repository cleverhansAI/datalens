from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="/media", tags=["media"])


def _resolve_local_path(raw_path: str) -> Path:
    decoded = unquote(raw_path)
    if decoded.startswith("file://"):
        parsed = urlparse(decoded)
        if parsed.scheme != "file":
            raise HTTPException(status_code=400, detail="Only local file paths are supported.")
        path = Path(parsed.path)
    elif "://" in decoded:
        raise HTTPException(status_code=400, detail="Only local file paths are supported.")
    else:
        path = Path(decoded)
    return path.expanduser().resolve()


@router.get("/image")
def get_image(path: str = Query(..., description="Absolute local image path")):
    local_path = _resolve_local_path(path)
    if not local_path.exists() or not local_path.is_file():
        raise HTTPException(status_code=404, detail=f"Image not found: {local_path}")
    media_type, _ = mimetypes.guess_type(str(local_path))
    return FileResponse(str(local_path), media_type=media_type or "application/octet-stream")
