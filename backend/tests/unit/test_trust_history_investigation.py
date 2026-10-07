"""Synthetic diagnostic boundaries, separate from the REAL historical evidence artifact."""

import importlib.util
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "trust_history_investigation", Path(__file__).parents[3] / "scripts/investigate-trust-data.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
OPEN = datetime(2026, 10, 5, 13, 30, tzinfo=UTC)
CLOSE = datetime(2026, 10, 2, 20, tzinfo=UTC)
RECEIVED = datetime(2026, 10, 6, 18, tzinfo=UTC)


def bars():
    common = dict(
        kind="BAR",
        source="MASSIVE",
        data_mode="LIVE",
        data_quality="HISTORICAL",
        ticker="NVDA",
        adjusted=True,
        ingestion_timestamp=RECEIVED,
    )
    return [
        SimpleNamespace(
            **common,
            interval="1minute",
            source_timestamp=CLOSE - timedelta(minutes=1),
            close=Decimal("100"),
        ),
        SimpleNamespace(**common, interval="5minute", source_timestamp=OPEN, close=Decimal("103")),
    ]


def test_exact_canonical_target_is_post_decision_outcome_not_feature():
    result = audit.opening_outcome(bars(), CLOSE, OPEN)
    assert result["opening_return"] == "0.03" and result["status"] == "SCORABLE_OUTCOME_ONLY"
    assert not result["outcome_is_decision_feature"]
    assert result["target_bar_completed_at"] == (OPEN + timedelta(minutes=5)).isoformat()
    assert result["target_available_at"] == RECEIVED.isoformat()


@pytest.mark.parametrize(
    "mutation",
    ["missing", "late_start", "previous_wrong_close", "demo", "source", "adjustment", "incomplete"],
)
def test_missing_inexact_or_conflicting_opening_bar_is_unscorable(mutation):
    rows = bars()
    if mutation == "missing":
        rows.pop()
    elif mutation == "late_start":
        rows[-1].source_timestamp += timedelta(minutes=5)
    elif mutation == "previous_wrong_close":
        rows[0].source_timestamp -= timedelta(minutes=1)
    elif mutation == "demo":
        rows[-1].data_mode = "DEMO"
    elif mutation == "source":
        rows[-1].source = "BINANCE_RWA"
    elif mutation == "adjustment":
        rows[-1].adjusted = False
    else:
        rows[-1].ingestion_timestamp = OPEN + timedelta(minutes=4)
    result = audit.opening_outcome(rows, CLOSE, OPEN)
    assert result["status"] == "UNSCORABLE" and result["opening_return"] is None


def test_token_reference_news_and_target_timestamps_preserve_first_availability():
    token = SimpleNamespace(
        source_timestamp=OPEN - timedelta(minutes=1), interval="1m", ingestion_timestamp=RECEIVED
    )
    future = SimpleNamespace(source_timestamp=OPEN, interval="1m", ingestion_timestamp=RECEIVED)
    news = SimpleNamespace(
        published_timestamp=OPEN - timedelta(minutes=20), ingestion_timestamp=RECEIVED
    )
    result = audit.leakage_summary(
        [token, future], bars(), [news], OPEN, audit.opening_outcome(bars(), CLOSE, OPEN)
    )
    assert result["token_source_completion_before_decision"] == 1
    assert (
        result["token_features_known_by_decision"]
        == result["equity_references_known_by_decision"]
        == 0
    )
    assert result["news_published_by_decision"] == 1 and result["news_known_by_decision"] == 0
    assert result["target_excluded_from_features"] and result["target_available_after_decision"]
    assert (
        result["analogue_retrieval_at_historical_decision"]
        == "ZERO_ELIGIBLE_COMPLETED_AVAILABLE_EPISODES"
    )
