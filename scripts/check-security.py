"""Local audit: ignore rules, configured-secret leakage and frontend isolation.

Secret values are read only into memory. Never print values or matching snippets.
No external calls, Git initialization in the workspace or commits are performed.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
SECRET_NAMES = (
    "BINANCE_WEB3_API_KEY",
    "BINANCE_WEB3_SECRET_KEY",
    "MASSIVE_API_KEY",
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "POLYGON_API_KEY",
    "TWELVE_DATA_API_KEY",
    "FINNHUB_API_KEY",
    "LLM_API_KEY",
    "EXECUTION_WORKER_TOKEN",
    "LIVE_SIGNER_PRIVATE_KEY",
    "SIDECAR_TOKEN",
    "ALTANA_OWNER_PRIVATE_KEY",
    "X402_FACILITATOR_KEY",
)
configured = dotenv_values(ROOT / ".env") if (ROOT / ".env").is_file() else {}
secrets = [os.environ.get(key) or configured.get(key) for key in SECRET_NAMES]
secrets = [value.encode() for value in secrets if value]

source_files = []
for folder in ["backend", "frontend/src", "frontend/dist", "scripts", "docs", "data", "sidecar"]:
    for candidate in (ROOT / folder).rglob("*"):
        if candidate.is_file() and not any(
            part in {"__pycache__", "node_modules", ".venv"} for part in candidate.parts
        ):
            source_files.append(candidate)
source_files += [
    ROOT / name
    for name in [
        "README.md",
        ".env.example",
        ".gitignore",
        ".dockerignore",
        "compose.yaml",
        "Dockerfile",
        "package.json",
        "package-lock.json",
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "frontend/Dockerfile",
        "frontend/nginx.conf",
    ]
    if (ROOT / name).is_file()
]
leaks = sum(any(secret in path.read_bytes() for secret in secrets) for path in source_files)
assert leaks == 0, "Configured credential value detected in an audited artifact; details suppressed"

bundle_files = list((ROOT / "frontend/dist").rglob("*.js"))
assert bundle_files, "Build the frontend before running this audit"
for path in bundle_files:
    content = path.read_text()
    assert all(name not in content for name in SECRET_NAMES), (
        "Backend variable name in frontend bundle"
    )

# Check real Git ignore semantics against filenames without reading or copying .env.
with tempfile.TemporaryDirectory(prefix="parity-ignore-") as directory:
    target = Path(directory)
    (target / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())
    subprocess.run(["git", "init", "--quiet", directory], check=True, capture_output=True)
    result = subprocess.run(
        ["git", "-C", directory, "check-ignore", "--stdin"],
        input=".env\n.env.local\n.env.production\n.env.example\n.venv/file\n",
        text=True,
        capture_output=True,
        check=True,
    )
    assert set(result.stdout.splitlines()) == {
        ".env",
        ".env.local",
        ".env.production",
        ".venv/file",
    }

ignore = (ROOT / ".dockerignore").read_text().splitlines()
assert ".env" in ignore and ".env.*" in ignore and "**/.env" in ignore
print(
    json.dumps(
        {
            "configured_secret_leakage": "PASS",
            "git_env_ignore": "PASS",
            "docker_env_exclusion": "PASS",
            "frontend_secret_isolation": "PASS",
            "artifacts_scanned": len(source_files),
        }
    )
)
