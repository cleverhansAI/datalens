# Using DataLens as a Pip Dependency

This document shows how another repository can consume DataLens exactly like a normal Python package.

## Install from Git

```bash
pip install "git+https://github.com/<your-org>/datalens.git"
```

## Install with ML extras

```bash
pip install "git+https://github.com/<your-org>/datalens.git#egg=datalens[ml]"
```

## What you get

- App:

```bash
datalens
datalens open /data/annotations.json --images /data/images --name my-dataset
```

`datalens` starts the local API and web UI together. It stores the dataset index in the project's `.datalens/` directory and closes that database when you stop the app.

- Python API:

```python
from datalens import DataLensClient
```

`DataLensClient()` uses the app when it is already running. Otherwise it reads and writes the project index in-process.

- Backend launcher for UI development:

```bash
datalens-server start --host 0.0.0.0 --port 8000
```

## Minimal integration example

```python
from datalens import DataLensClient

client = DataLensClient(api_base="http://127.0.0.1:8000/api/v1")

dataset = client.create_dataset(
    name="external-repo-dataset",
    coco_json_path="/data/annotations.json",
    image_root="/data/images",
    protocol="file"
)

view = client.query_view(
    dataset_id=dataset["id"],
    payload={"filters": [], "group_by": "directory", "page": 1, "page_size": 50}
)

print(view["total"])
```
