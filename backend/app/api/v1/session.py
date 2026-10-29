from pathlib import Path

from fastapi import APIRouter
from pydantic import ValidationError

from app.core.config import settings
from app.core.workspace import read_session, write_session
from app.models.schemas import SessionState
from app.repositories import get_repo

router = APIRouter(prefix="/session", tags=["session"])


def _data_root() -> Path:
    active = get_repo()
    root = getattr(active, "data_root", None)
    if isinstance(root, Path):
        return root
    return Path(settings.data_dir)


@router.get("")
def get_session() -> dict:
    payload = read_session(_data_root())
    try:
        return SessionState.model_validate(payload).model_dump(mode="json")
    except ValidationError:
        return SessionState().model_dump(mode="json")


@router.put("")
def put_session(request: SessionState) -> SessionState:
    write_session(_data_root(), request.model_dump(mode="json"))
    return request
