"""Immutable offline captures; original source identities survive filesystem migration."""

import hashlib
import json
from pathlib import Path

DIRECTORY = Path("data/historical")
BACKFILL_NAME = "TRUST_BLOCKER_HISTORICAL_BACKFILL.json"


def input_metadata(root, name):
    if Path(name).name != name:
        raise ValueError("Historical input must be a filename")
    manifest = json.loads((Path(root) / DIRECTORY / "manifest.json").read_text())
    if manifest.get("format_version") != 1:
        raise ValueError("Unsupported historical manifest")
    return manifest["inputs"][name]


def read_historical_input(root, name):
    metadata = input_metadata(root, name)
    raw = (Path(root) / DIRECTORY / name).read_bytes()
    if len(raw) != metadata["bytes"] or hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
        raise ValueError("Historical input integrity mismatch")
    return json.loads(raw)
