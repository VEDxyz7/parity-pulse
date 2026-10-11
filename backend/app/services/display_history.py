"""Bounded local display capture reader. No providers, databases or credentials."""

import json
from pathlib import Path

from app.config import ROOT_DIR
from app.models.display_history import DisplayHistory

HISTORY_PATH = ROOT_DIR / "data/display/equity-history.json"


def load_history(ticker, *, path=None):
    if ticker not in {"NVDA", "AAPL"}:
        raise ValueError("Unsupported display ticker")
    try:
        capture = Path(path or HISTORY_PATH)
        if capture.stat().st_size > 2_000_000:
            raise ValueError("Display capture too large")
        raw = json.loads(capture.read_text())
        result = DisplayHistory.model_validate(raw[ticker])
        if result.ticker != ticker:
            raise ValueError("Capture ticker mismatch")
        return result
    except (OSError, ValueError, KeyError, TypeError):
        return DisplayHistory(
            ticker=ticker,
            status="UNAVAILABLE",
            limitations=["No validated historical display capture. Scenario prices are separate."],
        )
