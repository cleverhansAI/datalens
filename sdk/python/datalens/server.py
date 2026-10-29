from __future__ import annotations

import uvicorn
from typer import Context, Option, Typer

server_app = Typer(help="Run DataLens backend server")


def _run_server(host: str, port: int, reload: bool) -> None:
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


@server_app.callback(invoke_without_command=True)
def server(
    ctx: Context,
    host: str = Option("0.0.0.0", help="Host interface"),
    port: int = Option(8000, help="Port"),
    reload: bool = Option(False, help="Enable auto reload")
) -> None:
    # Allow both forms:
    # - datalens-server --port 8000
    # - datalens-server start --port 8000
    if ctx.invoked_subcommand is None:
        _run_server(host=host, port=port, reload=reload)


@server_app.command("start")
def start(
    host: str = Option("0.0.0.0", help="Host interface"),
    port: int = Option(8000, help="Port"),
    reload: bool = Option(False, help="Enable auto reload")
) -> None:
    _run_server(host=host, port=port, reload=reload)


def main() -> None:
    server_app()
