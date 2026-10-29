# DataLens

DataLens is an open-source computer vision dataset exploration and curation platform.

## Install as a Python package

From another repository:

```bash
pip install "git+https://github.com/<your-org>/datalens.git"
```

For local development in this repository:

```bash
pip install -e ".[dev]"
```

Optional ML extras:

```bash
pip install -e ".[ml]"
```

You then get:

- `datalens` CLI
- `datalens-server` backend launcher
- `from datalens import DataLensClient` for Python API usage

## Monorepo layout

- `backend/`: FastAPI backend services
- `frontend/`: Next.js web app
- `cli/`: Typer-based command line client
- `sdk/python/`: Python SDK
- `docs/`: architecture and implementation notes

## Quick start

Install the package, then start the app from the project that owns your data:

```bash
pip install -e ".[dev]"
datalens
```

`datalens` serves the API and the web UI, opens a browser, and keeps running until you press Ctrl+C or it sits idle for 30 minutes. The database opens with the app and checkpoints when the app stops.

To view data that is already imported, run `datalens` again from the same project. That reopens `.datalens/` and does not read the COCO file again. The browser opens on the last dataset.

To import a COCO dataset as the app starts:

```bash
datalens open /path/to/annotations.json --images /path/to/images --name my-dataset
```

Saved indexes live in a `.datalens/` directory in the project (the nearest directory with `.git` or `pyproject.toml`). Images and annotation files stay where they are. Outside a project, data is stored in `~/.local/share/datalens`.

### Local UI development

The installed app does not need Node. Use the two processes below only when changing the web UI:

```bash
datalens-server start --reload
```

```bash
cd frontend
pnpm install
pnpm dev
```

Rebuild the bundled UI after frontend changes:

```bash
pnpm --dir frontend build
rm -rf sdk/python/datalens/ui
cp -a frontend/out sdk/python/datalens/ui
```

### CLI

```bash
datalens --help
```

## Start with a COCO file

Use the one-command startup script:

```bash
bash scripts/start_with_coco.sh /absolute/path/to/annotations.json /absolute/path/to/images my-dataset
```

Detailed guide: `docs/run_with_coco.md`

Pip package integration guide: `docs/pip_package_usage.md`
