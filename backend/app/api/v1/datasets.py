from fastapi import APIRouter, HTTPException

from app.models.schemas import DatasetCreateRequest
from app.services.dataset_service import dataset_service
from app.services.task_service import task_service

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("")
def create_dataset(request: DatasetCreateRequest):
    try:
        dataset = dataset_service.create(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return dataset


@router.post("/async")
def create_dataset_async(request: DatasetCreateRequest):
    try:
        task = task_service.create_task(
            lambda progress_callback: dataset_service.create(
                request,
                progress_callback=progress_callback
            ).model_dump(mode="json")
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return task


@router.get("")
def list_datasets():
    return dataset_service.list()
