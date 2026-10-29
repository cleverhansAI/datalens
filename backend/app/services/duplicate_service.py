from __future__ import annotations

from app.repositories import repo
from app.services.embedding_service import embedding_service


class DuplicateService:
    def find_visual_duplicates(self, dataset_id: str) -> list[dict]:
        bundle = repo.get_dataset_bundle(dataset_id)
        by_hash: dict[str, list[int]] = {}
        for image in bundle.images:
            if image.phash is None:
                continue
            by_hash.setdefault(image.phash, []).append(image.id)
        groups = []
        for phash, ids in by_hash.items():
            if len(ids) > 1:
                groups.append({"kind": "phash", "key": phash, "image_ids": ids})
        return groups

    def find_embedding_duplicates(self, dataset_id: str, threshold: float = 0.98) -> list[dict]:
        run = embedding_service.latest_run_for_dataset(dataset_id)
        if run is None:
            return []
        similar = embedding_service.find_similar_pairs(run.id, threshold=threshold, limit=100)
        return [{"kind": "embedding", "pair": item["pair"], "score": item["score"]} for item in similar]


duplicate_service = DuplicateService()
