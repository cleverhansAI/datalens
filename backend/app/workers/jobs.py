from __future__ import annotations

from dataclasses import dataclass


@dataclass
class JobResult:
    task_id: str
    success: bool
    message: str


def run_job(task_id: str) -> JobResult:
    return JobResult(task_id=task_id, success=True, message="Executed inline job runner")
