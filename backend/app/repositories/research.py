"""Content-addressed research artifacts only; no production database or execution state."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from app.models.research import ReplayRun


class ResearchStore:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        if self.directory.is_file() or self.directory.suffix == ".db":
            raise ValueError("Research artifacts require a separate directory")
        self.directory.mkdir(parents=True, exist_ok=True)
        if list(self.directory.glob("*.db")):
            raise ValueError("Research store must not contain application databases")

    def save(self, run):
        run = ReplayRun.model_validate(run.model_dump())
        if len(run.run_id) != 64 or any(c not in "0123456789abcdef" for c in run.run_id):
            raise ValueError("Content-addressed identity required")
        destination = self.directory / f"{run.run_id}.json"
        record = run.model_dump_json()
        payload = (
            json.dumps(
                {
                    "sha256": hashlib.sha256(record.encode()).hexdigest(),
                    "record": record,
                },
                indent=2,
            )
            + "\n"
        ).encode()
        if destination.exists():
            if destination.read_bytes() != payload:
                raise ValueError("Immutable replay artifact conflict")
            return destination
        fd, temporary = tempfile.mkstemp(prefix=".replay-", dir=self.directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, destination)  # Atomic no-overwrite publication.
            except FileExistsError:
                if destination.read_bytes() != payload:
                    raise ValueError("Concurrent immutable replay artifact conflict") from None
        finally:
            Path(temporary).unlink(missing_ok=True)
        return destination

    def load(self, identifier):
        if len(identifier) != 64 or any(c not in "0123456789abcdef" for c in identifier):
            raise ValueError("Invalid replay identity")
        artifact = json.loads((self.directory / f"{identifier}.json").read_bytes())
        record = artifact["record"]
        if hashlib.sha256(record.encode()).hexdigest() != artifact["sha256"]:
            raise ValueError("Corrupt research artifact")
        run = ReplayRun.model_validate_json(record)
        if run.run_id != identifier:
            raise ValueError("Replay identity conflict")
        return run

    def list(self, mode):
        """Bounded immutable catalog; loading uses the original checksum/schema checks."""
        if mode not in {"DEMO", "LIVE"}:
            raise ValueError("Explicit replay mode required")
        paths = sorted(self.directory.glob("*.json"))
        if len(paths) > 50 or any(p.stat().st_size > 2_000_000 for p in paths):
            raise ValueError("Replay catalog inspection bound exceeded")
        runs = [self.load(p.stem) for p in paths]
        return tuple(run for run in runs if run.data_mode == mode)
