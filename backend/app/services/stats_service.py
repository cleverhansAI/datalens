from __future__ import annotations

from collections import Counter

from app.repositories import repo


class StatsService:
    def image_stats(self, dataset_id: str) -> dict:
        bundle = repo.get_dataset_bundle(dataset_id)
        widths = [img.width for img in bundle.images]
        heights = [img.height for img in bundle.images]
        aspects = [img.aspect_ratio for img in bundle.images]
        directory_counts = Counter(img.directory_name for img in bundle.images)
        return {
            "image_count": len(bundle.images),
            "avg_width": sum(widths) / len(widths) if widths else 0,
            "avg_height": sum(heights) / len(heights) if heights else 0,
            "avg_aspect_ratio": sum(aspects) / len(aspects) if aspects else 0,
            "directory_distribution": dict(sorted(directory_counts.items()))
        }

    def object_stats(self, dataset_id: str) -> dict:
        bundle = repo.get_dataset_bundle(dataset_id)
        areas = [ann.area for ann in bundle.annotations]
        bbox_widths = [ann.bbox_xywh[2] for ann in bundle.annotations]
        bbox_heights = [ann.bbox_xywh[3] for ann in bundle.annotations]
        class_counts = Counter(ann.class_name for ann in bundle.annotations)
        return {
            "object_count": len(bundle.annotations),
            "avg_area": sum(areas) / len(areas) if areas else 0,
            "class_distribution": dict(class_counts),
            "bbox_width_min": min(bbox_widths) if bbox_widths else 0,
            "bbox_width_max": max(bbox_widths) if bbox_widths else 0,
            "bbox_height_min": min(bbox_heights) if bbox_heights else 0,
            "bbox_height_max": max(bbox_heights) if bbox_heights else 0
        }


stats_service = StatsService()
