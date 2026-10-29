#!/usr/bin/env python3
from __future__ import annotations

import time

from datalens import DataLensClient

COCO_JSON = "/media/max/8TB Drive/data/ODCT/odct_train/annotations/copy_paste/odct/augmented.json"
IMAGE_ROOT = ""
DATASET_NAME = "my-dataset"


def main() -> None:
    print("Starting dataset import...", flush=True)
    with DataLensClient() as client:
        task = client.create_dataset_async(
            name=DATASET_NAME,
            coco_json_path=COCO_JSON,
            image_root=IMAGE_ROOT or None,
        )
        dataset = _wait_for_dataset(client, task["task_id"])
        print("Loading view...", flush=True)
        view = client.query_view(
            dataset_id=dataset["id"],
            payload={"filters": [], "group_by": "directory", "page": 1, "page_size": 50},
        )
        print(f"Ready. Dataset {dataset['id']} has {view['total']} images in view.", flush=True)


def _wait_for_dataset(client: DataLensClient, task_id: str) -> dict:
    started = time.monotonic()
    while True:
        task = client.get_task(task_id)
        elapsed = int(time.monotonic() - started)
        _render_progress(float(task.get("progress") or 0.0), str(task.get("message") or ""), elapsed)
        state = task["state"]
        if state == "done":
            print(flush=True)
            result = task.get("result")
            if not isinstance(result, dict):
                raise SystemExit("Dataset import finished without a result.")
            return result
        if state == "failed":
            print(flush=True)
            raise SystemExit(str(task.get("message") or "Dataset import failed."))
        time.sleep(0.2)


def _render_progress(progress: float, message: str, elapsed_seconds: int) -> None:
    bar_width = 32
    bounded = max(0.0, min(progress, 1.0))
    filled = int(bar_width * bounded)
    bar = "#" * filled + "-" * (bar_width - filled)
    print(
        f"\r[{bar}] {bounded * 100:6.2f}%  {message}  ({elapsed_seconds}s)",
        end="",
        flush=True,
    )


if __name__ == "__main__":
    main()
