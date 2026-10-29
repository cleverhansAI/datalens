#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
import json
import os
import shutil
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import httpx

from datalens import DataLensClient

_owned_pgids: list[int] = []
_owned_pids: list[int] = []
_cleanup_done = False
_shutdown_event = threading.Event()


def _is_healthy(url: str, timeout_seconds: float = 1.0) -> bool:
    # Bypass HTTP(S)_PROXY so localhost checks are not sent to a corporate proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout_seconds) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _wait_until_healthy(url: str, max_wait_seconds: int = 30) -> bool:
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        if _is_healthy(url):
            return True
        time.sleep(1.0)
    return False


def _backend_health_url(api_base: str) -> str:
    parsed = urlparse(api_base)
    return f"{parsed.scheme}://{parsed.netloc}/health"


def _frontend_url(frontend_port: int) -> str:
    return f"http://127.0.0.1:{frontend_port}"


def _resolve_pnpm_command(repo_root: Path) -> list[str]:
    pnpm_bin = shutil.which("pnpm")
    if pnpm_bin:
        return [pnpm_bin, "--dir", str(repo_root / "frontend")]
    corepack_bin = shutil.which("corepack")
    if corepack_bin:
        return [corepack_bin, "pnpm", "--dir", str(repo_root / "frontend")]
    raise RuntimeError(
        "Could not find 'pnpm' or 'corepack' in PATH. "
        "Install pnpm or run the script without --start-frontend."
    )


def _read_log_tail(path: Path, max_lines: int = 20) -> str:
    if not path.exists():
        return "<log file missing>"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def _render_progress_bar(progress: float, message: str, elapsed_seconds: int) -> None:
    bar_width = 32
    bounded_progress = max(0.0, min(progress, 1.0))
    filled = int(bar_width * bounded_progress)
    bar = "#" * filled + "-" * (bar_width - filled)
    print(
        f"\rIngesting COCO dataset [{bar}] {bounded_progress * 100:6.2f}% {message} elapsed: {elapsed_seconds}s",
        end="",
        flush=True
    )


def _ingest_with_spinner(
    client: DataLensClient,
    *,
    name: str,
    coco_json_path: str,
    image_root: str | None,
    protocol: str
) -> dict:
    result: dict = {}
    error: list[Exception] = []
    done = threading.Event()

    def _worker() -> None:
        try:
            dataset = client.create_dataset(
                name=name,
                coco_json_path=coco_json_path,
                image_root=image_root,
                protocol=protocol
            )
            result["dataset"] = dataset
        except Exception as exc:  # noqa: BLE001
            error.append(exc)
        finally:
            done.set()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    frames = ["[=         ]", "[==        ]", "[===       ]", "[ ====     ]", "[  ====    ]", "[   ====   ]", "[    ====  ]", "[     ==== ]", "[      ====]", "[       ===]", "[        ==]", "[         =]"]
    started = time.time()
    idx = 0
    while not done.is_set():
        elapsed = int(time.time() - started)
        frame = frames[idx % len(frames)]
        print(f"\rIngesting COCO dataset {frame} elapsed: {elapsed}s", end="", flush=True)
        idx += 1
        time.sleep(0.25)

    print("\rIngesting COCO dataset [##########] done.             ")
    if error:
        raise error[0]
    return result["dataset"]


