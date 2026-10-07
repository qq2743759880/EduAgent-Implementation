"""Start and stop only the EduAgent W3 worker processes registered here."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PYTHON = (ROOT / ".venv" / "Scripts" / "python.exe").resolve()
LOGS = ROOT / "logs"
STATE = LOGS / "worker-pids"
WORKERS = {
    "parser-worker": "run_parser_worker.py",
    "ingest-worker": "run_ingest_worker.py",
    "reconciler": "run_reconciler.py",
}


def _process_matches(pid: int, name: str) -> bool:
    """Refuse to signal a reused PID or a process outside this checkout/venv."""
    try:
        process = psutil.Process(pid)
        executable = Path(process.exe()).resolve()
        command = [str(item).strip('"') for item in process.cmdline()]
        expected_script = (ROOT / "scripts" / WORKERS[name]).resolve()
        return (
            executable == PYTHON
            and any(Path(arg).resolve() == expected_script for arg in command if arg)
            and any(Path(candidate.cwd()).resolve() == ROOT
                    and any(Path(arg).resolve() == expected_script for arg in candidate.cmdline()[1:] if arg)
                    for candidate in [process, *process.children(recursive=True)])
        )
    except (psutil.Error, OSError, ValueError):
        return False


def _pid_file(name: str) -> Path:
    return STATE / f"{name}.json"


def _read_owned_pid(name: str) -> int | None:
    path = _pid_file(name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pid = int(data["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if _process_matches(pid, name):
        return pid
    return None


def start() -> int:
    if not PYTHON.is_file():
        print(f"[workers] missing project venv: {PYTHON}")
        return 2

    # Keep this gate aligned with upload._w3_worker_path_ready: unsafe DEBUG or
    # non-primary mode must never make worker upload appear available.
    from app.config import settings
    if settings.DEBUG or (settings.IMPORT_COMMAND_MODE != "primary" and not settings.MINERU_ENABLED):
        print("[workers] skipped: require DEBUG=False and primary imports or explicit MinerU")
        return 0

    LOGS.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)
    for name, script_name in WORKERS.items():
        existing = _read_owned_pid(name)
        if existing:
            print(f"[workers] already running {name} pid={existing}")
            continue

        script = ROOT / "scripts" / script_name
        (STATE / f"{name}.stop").unlink(missing_ok=True)
        log_path = LOGS / f"{name}.log"
        log_handle = log_path.open("a", encoding="utf-8")
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        child = subprocess.Popen(
            [str(PYTHON), str(script)],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=flags,
            close_fds=True,
        )
        log_handle.close()
        _pid_file(name).write_text(
            json.dumps({"pid": child.pid, "script": script_name}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[workers] started {name} pid={child.pid} log={log_path}")
    return 0


def stop() -> int:
    failures = 0
    for name in WORKERS:
        pid = _read_owned_pid(name)
        if pid is None:
            print(f"[workers] skip {name}: no verified owned PID")
            continue
        (STATE / f"{name}.stop").write_text("drain\n", encoding="utf-8")

        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if not psutil.pid_exists(pid):
                break
            time.sleep(0.25)
        if psutil.pid_exists(pid):
            failures += 1
            print(f"[workers] still draining {name} pid={pid}; left running, retry after its job completes")
        else:
            print(f"[workers] stopped {name} pid={pid}")

        if not psutil.pid_exists(pid):
            try:
                _pid_file(name).unlink(missing_ok=True)
            except OSError:
                pass
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"start", "stop"}:
        print("usage: manage_workers.py start|stop")
        raise SystemExit(2)
    raise SystemExit(start() if sys.argv[1] == "start" else stop())
