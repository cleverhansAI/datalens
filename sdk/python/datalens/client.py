from __future__ import annotations

from typing import Any, Self
from urllib.parse import urlparse

import httpx

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _trust_env_for(api_base: str) -> bool:
    host = urlparse(api_base).hostname or ""
    return host not in _LOOPBACK_HOSTS


class DataLensClient:
    def __init__(self, api_base: str | None = None, timeout: int = 60) -> None:
        self.timeout = timeout
        self._store = None
        if api_base:
            self.api_base = api_base.rstrip("/")
            self._mode = "http"
            return
        from app.core.workspace import read_running_server, resolve_workspace

        running = read_running_server(resolve_workspace().data_root)
        if running is not None:
            self.api_base = f"http://{running.host}:{running.port}/api/v1"
            self._mode = "http"
            return
        self.api_base = ""
        self._mode = "local"

    def close(self) -> None:
        if self._store is not None:
            self._store.close()
            self._store = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, trust_env=_trust_env_for(self.api_base))

    def _get(self, path: str) -> Any:
        with self._client() as client:
            response = client.get(f"{self.api_base}{path}")
            response.raise_for_status()
            return response.json()

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        with self._client() as client:
            response = client.post(f"{self.api_base}{path}", json=payload)
            response.raise_for_status()
            return response.json()

    def _ensure_local(self):
        if self._store is None:
            from app.core.workspace import resolve_workspace
            from app.repositories import set_repo
            from app.repositories.project_store import ProjectStore

            self._store = ProjectStore(resolve_workspace())
            set_repo(self._store)
        return self._store

    def list_datasets(self) -> list[dict[str, Any]]:
        if self._mode == "local":
            self._ensure_local()
            from app.services.dataset_service import dataset_service

            return [item.model_dump(mode="json") for item in dataset_service.list()]
        return self._get("/datasets")

    def create_dataset(
        self,
        name: str,
        coco_json_path: str,
        image_root: str | None = None,
        protocol: str = "file"
    ) -> dict[str, Any]:
        payload = {
            "name": name,
            "coco_json_path": coco_json_path,
            "storage": {"protocol": protocol, "image_root": image_root, "options": {}}
        }
        if self._mode == "local":
            self._ensure_local()
            from app.models.schemas import DatasetCreateRequest
            from app.services.dataset_service import dataset_service

            dataset = dataset_service.create(DatasetCreateRequest.model_validate(payload))
            return dataset.model_dump(mode="json")
        return self._post("/datasets", payload)

    def create_dataset_async(
        self,
        name: str,
        coco_json_path: str,
        image_root: str | None = None,
        protocol: str = "file"
    ) -> dict[str, Any]:
        payload = {
            "name": name,
            "coco_json_path": coco_json_path,
            "storage": {"protocol": protocol, "image_root": image_root, "options": {}}
        }
        if self._mode == "local":
            self._ensure_local()
            from app.models.schemas import DatasetCreateRequest
            from app.services.dataset_service import dataset_service
            from app.services.task_service import task_service

            request = DatasetCreateRequest.model_validate(payload)
            task = task_service.create_task(
                lambda progress_callback: dataset_service.create(
                    request,
                    progress_callback=progress_callback
                ).model_dump(mode="json")
            )
            return task.model_dump(mode="json")
        return self._post("/datasets/async", payload)

    def get_task(self, task_id: str) -> dict[str, Any]:
        if self._mode == "local":
            self._ensure_local()
            from app.services.task_service import task_service

            return task_service.get_task(task_id).model_dump(mode="json")
        return self._get(f"/tasks/{task_id}")

    def query_view(self, dataset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._mode == "local":
            self._ensure_local()
            from app.models.schemas import ViewQueryRequest, ViewSpec
            from app.services.view_service import view_service

            if any(key in payload for key in ("filters", "group_by", "page", "page_size")):
                spec = ViewSpec.model_validate(payload)
                saved_view_id = None
            else:
                parsed = ViewQueryRequest.model_validate(payload)
                spec = parsed.spec
                saved_view_id = parsed.saved_view_id
            return view_service.query(dataset_id, spec, saved_view_id=saved_view_id).model_dump(mode="json")
        return self._post(f"/views/{dataset_id}/query", payload)

    def run_embeddings(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._mode == "local":
            self._ensure_local()
            from app.models.schemas import EmbeddingRunRequest
            from app.services.embedding_service import embedding_service

            run = embedding_service.run(EmbeddingRunRequest.model_validate(payload))
            return run.model_dump(mode="json")
        return self._post("/embeddings/run", payload)

    def export_coco(self, dataset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._mode == "local":
            self._ensure_local()
            from app.models.schemas import ExportViewRequest, ViewSpec
            from app.services.export_service import export_service

            if any(key in payload for key in ("filters", "group_by", "page", "page_size")):
                spec = ViewSpec.model_validate(payload)
                saved_view_id = None
            else:
                parsed = ExportViewRequest.model_validate(payload)
                spec = parsed.view
                saved_view_id = parsed.saved_view_id
            path = export_service.export_view_to_coco(dataset_id, spec, saved_view_id=saved_view_id)
            return {"path": path}
        return self._post(f"/exports/{dataset_id}/coco", payload)
