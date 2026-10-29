from fastapi import APIRouter, HTTPException

from app.models.schemas import EmbeddingRunRequest
from app.services.embedding_service import embedding_service
from app.services.task_service import task_service

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


@router.post("/run")
def run_embeddings(request: EmbeddingRunRequest):
    try:
        return embedding_service.run(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/run_async")
def run_embeddings_async(request: EmbeddingRunRequest):
    try:
        task = task_service.create_task(
            lambda progress_callback: embedding_service.run(
                request,
                progress_callback=progress_callback
            ).model_dump(mode="json")
        )
        return task
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{dataset_id}/runs")
def list_embedding_runs(dataset_id: str):
    return embedding_service.list_runs(dataset_id)


@router.get("/projection/{run_id}")
def get_embedding_projection(run_id: str):
    try:
        return embedding_service.get_projection(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
