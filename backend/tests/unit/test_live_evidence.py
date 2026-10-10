"""Bounded parseable captures, no credentials or signing artifacts in diagnostics."""

import json

import pytest

from app.repositories.live_fills import MAX_CAPTURE_ROWS, LiveFillStore
from backend.tests.fixtures.rfq_orders import cow


def payload():
    return {
        "executionMode": "RFQ",
        "rfq": {
            "vendor": "CowSwap",
            "orderId": "fixture-order",
            "typedDataToSign": json.dumps(cow()),
            "signingScheme": "EIP712",
        },
        "headers": {"authorization": "SENTINEL_CREDENTIAL"},
        "signature": "SENTINEL_SIGNATURE",
    }


def test_capture_sanitization_provenance_integrity_and_public_allowlist():
    store = LiveFillStore(redaction_values=("SENTINEL_CREDENTIAL",))
    raw = payload()
    raw["rfq"]["signature"] = "SENTINEL_SIGNATURE"
    store.capture_rfq(raw, verdict="REJECTED", reason="RFQ_SETTLEMENT_EQUIVALENCE_UNVERIFIED")
    view = store.rfq_captures()[0]
    assert "payload" not in view and view["schema_version"] == 2 and view["integrity"] == "PASS"
    assert view["source"] == "BINANCE_WEB3" and view["chain_id"] == "56"
    internal = store.rfq_captures(internal=True)[0]
    assert internal["payload"]["typedDataToSign"] == cow()
    assert "SENTINEL" not in json.dumps(internal)
    assert internal["captured_at"]


def test_oversized_json_is_valid_gap_record_not_truncated_json():
    store = LiveFillStore()
    raw = payload()
    raw["rfq"]["typedDataToSign"] = json.dumps({"huge": "x" * 300000})
    store.capture_rfq(raw, verdict="REJECTED")
    row = store.rfq_captures(internal=True)[0]
    assert row["verdict"] == "INCOMPLETE" and row["reason"] == "PAYLOAD_SIZE_LIMIT"
    assert row["payload"]["omitted"] == "PAYLOAD_SIZE_LIMIT"


def test_retention_is_bounded_and_corruption_is_visible():
    store = LiveFillStore()
    for _ in range(MAX_CAPTURE_ROWS + 3):
        store.capture_rfq(payload(), verdict="REJECTED")
    assert len(store.rfq_captures(1000)) == MAX_CAPTURE_ROWS
    store.db.execute("UPDATE rfq_evidence_v2 SET payload='{}'")
    store.db.commit()
    assert all(
        r["integrity"] == "FAIL" and "payload" not in r for r in store.rfq_captures(internal=True)
    )


@pytest.mark.parametrize("raw", [None, [], {"rfq": None}, {"rfq": {"typedDataToSign": "bad-json"}}])
def test_malformed_capture_does_not_break_diagnostics(raw):
    store = LiveFillStore()
    store.capture_rfq(raw, verdict="REJECTED")
    assert store.rfq_captures()[0]["integrity"] == "PASS"


def test_metadata_bounded_and_invalid_domain_is_visible():
    store = LiveFillStore(redaction_values=("CREDENTIAL_SENTINEL",))
    raw = payload()
    raw["rfq"]["typedDataToSign"] = cow()
    raw["rfq"]["typedDataToSign"]["domain"] = None
    raw["rfq"]["vendor"] = {"unsupported": "value"}
    store.capture_rfq(raw, verdict="REJECTED", reason="x" * 300000, source="CREDENTIAL_SENTINEL")
    row = store.rfq_captures()[0]
    assert row["verdict"] == "INCOMPLETE" and row["chain_id"] == ""
    assert row["source"] == "UNKNOWN_SOURCE" and len(row["reason"]) <= 256
    assert "SENTINEL" not in json.dumps(row)


def test_total_retention_includes_payloads_not_only_row_count():
    store = LiveFillStore()
    raw = payload()
    typed = cow()
    typed["message"]["appData"] = (
        "0x" + "a" * 200000
    )  # schema-incomplete unsigned evidence, not compatible order
    raw["rfq"]["typedDataToSign"] = json.dumps(typed)
    for _ in range(50):
        store.capture_rfq(raw, verdict="INCOMPLETE")
    rows = store.rfq_captures(128)
    assert 0 < len(rows) < 50
    assert sum(row["size"] for row in rows) < 8 * 1024 * 1024
