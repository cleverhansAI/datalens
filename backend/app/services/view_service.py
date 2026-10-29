from __future__ import annotations

from collections import Counter, defaultdict

from app.core.config import settings
from app.models.schemas import (
    AnnotationRecord,
    FilterClause,
    GroupCount,
    ImageRecord,
    SavedView,
    SavedViewCreateRequest,
    SavedViewUpdateRequest,
    ViewResult,
    ViewSpec,
)
from app.repositories import DatasetBundle, repo


class ViewService:
    def list_saved_views(self, dataset_id: str) -> list[SavedView]:
        repo.get_dataset_bundle(dataset_id)
        return repo.list_saved_views(dataset_id)

    def create_saved_view(self, dataset_id: str, request: SavedViewCreateRequest) -> SavedView:
        repo.get_dataset_bundle(dataset_id)
        return repo.create_saved_view(
            dataset_id=dataset_id,
            name=request.name,
            description=request.description,
            spec=request.spec
        )

    def get_saved_view(self, saved_view_id: str) -> SavedView:
        return repo.get_saved_view(saved_view_id)

    def update_saved_view(self, saved_view_id: str, request: SavedViewUpdateRequest) -> SavedView:
        return repo.update_saved_view(
            saved_view_id,
            name=request.name,
            description=request.description,
            spec=request.spec
        )

    def delete_saved_view(self, saved_view_id: str) -> None:
        repo.delete_saved_view(saved_view_id)

    def resolve_spec(
        self,
        dataset_id: str,
        *,
        view_spec: ViewSpec | None = None,
        saved_view_id: str | None = None
    ) -> ViewSpec:
        if saved_view_id is None:
            return view_spec.model_copy(deep=True) if view_spec is not None else ViewSpec()

        saved_view = repo.get_saved_view(saved_view_id)
        if saved_view.dataset_id != dataset_id:
            raise KeyError(f"Saved view {saved_view_id} does not belong to dataset {dataset_id}")

        resolved_spec = saved_view.spec.model_copy(deep=True)
        if view_spec is not None:
            resolved_spec = resolved_spec.model_copy(
                update={
                    "page": view_spec.page,
                    "page_size": view_spec.page_size
                }
            )
        return resolved_spec

    def resolve(
        self,
        dataset_id: str,
        spec: ViewSpec | None = None,
        *,
        saved_view_id: str | None = None
    ) -> ViewResult:
        resolved_spec = self.resolve_spec(dataset_id, view_spec=spec, saved_view_id=saved_view_id)
        bundle = repo.get_dataset_bundle(dataset_id)
        return self._build_full_view(bundle, resolved_spec)

    def query(
        self,
        dataset_id: str,
        spec: ViewSpec | None = None,
        *,
        saved_view_id: str | None = None
    ) -> ViewResult:
        resolved_spec = self.resolve_spec(dataset_id, view_spec=spec, saved_view_id=saved_view_id)
        resolved_view = self.resolve(dataset_id, resolved_spec)
        page_size = max(1, min(resolved_spec.page_size, settings.max_page_size))
        page_start = max(resolved_spec.page - 1, 0) * page_size
        page_end = page_start + page_size
        page_images = resolved_view.images[page_start:page_end]
        page_image_ids = {img.id for img in page_images}
        page_annotations = [ann for ann in resolved_view.annotations if ann.image_id in page_image_ids]
        return ViewResult(
            total=resolved_view.total,
            total_annotations=resolved_view.total_annotations,
            class_distribution=resolved_view.class_distribution,
            groups=resolved_view.groups,
            avg_width=resolved_view.avg_width,
            avg_height=resolved_view.avg_height,
            avg_aspect_ratio=resolved_view.avg_aspect_ratio,
            images=page_images,
            annotations=page_annotations
        )

    def _build_full_view(self, bundle: DatasetBundle, spec: ViewSpec) -> ViewResult:
        image_by_id = {img.id: img for img in bundle.images}
        image_filters = self._image_filters(spec.filters)
        annotation_filters = self._annotation_filters(spec.filters)

        filtered_images = self._filter_images(bundle.images, image_filters)
        filtered_image_ids = {img.id for img in filtered_images}

        if annotation_filters:
            annotations = [
                ann for ann in self._filter_annotations(bundle.annotations, annotation_filters) if ann.image_id in filtered_image_ids
            ]
            image_ids = {ann.image_id for ann in annotations}
        else:
            image_ids = filtered_image_ids
            annotations = [ann for ann in bundle.annotations if ann.image_id in image_ids]

        images = [image_by_id[i] for i in image_ids if i in image_by_id]
        images = self._sort_images(images, spec.sort_by, spec.sort_desc)
        groups = self._group_counts(bundle, images, annotations, spec.group_by)
        class_distribution = dict(
            sorted(Counter(ann.class_name for ann in annotations).items(), key=lambda item: (-item[1], item[0]))
        )
        image_count = len(images)
        if image_count:
            avg_width = sum(image.width for image in images) / image_count
            avg_height = sum(image.height for image in images) / image_count
            avg_aspect_ratio = sum(image.aspect_ratio for image in images) / image_count
        else:
            avg_width = 0.0
            avg_height = 0.0
            avg_aspect_ratio = 0.0
        return ViewResult(
            total=image_count,
            total_annotations=len(annotations),
            class_distribution=class_distribution,
            groups=groups,
            avg_width=avg_width,
            avg_height=avg_height,
            avg_aspect_ratio=avg_aspect_ratio,
            images=images,
            annotations=annotations
        )

    def _filter_images(self, images: list[ImageRecord], filters: list[FilterClause]) -> list[ImageRecord]:
        filtered = images
        for clause in filters:
            if clause.field == "directory":
                filtered = [img for img in filtered if self._matches(img.directory_name, clause)]
            elif clause.field == "id":
                filtered = [img for img in filtered if self._matches(img.id, clause)]
        return filtered

    def _filter_annotations(self, annotations: list[AnnotationRecord], filters: list[FilterClause]) -> list[AnnotationRecord]:
        filtered = annotations
        for clause in filters:
            if clause.field == "class":
                filtered = [ann for ann in filtered if self._matches(ann.class_name, clause)]
            elif clause.field == "area":
                filtered = [ann for ann in filtered if self._matches(ann.area, clause)]
            elif clause.field == "bbox_width":
                filtered = [ann for ann in filtered if self._matches(ann.bbox_xywh[2], clause)]
            elif clause.field == "bbox_height":
                filtered = [ann for ann in filtered if self._matches(ann.bbox_xywh[3], clause)]
        return filtered

    def _image_filters(self, filters: list[FilterClause]) -> list[FilterClause]:
        return [clause for clause in filters if clause.field in {"directory", "id"}]

    def _annotation_filters(self, filters: list[FilterClause]) -> list[FilterClause]:
        return [clause for clause in filters if clause.field != "directory"]

    def _matches(self, value, clause: FilterClause) -> bool:
        if clause.operator == "eq":
            return value == clause.value
        if clause.operator == "neq":
            return value != clause.value
        if clause.operator == "in":
            return value in clause.value
        if clause.operator == "gte":
            return value >= clause.value
        if clause.operator == "lte":
            return value <= clause.value
        if clause.operator == "contains":
            return str(clause.value).lower() in str(value).lower()
        return True

    def _sort_images(self, images, sort_by: str | None, sort_desc: bool):
        if sort_by is None:
            return images
        try:
            return sorted(images, key=lambda img: getattr(img, sort_by), reverse=sort_desc)
        except AttributeError:
            return images

    def _group_counts(
        self,
        bundle: DatasetBundle,
        images,
        annotations: list[AnnotationRecord],
        group_by: str | None
    ) -> list[GroupCount]:
        if group_by == "directory":
            counter = Counter(img.directory_name for img in images)
            return [GroupCount(key=k, count=v) for k, v in sorted(counter.items())]
        if group_by == "class":
            counter = Counter(ann.class_name for ann in annotations)
            return [GroupCount(key=k, count=v) for k, v in sorted(counter.items())]
        if group_by == "image_size_bucket":
            buckets = defaultdict(int)
            for img in images:
                area = img.width * img.height
                if area < 512 * 512:
                    key = "small"
                elif area < 1280 * 720:
                    key = "medium"
                else:
                    key = "large"
                buckets[key] += 1
            return [GroupCount(key=k, count=v) for k, v in sorted(buckets.items())]
        return []


view_service = ViewService()
