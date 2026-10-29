from __future__ import annotations

from pathlib import Path


def bundled_ui_dir() -> Path | None:
    candidates: list[Path] = []
    try:
        import datalens

        candidates.append(Path(datalens.__file__).resolve().parent / "ui")
    except ImportError:
        pass
    candidates.append(Path(__file__).resolve().parents[3] / "frontend" / "out")
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None
