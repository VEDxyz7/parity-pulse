"""Local generated artifacts are separate from immutable historical inputs."""

from pathlib import Path


def diagnostic_output(root, name):
    if Path(name).name != name or name in {"", ".", ".."}:
        raise ValueError("Diagnostic output must be a filename")
    path = Path(root) / "var/diagnostics" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
