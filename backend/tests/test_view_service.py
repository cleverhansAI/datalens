from datetime import UTC, datetime

from app.models.schemas import (
    AnnotationRecord,
    Dataset,
    FilterClause,
    ImageRecord,
    SavedView,
    ViewSpec,
)
from app.repositories import DatasetBundle
from app.services import view_service as view_service_module
from app.services.view_service import ViewService


def test_image_id_filter_limits_images() -> None:
    service = ViewService()
    images = [
        ImageRecord(id=1, file_path="/a.jpg", directory_name="a", width=10, height=10, aspect_ratio=1.0),
        ImageRecord(id=2, file_path="/b.jpg", directory_name="a", width=10, height=10, aspect_ratio=1.0)
    ]
    filtered = service._filter_images(images, [FilterClause(field="id", operator="in", value=[2])])
    assert [image.id for image in filtered] == [2]


def test_group_by_directory() -> None:
    service = ViewService()
    bundle = DatasetBundle(
        dataset=Dataset(
            id="d1",
            name="demo",
            source_uri="source.json",
            created_at=datetime.now(tz=UTC),
            image_count=2,
            annotation_count=2
        ),
        images=[
            ImageRecord(id=1, file_path="/a/x.jpg", directory_name="a", width=100, height=50, aspect_ratio=2.0),
            ImageRecord(id=2, file_path="/b/y.jpg", directory_name="b", width=100, height=100, aspect_ratio=1.0)
        ],
        annotations=[
            AnnotationRecord(
                id=1,
                image_id=1,
                class_id=1,
                class_name="car",
                bbox_xywh=(0, 0, 10, 10),
                area=100,
                aspect_ratio=1.0
            ),
            AnnotationRecord(
                id=2,
                image_id=2,
                class_id=2,
                class_name="person",
                bbox_xywh=(0, 0, 10, 10),
                area=100,
                aspect_ratio=1.0
            )
        ]
    )
    groups = service._group_counts(bundle, bundle.images, bundle.annotations, "directory")
    assert len(groups) == 2
    assert {g.key for g in groups} == {"a", "b"}


def test_no_filters_returns_all_annotations() -> None:
    service = ViewService()
    anns = [
        AnnotationRecord(
            id=1,
            image_id=1,
            class_id=1,
            class_name="car",
            bbox_xywh=(0, 0, 10, 10),
            area=100,
            aspect_ratio=1.0
        )
    ]
    filtered = service._filter_annotations(anns, ViewSpec().filters)
    assert len(filtered) == 1


def test_bbox_dimension_filters() -> None:
    service = ViewService()
    anns = [
        AnnotationRecord(
            id=1,
            image_id=1,
            class_id=1,
            class_name="car",
            bbox_xywh=(0, 0, 24, 12),
            area=288,
            aspect_ratio=2.0
        ),
        AnnotationRecord(
            id=2,
            image_id=1,
            class_id=2,
            class_name="person",
            bbox_xywh=(0, 0, 60, 80),
            area=4800,
            aspect_ratio=0.75
        )
    ]

    filtered = service._filter_annotations(
        anns,
        [
            FilterClause(field="bbox_width", operator="gte", value=30),
            FilterClause(field="bbox_height", operator="lte", value=90)
        ]
    )

    assert [ann.id for ann in filtered] == [2]


def test_query_preserves_full_view_metadata_when_paginated() -> None:
    service = ViewService()
    bundle = DatasetBundle(
        dataset=Dataset(
            id="d1",
            name="demo",
            source_uri="source.json",
            created_at=datetime.now(tz=UTC),
            image_count=3,
            annotation_count=3
        ),
        images=[
            ImageRecord(id=1, file_path="/a/x.jpg", directory_name="a", width=100, height=50, aspect_ratio=2.0),
            ImageRecord(id=2, file_path="/b/y.jpg", directory_name="b", width=100, height=100, aspect_ratio=1.0),
            ImageRecord(id=3, file_path="/b/z.jpg", directory_name="b", width=120, height=80, aspect_ratio=1.5)
        ],
        annotations=[
            AnnotationRecord(
                id=1,
                image_id=1,
                class_id=1,
                class_name="car",
                bbox_xywh=(0, 0, 10, 10),
                area=100,
                aspect_ratio=1.0
            ),
            AnnotationRecord(
                id=2,
                image_id=2,
                class_id=2,
                class_name="person",
                bbox_xywh=(0, 0, 10, 10),
                area=100,
                aspect_ratio=1.0
            ),
            AnnotationRecord(
                id=3,
                image_id=3,
                class_id=1,
                class_name="car",
                bbox_xywh=(0, 0, 8, 12),
                area=96,
                aspect_ratio=0.67
            )
        ]
    )

    service.resolve = lambda dataset_id, spec: service._build_full_view(bundle, spec)  # type: ignore[method-assign]
    result = service.query("d1", ViewSpec(group_by="class", page=1, page_size=1))

    assert result.total == 3
    assert result.total_annotations == 3
    assert result.class_distribution == {"car": 2, "person": 1}
    assert [(group.key, group.count) for group in result.groups] == [("car", 2), ("person", 1)]
    assert len(result.images) == 1
    assert len(result.annotations) == 1


