from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.models.schemas import AnnotationRecord, ImageRecord


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DatasetLoadResult:
    dataset_name: str
    source_uri: str
    images: list[ImageRecord]
    annotations: list[AnnotationRecord]


class DatasetLoader(ABC):
    @abstractmethod
    def can_load(self, source: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def validate(self, source: str, options: dict[str, Any]) -> ValidationResult:
        raise NotImplementedError

    @abstractmethod
    def load(
        self,
        source: str,
        options: dict[str, Any],
        progress_callback: Callable[[float, str], None] | None = None
    ) -> DatasetLoadResult:
        raise NotImplementedError
