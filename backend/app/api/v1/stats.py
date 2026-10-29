from fastapi import APIRouter, HTTPException

from app.services.stats_service import stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/{dataset_id}/images")
def image_stats(dataset_id: str):
    try:
        return stats_service.image_stats(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{dataset_id}/objects")
def object_stats(dataset_id: str):
    try:
        return stats_service.object_stats(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
