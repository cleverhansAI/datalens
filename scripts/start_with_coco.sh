#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: bash scripts/start_with_coco.sh <coco_json_path> [image_root] [dataset_name]"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COCO_JSON_PATH="$1"
IMAGE_ROOT="${2:-}"
DATASET_NAME="${3:-coco-dataset}"
API_BASE="http://127.0.0.1:8000/api/v1"

if [[ ! -f "$COCO_JSON_PATH" ]]; then
  echo "COCO JSON file not found: $COCO_JSON_PATH"
  exit 1
fi

mkdir -p "$ROOT_DIR/.run"
BACKEND_LOG="$ROOT_DIR/.run/backend.log"
FRONTEND_LOG="$ROOT_DIR/.run/frontend.log"

echo "==> Setting up Python environment"
if [[ ! -d "$ROOT_DIR/.venv" ]]; then
  python3 -m venv "$ROOT_DIR/.venv"
fi
source "$ROOT_DIR/.venv/bin/activate"
pip install -q -e "$ROOT_DIR[dev]"

echo "==> Starting backend on :8000"
if ! curl -fsS "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
  nohup "$ROOT_DIR/.venv/bin/datalens-server" start --host 0.0.0.0 --port 8000 >"$BACKEND_LOG" 2>&1 &
  for _ in {1..30}; do
    if curl -fsS "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

if ! curl -fsS "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
  echo "Backend did not become healthy. Check: $BACKEND_LOG"
  exit 1
fi

echo "==> Ingesting COCO dataset"
if [[ -n "$IMAGE_ROOT" ]]; then
  "$ROOT_DIR/.venv/bin/datalens" create-dataset "$DATASET_NAME" "$COCO_JSON_PATH" --image-root "$IMAGE_ROOT" --protocol file --api-base "$API_BASE"
else
  "$ROOT_DIR/.venv/bin/datalens" create-dataset "$DATASET_NAME" "$COCO_JSON_PATH" --protocol file --api-base "$API_BASE"
fi

echo "==> Installing frontend dependencies"
if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
  (cd "$ROOT_DIR/frontend" && pnpm install)
fi

echo "==> Starting frontend on :3000"
if ! curl -fsS "http://127.0.0.1:3000" >/dev/null 2>&1; then
  nohup pnpm --dir "$ROOT_DIR/frontend" dev --port 3000 >"$FRONTEND_LOG" 2>&1 &
  sleep 2
fi

echo ""
echo "DataLens is starting."
echo "Frontend: http://127.0.0.1:3000"
echo "Backend API: http://127.0.0.1:8000/api/v1"
echo "Backend log: $BACKEND_LOG"
echo "Frontend log: $FRONTEND_LOG"
echo ""
echo "To stop later:"
echo "  pkill -f \"datalens-server\""
echo "  pkill -f \"next dev\""
