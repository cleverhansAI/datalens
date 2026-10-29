# Run DataLens With a COCO Dataset

This guide starts the full stack and imports a COCO JSON in one command.

The startup script installs DataLens from the **repository root package** (`pip install -e .[dev]`) so it behaves like a pip-installable external dependency.

## 1) Requirements

- Python 3.11+
- Node.js 20+
- `pnpm`

## 2) Start with one script

From repo root:

```bash
bash scripts/start_with_coco.sh /absolute/path/to/annotations.json /absolute/path/to/images my-dataset
```

Arguments:

- `coco_json_path` (required): COCO annotation JSON
- `image_root` (optional): root directory for relative `file_name` entries in COCO
- `dataset_name` (optional): defaults to `coco-dataset`

If your COCO uses absolute image paths in `file_name`, omit `image_root`:

```bash
bash scripts/start_with_coco.sh /absolute/path/to/annotations.json
```

## 3) Open the app

- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8000/api/v1`

Logs:

- Backend: `.run/backend.log`
- Frontend: `.run/frontend.log`

## 4) Stop services

```bash
pkill -f "datalens-server"
pkill -f "next dev"
```
