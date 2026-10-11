"""Committed historical bytes and logical provenance survive evidence cleanup."""

import hashlib
import json
from pathlib import Path

import pytest

from app.repositories.historical_inputs import BACKFILL_NAME, DIRECTORY, read_historical_input
from app.repositories.research_source import HistoricalSource
from app.services.research_episodes import fingerprint
from app.utils.artifacts import diagnostic_output

ROOT = Path(__file__).parents[3]


def test_all_committed_inputs_match_original_bytes():
    manifest = json.loads((ROOT / DIRECTORY / "manifest.json").read_text())
    assert len(manifest["inputs"]) == 8
    for name, entry in manifest["inputs"].items():
        raw = (ROOT / DIRECTORY / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
        assert len(raw) == entry["bytes"]
        assert read_historical_input(ROOT, name) == json.loads(raw)


def copy_capture(tmp_path):
    directory = tmp_path / DIRECTORY
    directory.mkdir(parents=True)
    for name in (BACKFILL_NAME, "manifest.json"):
        (directory / name).write_bytes((ROOT / DIRECTORY / name).read_bytes())
    return directory / BACKFILL_NAME


def test_raw_coverage_and_original_provenance_preserved_without_local_databases(tmp_path):
    copy_capture(tmp_path)
    source = HistoricalSource(tmp_path).load()
    raw = read_historical_input(tmp_path, BACKFILL_NAME)
    assert len(raw["token_bars"]) == 7336
    assert len(raw["equity_bars"]) == 62
    assert source.coverage()["unique_primary_raw_bars"] == 7336
    assert source.coverage()["equity_bar_count"] == 62
    assert source.provenance == ["docs/evidence/" + BACKFILL_NAME + ":" + fingerprint(raw)]
    assert all(r.data_mode == "LIVE" for r in source.records["raw_token_bars"])
    assert all(r.data_quality == "HISTORICAL" for r in source.records["raw_token_bars"])


def test_modified_input_fails_closed_before_becoming_research_evidence(tmp_path):
    path = copy_capture(tmp_path)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="integrity mismatch"):
        HistoricalSource(tmp_path).load()


def test_missing_manifest_input_cannot_silently_reduce_coverage(tmp_path):
    copy_capture(tmp_path).unlink()
    with pytest.raises(FileNotFoundError):
        HistoricalSource(tmp_path).load()


def test_local_diagnostics_cannot_replace_archived_history(tmp_path):
    path = copy_capture(tmp_path)
    before = path.read_bytes()
    local = diagnostic_output(tmp_path, BACKFILL_NAME)
    local.write_text('{"synthetic": true}')
    assert local == tmp_path / "var/diagnostics" / BACKFILL_NAME
    assert path.read_bytes() == before
    assert HistoricalSource(tmp_path).load().coverage()["unique_primary_raw_bars"] == 7336
    with pytest.raises(ValueError, match="filename"):
        diagnostic_output(tmp_path, "../../data/historical/overwrite.json")
