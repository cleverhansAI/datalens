from typing import Any

from fastapi import APIRouter, HTTPException

from app.models.schemas import SavedViewCreateRequest, SavedViewUpdateRequest, ViewQueryRequest, ViewSpec
from app.services.view_service import view_service

router = APIRouter(prefix="/views", tags=["views"])


@router.post("/{dataset_id}/query")
def query_view(dataset_id: str, request: dict[str, Any]):
    if "filters" in request or "group_by" in request or "page" in request or "page_size" in request:
        spec = ViewSpec.model_validate(request)
        saved_view_id = None
    else:
        parsed = ViewQueryRequest.model_validate(request)
        spec = parsed.spec
        saved_view_id = parsed.saved_view_id
    try:
        return view_service.query(dataset_id, spec, saved_view_id=saved_view_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{dataset_id}/saved")
def list_saved_views(dataset_id: str):
    try:
        return view_service.list_saved_views(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{dataset_id}/saved")
def create_saved_view(dataset_id: str, request: SavedViewCreateRequest):
    try:
        return view_service.create_saved_view(dataset_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/saved/{view_id}")
def get_saved_view(view_id: str):
    try:
        return view_service.get_saved_view(view_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/saved/{view_id}")
def update_saved_view(view_id: str, request: SavedViewUpdateRequest):
    try:
        return view_service.update_saved_view(view_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/saved/{view_id}")
def delete_saved_view(view_id: str):
    try:
        view_service.delete_saved_view(view_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}
