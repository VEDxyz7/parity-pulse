"""Run built React UI against disposable, credential-free local fixture backends.

Requires local Google Chrome. Uses ports 8054-8057/5178; refuses occupied ports.
No .env is loaded and no provider/wallet credentials are forwarded. Own processes only.
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--presentation-only", action="store_true")
    parser.add_argument("--landing-only", action="store_true")
    options = parser.parse_args()
    assert (ROOT / "frontend/dist/index.html").is_file(), "Run npm run build first"
    assert Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").is_file()
    ports = (8054, 8055, 8056, 8057, 5178)
    for port in ports:
        with socket.socket() as check:
            check.bind(("127.0.0.1", port))
    directory = Path(tempfile.mkdtemp(prefix="parity-phase15-browser-"))
    safe = {k: os.environ[k] for k in ("PATH", "TMPDIR", "LANG", "LC_ALL") if k in os.environ}
    safe["PARITY_PHASE15_DIR"] = str(directory)
    safe["PYTHONPATH"] = str(ROOT / "backend")
    jobs = []
    try:
        for port, factory in (
            (8054, "demo"),
            (8055, "demo"),
            (8056, "ordinary"),
            (8057, "failed_simulation"),
        ):
            command = [
                str(ROOT / ".venv/bin/python"),
                "-m",
                "uvicorn",
                "backend.tests.fixtures.frontend_phase15:" + factory,
                "--factory",
                "--app-dir",
                str(ROOT),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ]
            with (directory / f"server-{port}.log").open("w") as log:
                jobs.append(
                    subprocess.Popen(
                        command, cwd=ROOT, env=safe, stdout=log, stderr=log, start_new_session=True
                    )
                )
        with (directory / "frontend.log").open("w") as log:
            jobs.append(
                subprocess.Popen(
                    [
                        str(ROOT / ".venv/bin/python"),
                        "-m",
                        "http.server",
                        "5178",
                        "--bind",
                        "127.0.0.1",
                        "--directory",
                        str(ROOT / "frontend/dist"),
                    ],
                    cwd=ROOT,
                    env=safe,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
            )
        for port in ports:
            for attempt in range(150):
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}" + ("/api/health" if port != 5178 else "/"),
                        timeout=1,
                    ) as response:
                        assert response.status == 200
                    break
                except Exception:
                    assert all(p.poll() is None for p in jobs), (
                        f"Test server failed; logs: {directory}"
                    )
                    if attempt == 149:
                        raise RuntimeError("Isolated test readiness failed") from None
                    time.sleep(0.1)
        if not options.presentation_only and not options.landing_only:
            subprocess.run(
                [str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/check-mcp-hardening.py")],
                cwd=ROOT,
                env=safe,
                check=True,
            )
            subprocess.run(
                ["node", str(ROOT / "scripts/check-frontend-phase15.mjs")],
                cwd=ROOT,
                env=safe,
                check=True,
            )
        if not options.landing_only:
            subprocess.run(
                ["node", str(ROOT / "scripts/check-presentation-browser.mjs")],
                cwd=ROOT, env=safe, check=True,
            )
        subprocess.run(
            ["node", str(ROOT / "scripts/check-landing-browser.mjs")],
            cwd=ROOT, env=safe, check=True,
        )
    finally:
        for process in jobs:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in jobs:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        print(
            json.dumps(
                {
                    "evidence_directory": str(directory),
                    "owned_servers_stopped": len(jobs),
                    "unrelated_processes_touched": 0,
                }
            )
        )


if __name__ == "__main__":
    main()
