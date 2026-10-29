# DataLens Architecture Notes

## Modules

- Backend service layer for ingestion, views, embeddings, stats, duplicates, export.
- Frontend Next.js application with board, dashboards, and embedding views.
- Python SDK and CLI that use the same HTTP APIs.

## Performance-first defaults

- Paged view APIs with group counters.
- Lightweight in-memory repo baseline and columnar embeddings in Parquet.
- Frontend designed for virtualized-ready card components and incremental tabs.

## Next hardening targets

- Replace in-memory repository with DuckDB-backed metadata and indexed query plans.
- Add async task queue and distributed worker scale-out.
- Add OpenTelemetry traces and benchmark suites to CI.