def test_query_can_resolve_saved_view(monkeypatch) -> None:
    service = ViewService()
    bundle = DatasetBundle(
        dataset=Dataset(
            id="d1",
            name="demo",
            source_uri="source.json",
            created_at=datetime.now(tz=UTC),
            image_count=2,
            annotation_count=2
        ),
        images=[
            ImageRecord(id=1, file_path="/a/x.jpg", directory_name="a", width=100, height=50, aspect_ratio=2.0),
            ImageRecord(id=2, file_path="/b/y.jpg", directory_name="b", width=100, height=100, aspect_ratio=1.0)
        ],
        annotations=[
            AnnotationRecord(
                id=1,
                image_id=1,
                class_id=1,
                class_name="car",
                bbox_xywh=(0, 0, 10, 10),
                area=100,
                aspect_ratio=1.0
            ),
            AnnotationRecord(
                id=2,
                image_id=2,
                class_id=2,
                class_name="person",
                bbox_xywh=(0, 0, 10, 10),
                area=100,
                aspect_ratio=1.0
            )
        ]
    )
    saved_view = SavedView(
        id="saved-1",
        dataset_id="d1",
        name="cars",
        description="only cars",
        spec=ViewSpec(filters=[FilterClause(field="class", operator="eq", value="car")], page=1, page_size=10),
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC)
    )

    monkeypatch.setattr(view_service_module.repo, "get_saved_view", lambda saved_view_id: saved_view)
    monkeypatch.setattr(view_service_module.repo, "get_dataset_bundle", lambda dataset_id: bundle)

    result = service.query("d1", saved_view_id="saved-1")

    assert result.total == 1
    assert result.images[0].id == 1
    assert result.annotations[0].class_name == "car"


def test_directory_filter_limits_images_and_annotations() -> None:
    service = ViewService()
    bundle = DatasetBundle(
        dataset=Dataset(
            id="d1",
            name="demo",
            source_uri="source.json",
            created_at=datetime.now(tz=UTC),
            image_count=3,
            annotation_count=3
        ),
        images=[
            ImageRecord(id=1, file_path="/a/x.jpg", directory_name="a", width=100, height=50, aspect_ratio=2.0),
            ImageRecord(id=2, file_path="/b/y.jpg", directory_name="b", width=100, height=100, aspect_ratio=1.0),
            ImageRecord(id=3, file_path="/b/z.jpg", directory_name="b", width=120, height=80, aspect_ratio=1.5)
        ],
        annotations=[
            AnnotationRecord(
                id=1,
                image_id=1,
                class_id=1,
                class_name="car",
                bbox_xywh=(0, 0, 10, 10),
                area=100,
                aspect_ratio=1.0
            ),
            AnnotationRecord(
                id=2,
                image_id=2,
                class_id=2,
                class_name="person",
                bbox_xywh=(0, 0, 10, 10),
                area=100,
                aspect_ratio=1.0
            ),
            AnnotationRecord(
                id=3,
                image_id=3,
                class_id=1,
                class_name="car",
                bbox_xywh=(0, 0, 8, 12),
                area=96,
                aspect_ratio=0.67
            )
        ]
    )

    result = service._build_full_view(
        bundle,
        ViewSpec(filters=[FilterClause(field="directory", operator="eq", value="b")], page=1, page_size=10)
    )

    assert {image.id for image in result.images} == {2, 3}
    assert {annotation.id for annotation in result.annotations} == {2, 3}
