from typing import Any

from fastapi import APIRouter, HTTPException

from app.models.schemas import ExportViewRequest, ViewSpec
from app.services.export_service import export_service

router = APIRouter(prefix="/exports", tags=["exports"])


@router.post("/{dataset_id}/coco")
def export_coco(dataset_id: str, request: dict[str, Any]):
    if "filters" in request or "group_by" in request or "page" in request or "page_size" in request:
        spec = ViewSpec.model_validate(request)
        saved_view_id = None
    else:
        parsed = ExportViewRequest.model_validate(request)
        spec = parsed.view
        saved_view_id = parsed.saved_view_id
    try:
        path = export_service.export_view_to_coco(dataset_id, spec, saved_view_id=saved_view_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"path": path}
