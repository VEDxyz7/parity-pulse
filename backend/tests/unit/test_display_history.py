"""Display capture is historical and cannot become Trust/reference evidence."""

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.data import EquityObservation
from app.models.display_history import DisplayHistory
from app.services.display_history import load_history


def capture():
    row = EquityObservation(
        ticker="NVDA",
        source="ALPACA",
        provider_identifier="NVDA",
        source_timestamp=datetime(2026, 10, 5, 13, 30, tzinfo=UTC),
        ingestion_timestamp=datetime(2026, 10, 11, tzinfo=UTC),
        data_mode="LIVE",
        data_quality="HISTORICAL",
        kind="BAR",
        interval="5minute",
        close="100",
        adjusted=False,
        feed="sip",
    )
    return DisplayHistory(
        ticker="NVDA",
        status="AVAILABLE",
        observations=[row],
        captured_at=datetime(2026, 10, 11, tzinfo=UTC),
    ).model_dump(mode="json")


def test_validated_local_capture_is_never_production_reference(tmp_path):
    path = tmp_path / "history.json"
    path.write_text(json.dumps({"NVDA": capture()}))
    result = load_history("NVDA", path=path)
    assert result.status == "AVAILABLE"
    assert result.production_reference_eligible is False
    assert result.observations[0].data_quality == "HISTORICAL"
    assert load_history("AAPL", path=path).status == "UNAVAILABLE"


@pytest.mark.parametrize(
    "field,value",
    [
        ("data_quality", "LIVE"),
        ("data_mode", "DEMO"),
        ("ticker", "AAPL"),
        ("source", "BINANCE"),
        ("feed", "boats"),
        ("adjusted", True),
        ("source_timestamp", None),
        ("source_timestamp", "2026-10-04T13:30:00Z"),
        ("source_timestamp", "2026-10-05T13:31:00Z"),
        ("source_timestamp", "2026-10-05T12:30:00Z"),
        ("close", None),
    ],
)
def test_rejects_identity_quality_and_session_mismatch(field, value):
    raw = capture()
    raw["observations"][0][field] = value
    with pytest.raises(ValidationError):
        DisplayHistory.model_validate(raw)


def test_rejects_duplicates_missing_capture_time_and_promotion():
    for patch in (
        {"production_reference_eligible": True},
        {"captured_at": None},
        {"status": "UNAVAILABLE"},
    ):
        with pytest.raises(ValidationError):
            DisplayHistory.model_validate({**capture(), **patch})
    raw = capture()
    raw["observations"] *= 2
    with pytest.raises(ValidationError):
        DisplayHistory.model_validate(raw)


@pytest.mark.parametrize("content", ['{"NVDA": null}', "not json", '{"AAPL": {}}'])
def test_missing_or_corrupt_capture_fails_to_empty_history(tmp_path, content):
    path = tmp_path / "history.json"
    assert load_history("NVDA", path=path).status == "UNAVAILABLE"
    path.write_text(content)
    assert load_history("NVDA", path=path).observations == []


def test_ticker_swapping_and_oversized_capture_rejected(tmp_path):
    raw = capture()
    raw["ticker"] = "AAPL"
    raw["observations"][0]["ticker"] = "AAPL"
    path = tmp_path / "history.json"
    path.write_text(json.dumps({"NVDA": raw}))
    assert load_history("NVDA", path=path).status == "UNAVAILABLE"
    path.write_text(" " * 2_000_001)
    assert load_history("NVDA", path=path).status == "UNAVAILABLE"
    with pytest.raises(ValueError):
        load_history("OTHER", path=path)


def test_display_api_is_closed_to_unknown_tickers_and_does_not_fetch(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import display_history

    calls = []

    def local_read(ticker):
        calls.append(ticker)
        return DisplayHistory(ticker=ticker, status="UNAVAILABLE")

    monkeypatch.setattr(display_history, "load_history", local_read)
    app = FastAPI()
    app.include_router(display_history.router)
    with TestClient(app) as client:
        response = client.get("/api/display-history/NVDA")
        assert response.status_code == 200
        assert response.json()["production_reference_eligible"] is False
        assert client.get("/api/display-history/OTHER").status_code == 422
        assert client.post("/api/display-history/NVDA").status_code == 405
    assert calls == ["NVDA"]


def test_display_movement_is_decimal_and_recomputed_from_observed_closes():
    raw = capture()
    second = {
        **raw["observations"][0],
        "source_timestamp": "2026-10-05T13:35:00Z",
        "close": "102.25",
    }
    third = {**second, "source_timestamp": "2026-10-06T13:30:00Z", "close": "105.00"}
    raw["observations"].extend([second, third])
    # Caller-supplied percentages cannot override the validated bars.
    raw["periods"][0]["change_fraction"] = "99"
    result = DisplayHistory.model_validate(raw)
    periods = {p.period: p for p in result.periods}
    assert str(periods["1W"].change_fraction) == "0.05"
    assert periods["1W"].bar_count == 3
    assert periods["1D"].bar_count == 1
    assert periods["1D"].change_fraction == 0
    assert periods["1D"].first_close == periods["1W"].last_close
    assert result.production_reference_eligible is False


def test_unavailable_display_history_has_no_movement_metrics():
    assert DisplayHistory(ticker="NVDA", status="UNAVAILABLE").periods == []
