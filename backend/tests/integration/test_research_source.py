"""Offline SQL/source boundaries; temporary fixtures are not real research evidence."""

import hashlib
import json
import sqlite3

import pytest

from app.repositories.research_source import HistoricalSource
from app.services.demo_sandbox import DemoTrustSandbox


def database(tmp_path, *, declared_mode="DEMO", payload=None):
    folder = tmp_path / "data"
    folder.mkdir()
    path = folder / "fixture.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE token_observations(id TEXT, data_mode TEXT, payload TEXT)")
        connection.execute("CREATE TABLE positions(id TEXT, payload TEXT)")
        connection.execute("INSERT INTO positions VALUES('untouched','private execution state')")
        record = DemoTrustSandbox().datasets["steady"].price.record
        connection.execute(
            "INSERT INTO token_observations VALUES(?,?,?)",
            ("test", declared_mode, payload or record.model_dump_json()),
        )
    return path


def test_demo_records_excluded_and_no_execution_state_mutation(tmp_path):
    path = database(tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    source = HistoricalSource(tmp_path).load()
    assert source.coverage()["unique_existing_token_records"] == 0
    assert source.records["trust_samples"] == source.records["trust_episodes"] == []
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert source.provenance == HistoricalSource(tmp_path).load().provenance
    assert not list((tmp_path / "data").glob("*.db-journal"))


def test_outer_sql_mode_cannot_promote_demo_payload(tmp_path):
    database(tmp_path, declared_mode="LIVE")
    source = HistoricalSource(tmp_path).load()
    assert source.records["token_observations"] == []
    assert source.rejected["token_observations:MODE_CONFLICT"] == 1


def test_malformed_real_labeled_sql_row_is_explicitly_rejected(tmp_path):
    database(tmp_path, declared_mode="LIVE", payload='{"token_price":"NaN"}')
    source = HistoricalSource(tmp_path).load()
    assert source.rejected["token_observations:MALFORMED"] == 1
    assert source.coverage()["unique_existing_token_records"] == 0


def test_raw_diagnostic_ratio_backfill_and_non_primary_source_forbidden(tmp_path):
    (tmp_path / "data").mkdir()
    directory = tmp_path / "data/historical"
    directory.mkdir(parents=True)
    path = directory / "TRUST_BLOCKER_HISTORICAL_BACKFILL.json"
    for change in ({"historical_ratio": "0.5"}, {"source": "GECKOTERMINAL"}, {"synthetic": True}):
        row = {"synthetic": False, "historical_ratio": None, "source": "BINANCE_MARKET", **change}
        path.write_text(
            json.dumps(
                {"evidence_kind": "REAL_TEST_ENVELOPE", "execution_calls": 0, "token_bars": [row]}
            )
        )
        manifest = {
            "format_version": 1,
            "inputs": {
                path.name: {
                    "original_path": "docs/evidence/" + path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "bytes": path.stat().st_size,
                }
            },
        }
        (directory / "manifest.json").write_text(json.dumps(manifest))
        with pytest.raises(ValueError, match="Unverified raw token"):
            HistoricalSource(tmp_path).load()
