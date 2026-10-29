from __future__ import annotations

import json

import typer

app = typer.Typer(help="Open the DataLens app, or work with saved project data.")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    port: int | None = typer.Option(None, help="Port to bind. Defaults to a free local port."),
    idle_timeout: int = typer.Option(30, help="Minutes of inactivity before exit. 0 disables the timeout."),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open a browser window.")
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    from datalens.launcher import serve

    serve(port=port, idle_timeout_minutes=idle_timeout, open_browser=not no_browser)


@app.command("open")
def open_dataset(
    coco_json: str = typer.Argument(..., help="Path to a COCO annotations file"),
    images: str | None = typer.Option(None, "--images", help="Directory that contains the images"),
    name: str | None = typer.Option(None, "--name", help="Dataset name"),
    port: int | None = typer.Option(None, help="Port to bind. Defaults to a free local port."),
    idle_timeout: int = typer.Option(30, help="Minutes of inactivity before exit. 0 disables the timeout."),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open a browser window.")
) -> None:
    from datalens.launcher import serve

    serve(
        coco_json=coco_json,
        image_root=images,
        dataset_name=name,
        port=port,
        idle_timeout_minutes=idle_timeout,
        open_browser=not no_browser
    )


@app.command()
def list_datasets(
    api_base: str | None = typer.Option(None, help="API base URL. Defaults to the running app, or local project data.")
) -> None:
    from datalens import DataLensClient

    with DataLensClient(api_base=api_base) as client:
        typer.echo(json.dumps(client.list_datasets(), indent=2))


@app.command()
def create_dataset(
    name: str,
    coco_json_path: str,
    image_root: str | None = None,
    protocol: str = "file",
    api_base: str | None = typer.Option(None, help="API base URL. Defaults to the running app, or local project data.")
) -> None:
    from datalens import DataLensClient

    with DataLensClient(api_base=api_base) as client:
        payload = client.create_dataset(
            name=name,
            coco_json_path=coco_json_path,
            image_root=image_root,
            protocol=protocol
        )
    typer.echo(json.dumps(payload, indent=2))


@app.command()
def export_coco(
    dataset_id: str,
    api_base: str | None = typer.Option(None, help="API base URL. Defaults to the running app, or local project data.")
) -> None:
    from datalens import DataLensClient

    payload = {"filters": [], "group_by": "directory", "page": 1, "page_size": 100000}
    with DataLensClient(api_base=api_base) as client:
        exported = client.export_coco(dataset_id, payload)
    typer.echo(json.dumps(exported, indent=2))