def _ingest_with_progress(
    client: DataLensClient,
    *,
    name: str,
    coco_json_path: str,
    image_root: str | None,
    protocol: str
) -> dict:
    try:
        task = client.create_dataset_async(
            name=name,
            coco_json_path=coco_json_path,
            image_root=image_root,
            protocol=protocol
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {404, 405}:
            return _ingest_with_spinner(
                client,
                name=name,
                coco_json_path=coco_json_path,
                image_root=image_root,
                protocol=protocol
            )
        raise

    task_id = task["task_id"]
    started = time.time()
    while True:
        status = client.get_task(task_id)
        elapsed = int(time.time() - started)
        message = status.get("message", "") or "Working"
        progress = float(status.get("progress", 0.0))
        _render_progress_bar(progress, message, elapsed)

        state = status.get("state")
        if state == "done":
            print("")
            result = status.get("result")
            if result is None:
                raise RuntimeError("Dataset task completed without a result payload.")
            return result
        if state == "failed":
            print("")
            raise RuntimeError(message)

        time.sleep(0.5)


def _register_started_process(proc: subprocess.Popen) -> None:
    # start_new_session=True makes this pid the process-group leader.
    _owned_pgids.append(proc.pid)


def _cmdline_of(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def _pids_matching(pattern: str) -> list[int]:
    result = subprocess.run(
        ["pgrep", "-f", pattern],
        capture_output=True,
        text=True,
        check=False
    )
    skip = {os.getpid(), os.getppid()}
    pids: list[int] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.isdigit():
            continue
        pid = int(line)
        if pid in skip:
            continue
        cmdline = _cmdline_of(pid)
        if pattern not in cmdline or "start_datalens_with_coco.py" in cmdline:
            continue
        pids.append(pid)
    return pids


def _register_existing_pids(pattern: str) -> None:
    _owned_pids.extend(_pids_matching(pattern))


def _send_signal(pid: int, sig: int, *, process_group: bool) -> bool:
    try:
        if process_group:
            os.killpg(pid, sig)
        else:
            os.kill(pid, sig)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        if process_group:
            return _send_signal(pid, sig, process_group=False)
        return False


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _stop_pid(pid: int, *, process_group: bool, timeout_seconds: float = 5.0) -> None:
    if not _pid_exists(pid):
        return
    _send_signal(pid, signal.SIGTERM, process_group=process_group)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not _pid_exists(pid):
            return
        time.sleep(0.1)
    _send_signal(pid, signal.SIGKILL, process_group=process_group)
    if process_group:
        _send_signal(pid, signal.SIGKILL, process_group=False)


def _stop_matching_processes(pattern: str, label: str) -> None:
    pids = _pids_matching(pattern)
    if not pids:
        return
    print(f"Stopping stale {label} (pids: {', '.join(str(pid) for pid in pids)})...")
    for pid in pids:
        _stop_pid(pid, process_group=True)
        _stop_pid(pid, process_group=False)


def _cleanup_services() -> None:
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True
    if not _owned_pgids and not _owned_pids:
        return
    print("\nStopping DataLens services...")
    for pgid in _owned_pgids:
        _stop_pid(pgid, process_group=True)
    for pid in _owned_pids:
        _stop_pid(pid, process_group=False)
    print("Backend (and DuckDB) stopped.")


def _handle_shutdown_signal(signum: int, frame: object | None) -> None:
    _shutdown_event.set()
    raise SystemExit(0)


def _install_shutdown_handlers() -> None:
    atexit.register(_cleanup_services)
    signal.signal(signal.SIGINT, _handle_shutdown_signal)
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)


def _wait_until_shutdown() -> None:
    print("Services will keep running until you stop this task or press Ctrl+C.")
    try:
        while not _shutdown_event.wait(timeout=1.0):
            pass
    except KeyboardInterrupt:
        _shutdown_event.set()
    _cleanup_services()


def _start_backend_if_needed(repo_root: Path, backend_port: int, log_path: Path) -> None:
    health_url = f"http://127.0.0.1:{backend_port}/health"
    if _is_healthy(health_url):
        print(f"Backend already running at {health_url}")
        _register_existing_pids("datalens-server")
        return

    _stop_matching_processes("datalens-server", "backend")

    server_bin = repo_root / ".venv" / "bin" / "datalens-server"
    if not server_bin.exists():
        raise FileNotFoundError(
            f"Could not find {server_bin}. Activate venv and run: pip install -e \".[dev]\""
        )

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            [str(server_bin), "start", "--host", "0.0.0.0", "--port", str(backend_port)],
            cwd=repo_root,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
    _register_started_process(proc)

    if not _wait_until_healthy(health_url, max_wait_seconds=40):
        log_tail = _read_log_tail(log_path)
        raise RuntimeError(
            f"Backend failed to become healthy. Check log: {log_path}\n\n"
            f"Last log lines:\n{log_tail}"
        )
    print(f"Backend started: {health_url}")


def _start_frontend_if_needed(repo_root: Path, frontend_port: int, log_path: Path) -> None:
    url = _frontend_url(frontend_port)
    if _is_healthy(url, timeout_seconds=1.0):
        print(f"Frontend already running at {url}")
        _register_existing_pids("next dev")
        return

    _stop_matching_processes("next dev", "frontend")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    pnpm_prefix = _resolve_pnpm_command(repo_root)

    node_modules = repo_root / "frontend" / "node_modules"
    if not node_modules.exists():
        print("Installing frontend dependencies (node_modules missing)...")
        install = subprocess.run(
            [*pnpm_prefix, "install"],
            cwd=repo_root,
            capture_output=True,
            text=True
        )
        if install.returncode != 0:
            raise RuntimeError(
                "Failed to install frontend dependencies.\n"
                f"stdout:\n{install.stdout}\n\nstderr:\n{install.stderr}"
            )

    with log_path.open("a", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            [*pnpm_prefix, "dev", "--port", str(frontend_port)],
            cwd=repo_root,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
    _register_started_process(proc)

    # Frontend cold start may take a bit longer.
    if not _wait_until_healthy(url, max_wait_seconds=60):
        log_tail = _read_log_tail(log_path)
        raise RuntimeError(
            f"Frontend failed to become healthy. Check log: {log_path}\n\n"
            f"Last log lines:\n{log_tail}"
        )
    print(f"Frontend started: {url}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Start DataLens and ingest a COCO dataset.")
    parser.add_argument("coco_json_path", help="Absolute or relative path to COCO JSON file.")
    parser.add_argument(
        "--image-root",
        default=None,
        help="Image root directory for relative file_name entries in COCO."
    )
    parser.add_argument("--dataset-name", default="coco-dataset", help="Dataset display name.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000/api/v1", help="Backend API base URL.")
    parser.add_argument(
        "--api-timeout-seconds",
        type=int,
        default=900,
        help="HTTP timeout used for dataset ingestion call."
    )
    parser.add_argument("--backend-port", type=int, default=8000, help="Backend port.")
    parser.add_argument("--frontend-port", type=int, default=3000, help="Frontend port.")
    parser.add_argument(
        "--start-frontend",
        action="store_true",
        help="Also start the Next.js frontend."
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    coco_path = Path(args.coco_json_path).expanduser().resolve()
    if not coco_path.exists():
        raise FileNotFoundError(f"COCO JSON not found: {coco_path}")

    run_dir = repo_root / ".run"
    backend_log = run_dir / "backend.log"
    frontend_log = run_dir / "frontend.log"

    _install_shutdown_handlers()
    _start_backend_if_needed(repo_root=repo_root, backend_port=args.backend_port, log_path=backend_log)

    if args.start_frontend:
        _start_frontend_if_needed(
            repo_root=repo_root,
            frontend_port=args.frontend_port,
            log_path=frontend_log
        )

    client = DataLensClient(api_base=args.api_base, timeout=args.api_timeout_seconds)
    try:
        dataset = _ingest_with_progress(
            client,
            name=args.dataset_name,
            coco_json_path=str(coco_path),
            image_root=args.image_root,
            protocol="file"
        )
    except httpx.ReadTimeout as exc:
        raise RuntimeError(
            "Dataset ingestion request timed out. "
            "Retry with a larger --api-timeout-seconds value (for example 1800) "
            "or inspect backend log for loader bottlenecks.\n"
            f"Backend log: {backend_log}"
        ) from exc

    print("")
    print("Dataset ingested successfully.")
    print(json.dumps(dataset, indent=2))
    print("")
    print(f"Backend API: {args.api_base}")
    if args.start_frontend:
        print(f"Frontend: {_frontend_url(args.frontend_port)}")
    print(f"Backend log: {backend_log}")
    if args.start_frontend:
        print(f"Frontend log: {frontend_log}")
    print("")
    _wait_until_shutdown()


if __name__ == "__main__":
    main()
