from __future__ import annotations

import threading
from collections.abc import Callable
from copy import deepcopy
from uuid import uuid4

from app.models.schemas import TaskStatus


class TaskService:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskStatus] = {}
        self._lock = threading.Lock()

    def create_task(self, job: Callable[[Callable[[float, str], None]], dict]) -> TaskStatus:
        task_id = str(uuid4())
        status = TaskStatus(task_id=task_id, state="queued", progress=0.0, message="Queued")
        with self._lock:
            self._tasks[task_id] = status

        def runner() -> None:
            self._set_status(task_id, state="running", progress=0.0, message="Starting")
            try:
                result = job(
                    lambda progress, message, completed=None, total=None: self.update_progress(
                        task_id,
                        progress,
                        message,
                        completed=completed,
                        total=total
                    )
                )
                self._set_status(task_id, state="done", progress=1.0, message="Completed", result=result)
            except Exception as exc:
                self._set_status(task_id, state="failed", progress=1.0, message=str(exc))

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        return status

    def get_task(self, task_id: str) -> TaskStatus:
        with self._lock:
            return deepcopy(self._tasks[task_id])

    def update_progress(
        self,
        task_id: str,
        progress: float,
        message: str,
        completed: int | None = None,
        total: int | None = None
    ) -> None:
        bounded_progress = max(0.0, min(progress, 1.0))
        self._set_status(
            task_id,
            progress=bounded_progress,
            message=message,
            state="running",
            completed=completed,
            total=total
        )

    def _set_status(
        self,
        task_id: str,
        *,
        state: str | None = None,
        progress: float | None = None,
        message: str | None = None,
        result: dict | None = None,
        completed: int | None = None,
        total: int | None = None
    ) -> None:
        with self._lock:
            current = self._tasks[task_id]
            update: dict[str, object] = {
                "state": state if state is not None else current.state,
                "progress": progress if progress is not None else current.progress,
                "message": message if message is not None else current.message,
                "result": result if result is not None else current.result
            }
            if completed is not None:
                update["completed"] = completed
            if total is not None:
                update["total"] = total
            self._tasks[task_id] = current.model_copy(update=update)


task_service = TaskService()
