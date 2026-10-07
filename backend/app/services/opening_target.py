"""Single configured opening target, shared with historical diagnostics."""

from datetime import timedelta
from decimal import localcontext

from app.models.research import OPENING_MINUTES


def opening_outcome(bars, previous_close, opening):
    """A separately labeled outcome; never a feature available before reopening."""
    reference = [
        b
        for b in bars
        if b.kind == "BAR"
        and b.interval == "1minute"
        and b.source_timestamp + timedelta(minutes=1) == previous_close
    ]
    target = [
        b
        for b in bars
        if b.kind == "BAR"
        and b.interval == f"{OPENING_MINUTES}minute"
        and b.source_timestamp == opening
    ]
    if not reference or not target:
        return {
            "status": "UNSCORABLE",
            "reason": "PREVIOUS_REGULAR_CLOSE_OR_FIRST_5M_BAR_MISSING",
            "opening_return": None,
            "target_available_at": None,
        }
    if (
        len({(b.close, b.adjusted, b.source, b.ticker) for b in reference}) > 1
        or len({(b.close, b.adjusted, b.source, b.ticker) for b in target}) > 1
    ):
        return {
            "status": "UNSCORABLE",
            "reason": "CONFLICTING_CAPTURE_REVISIONS",
            "opening_return": None,
            "target_available_at": None,
        }
    previous = min(reference, key=lambda b: b.ingestion_timestamp)
    first = min(target, key=lambda b: b.ingestion_timestamp)
    if (
        previous.source != "MASSIVE"
        or first.source != "MASSIVE"
        or previous.data_mode != "LIVE"
        or first.data_mode != "LIVE"
        or previous.data_quality != "HISTORICAL"
        or first.data_quality != "HISTORICAL"
        or previous.ticker != first.ticker
        or previous.adjusted != first.adjusted
    ):
        return {
            "status": "UNSCORABLE",
            "reason": "CONFLICTING_OUTCOME_PROVENANCE",
            "opening_return": None,
            "target_available_at": None,
        }
    target_end = opening + timedelta(minutes=OPENING_MINUTES)
    if first.ingestion_timestamp < target_end or previous.ingestion_timestamp < previous_close:
        return {
            "status": "UNSCORABLE",
            "reason": "UNCOMPLETED_BAR",
            "opening_return": None,
            "target_available_at": None,
        }
    with localcontext() as context:
        context.prec = 256
        value = (first.close - previous.close) / previous.close
    return {
        "status": "SCORABLE_OUTCOME_ONLY",
        "previous_close": str(previous.close),
        "reference_bar_start": previous.source_timestamp.isoformat(),
        "reference_close_at": previous_close.isoformat(),
        "first_5m_close": str(first.close),
        "target_bar_start": first.source_timestamp.isoformat(),
        "target_bar_completed_at": target_end.isoformat(),
        "target_available_at": max(first.ingestion_timestamp, target_end).isoformat(),
        "opening_return": str(value),
        "adjusted": first.adjusted,
        "point_in_time_revision_history_verified": False,
        "outcome_is_decision_feature": False,
    }
