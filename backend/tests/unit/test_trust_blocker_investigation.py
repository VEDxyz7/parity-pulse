"""Synthetic diagnostic controls; never counted as real historical evidence."""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.clients.binance_web3 import READ_OPERATIONS
from app.clients.common import ProviderError

spec = importlib.util.spec_from_file_location(
    "trust_blocker_investigation",
    Path(__file__).parents[3] / "scripts/investigate-trust-blockers.py",
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
OPEN = datetime(2026, 10, 5, 13, 30, tzinfo=UTC)
CLOSE = datetime(2026, 10, 2, 20, tzinfo=UTC)
RECEIVED = datetime(2026, 10, 6, 22, tzinfo=UTC)


def equities():
    common = {
        "source": "MASSIVE",
        "ticker": "NVDA",
        "adjusted": True,
        "first_seen": RECEIVED.isoformat(),
    }
    return [
        {
            **common,
            "interval": "1minute",
            "start_utc": (CLOSE - timedelta(minutes=1)).isoformat(),
            "close": "100",
        },
        {**common, "interval": "5minute", "start_utc": OPEN.isoformat(), "close": "103"},
    ]


def minute_rows():
    return [
        {
            "interval": "1m",
            "start_utc": (OPEN - timedelta(minutes=i)).isoformat(),
            "first_seen": RECEIVED.isoformat(),
            "close": "103",
        }
        for i in range(1, 31)
    ]


def test_real_capture_prices_and_dense_window_do_not_prove_missing_asof_features():
    rows = minute_rows()
    # An accidentally attached current ratio never becomes historical proof.
    for row in rows:
        row["token_to_share_ratio"] = "1.001"
    result = audit.historical_gate(rows, [], equities(), CLOSE, OPEN)
    assert result["stages"]["exact_independent_close_and_opening_bar"]
    assert result["primary_density"]["density_only_pass"]
    assert result["outcome"]["opening_return"] == "0.03"
    assert not result["qualifies"] and result["historical_ratio"] is None
    assert result["normalized_deviation"] is None and result["required_features"] is None
    assert "ASOF_TOKEN_SHARE_RATIO_UNVERIFIED" in result["rejection_reasons"]


def test_secondary_pool_density_cannot_become_primary_token_authority():
    result = audit.historical_gate([], minute_rows(), equities(), CLOSE, OPEN)
    assert result["secondary_density"]["density_only_pass"]
    assert not result["primary_density"]["density_only_pass"]
    assert "SECONDARY_POOL_DENSITY_IS_NOT_PRIMARY_TOKEN_AUTHORITY" in result["rejection_reasons"]
    assert not result["qualifies"]


@pytest.mark.parametrize("change", ["missing", "late", "incomplete", "revision", "identity"])
def test_exact_completed_unrevised_opening_outcome_required(change):
    rows = equities()
    if change == "missing":
        rows.pop()
    elif change == "late":
        rows[-1]["start_utc"] = (OPEN + timedelta(minutes=5)).isoformat()
    elif change == "incomplete":
        rows[-1]["first_seen"] = (OPEN + timedelta(minutes=4)).isoformat()
    elif change == "revision":
        rows.append({**rows[-1], "close": "104"})
    else:
        rows[-1]["ticker"] = "AAPL"
    result = audit.outcome(rows, CLOSE, OPEN, "MASSIVE")
    assert result["status"] == "UNSCORABLE" and result["opening_return"] is None


def test_partial_minute_window_fails_density_without_filling_missing_candles():
    rows = minute_rows()
    assert audit.density(rows, OPEN)["density_only_pass"]
    sparse = [row for row in rows if row not in rows[10:13]]
    assert not audit.density(sparse, OPEN)["density_only_pass"]
    assert len(sparse) == 27


@pytest.mark.parametrize("bad", [True, "NaN", "Infinity", "-1"])
def test_malformed_raw_prices_never_enter_backfill(bad):
    raw = [bad, "105", "99", "103", "10", audit.ms(OPEN - timedelta(minutes=1)), 1]
    record, reason = audit.candle(raw, "ondo", "1m", RECEIVED, OPEN - timedelta(minutes=30), OPEN)
    assert record is None and reason == "MALFORMED"


def test_raw_backfill_does_not_copy_a_current_ratio_or_guess_volume_units():
    raw = ["100", "105", "99", "103", "10", audit.ms(OPEN - timedelta(minutes=1)), 1]
    record, reason = audit.candle(raw, "ondo", "1m", RECEIVED, OPEN - timedelta(minutes=30), OPEN)
    assert reason is None
    assert record["historical_ratio"] is None and record["volume_unit"] == "UNKNOWN"
    assert not record["point_in_time_availability_verified"]
    assert record["first_seen"] == RECEIVED.isoformat()


def test_uncompleted_and_upper_boundary_candles_are_never_saved():
    raw = ["100", "105", "99", "103", "10", audit.ms(OPEN), 1]
    record, reason = audit.candle(raw, "ondo", "1m", RECEIVED, OPEN - timedelta(minutes=30), OPEN)
    assert record is None and reason == "OUTSIDE_EXCLUSIVE_QUERY_WINDOW"
    record, reason = audit.candle(
        raw, "ondo", "1m", OPEN + timedelta(seconds=59), OPEN, OPEN + timedelta(minutes=2)
    )
    assert record is None and reason == "UNCOMPLETED"


def test_pool_read_does_not_expand_production_allowlist_or_allow_execution():
    assert "token/top-liquidity" not in READ_OPERATIONS["GET"]
    client = audit.DiagnosticBinance(SecretStr("synthetic-key"), SecretStr("synthetic-secret"))
    try:
        client.authorize("GET", "/api/v1/dex/market/token/top-liquidity")
        for method, path in [
            ("POST", "/api/v1/dex/market/token/top-liquidity"),
            ("GET", "/api/v1/dex/aggregator/swap"),
            ("POST", "/api/v1/dex/aggregator/order/submit"),
            ("POST", "/api/v1/dex/transaction/broadcast"),
        ]:
            with pytest.raises(ProviderError, match="READ_ONLY_OPERATION_REQUIRED"):
                client.authorize(method, path)
    finally:
        client.close()
