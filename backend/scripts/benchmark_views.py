from __future__ import annotations

import argparse
import time

from app.models.schemas import ViewSpec
from app.services.view_service import view_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark DataLens view query throughput")
    parser.add_argument("--dataset-id", required=True, help="Dataset id to benchmark")
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()

    spec = ViewSpec(group_by="directory", page=1, page_size=100)
    start = time.perf_counter()
    for _ in range(args.iterations):
        view_service.query(args.dataset_id, spec)
    elapsed = time.perf_counter() - start
    qps = args.iterations / elapsed if elapsed else 0
    print(f"iterations={args.iterations} elapsed={elapsed:.4f}s qps={qps:.2f}")


if __name__ == "__main__":
    main()
