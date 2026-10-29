from app.loaders.base import DatasetLoader
from app.loaders.coco_loader import CocoDatasetLoader


class LoaderRegistry:
    def __init__(self) -> None:
        self._loaders: list[DatasetLoader] = [CocoDatasetLoader()]

    def resolve(self, source: str) -> DatasetLoader:
        for loader in self._loaders:
            if loader.can_load(source):
                return loader
        raise ValueError(f"No loader can handle source: {source}")


loader_registry = LoaderRegistry()
