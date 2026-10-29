from fastapi import APIRouter, HTTPException

from app.services.duplicate_service import duplicate_service

router = APIRouter(prefix="/duplicates", tags=["duplicates"])


@router.get("/{dataset_id}/visual")
def visual_duplicates(dataset_id: str):
    try:
        return duplicate_service.find_visual_duplicates(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{dataset_id}/embedding")
def embedding_duplicates(dataset_id: str, threshold: float = 0.98):
    try:
        return duplicate_service.find_embedding_duplicates(dataset_id, threshold=threshold)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
