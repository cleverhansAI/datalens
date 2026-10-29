# DataLens Performance Baseline

## Runtime targets

- Keep interactive dataset view endpoint p95 under 250ms on medium local datasets.
- Keep board refresh under 500ms for a 60-card page.
- Keep embedding throughput stable with deterministic batching.

## How to benchmark

1. Create and ingest a dataset using API or CLI.
2. Run:

```bash
cd backend
python scripts/benchmark_views.py --dataset-id <DATASET_ID> --iterations 200
```

3. Record elapsed time and QPS in pull requests.

## Optimization checklist

- Use `page_size` limits and avoid oversized API payloads.
- Prefer grouped aggregate responses rather than client-side scans.
- Cache repeated view specs by dataset and hash key.
- Store vectors in Parquet and avoid JSON blob vector transport.
