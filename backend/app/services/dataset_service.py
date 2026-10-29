from __future__ import annotations

from collections.abc import Callable

from app.loaders.registry import loader_registry
from app.models.schemas import DatasetCreateRequest
from app.repositories import repo


class DatasetService:
    def create(
        self,
        request: DatasetCreateRequest,
        progress_callback: Callable[[float, str], None] | None = None
    ):
        loader = loader_registry.resolve(request.coco_json_path)
        options = {
            "protocol": request.storage.protocol,
            "image_root": request.storage.image_root,
            "options": request.storage.options
        }
        if request.storage.protocol == "file":
            finder = getattr(repo, "find_by_source", None)
            if callable(finder):
                existing = finder(request.coco_json_path, request.storage.image_root)
                if existing is not None:
                    if progress_callback:
                        progress_callback(1.0, "Using saved dataset")
                    return existing
        if progress_callback:
            progress_callback(0.01, "Validating COCO dataset")
        validation = loader.validate(request.coco_json_path, options)
        if not validation.valid:
            raise ValueError("; ".join(validation.errors))
        result = loader.load(
            request.coco_json_path,
            options,
            progress_callback=progress_callback
        )
        dataset = repo.create_dataset(
            name=request.name or result.dataset_name,
            source_uri=result.source_uri,
            images=result.images,
            annotations=result.annotations,
            progress_callback=progress_callback
        )
        if request.storage.protocol == "file":
            writer = getattr(repo, "write_fingerprint", None)
            if callable(writer):
                writer(dataset.id, request.coco_json_path, request.storage.image_root)
        return dataset

    def list(self):
        return repo.list_datasets()


dataset_service = DatasetService()
