"""Replay immutable real provider inputs; never current evidence or synthetic success."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.database import Database
from app.models.data import NewsEvent, TokenMetadata, TokenObservation
from app.models.trust import TrustAssessment, TrustEpisode, TrustSample
from app.services.calendar import USEquityCalendar
from app.services.trust import TrustService
from app.services.trust_evidence import LiquidityEvidenceService, NewsAlignmentService


@pytest.fixture
def captured():
    raw = json.loads(
        (Path(__file__).parents[1] / "fixtures/trust/real_remediation_capture.json").read_text()
    )
    assert raw["evidence_kind"] == "REAL_CAPTURED_INPUTS_REPLAY_NOT_CURRENT_OR_CALIBRATION"
    return raw


def test_real_news_prefix_replay_covers_window_not_full_history(captured):
    assessment = TrustAssessment.model_validate(captured["assessment"])
    articles = [NewsEvent.model_validate(row) for row in captured["news_events"]]
    assert len(articles) == 100 and all(a.data_mode == "LIVE" for a in articles)
    at = assessment.evaluated_at
    result = NewsAlignmentService().evaluate(
        articles,
        ticker="NVDA",
        company="Nvidia",
        deviation=Decimal(0),
        at=at,
        mode="LIVE",
        complete=False,
        prefix_start=articles[-1].published_timestamp,
    )
    assert result.coverage == "COMPLETE_REQUESTED_WINDOW" and result.state == "RELEVANT_NEWS"
    assert "BOUNDED_NEWS_HISTORY" in result.reason_codes
    assert "SOURCE_UPDATED_HOURLY_NOT_REALTIME_NEWS" in result.reason_codes
    assert not result.absence_proves_no_information and not result.provider_llm_sentiment_used
    # Newly obtained articles were NOT known at publication time; replay cannot backdate them.
    past = datetime(2026, 10, 6, 17, 0, tzinfo=UTC)
    unknown_then = NewsAlignmentService().evaluate(
        articles,
        ticker="NVDA",
        company="Nvidia",
        deviation=Decimal(0),
        at=past,
        mode="LIVE",
        complete=False,
        prefix_start=articles[-1].published_timestamp,
    )
    assert unknown_then.coverage == "PARTIAL" and unknown_then.article_ids == []


def test_real_missing_reference_liquidity_and_history_replay_fails_closed(
    captured, tmp_path, monkeypatch
):
    def prohibited(*args, **kwargs):
        raise AssertionError("Captured replay must make no external or execution call")

    monkeypatch.setattr(httpx.Client, "send", prohibited)
    original = TrustAssessment.model_validate(captured["assessment"])
    at = original.evaluated_at
    db = Database(f"sqlite:///{tmp_path}/real-replay.db")
    db.initialize()
    try:
        service = TrustService(
            SimpleNamespace(mode="LIVE", calendar=USEquityCalendar(mode="LIVE")), db
        )
        tokens = [TokenMetadata.model_validate(row) for row in captured["token_metadata"]]
        prices = [TokenObservation.model_validate(row) for row in captured["token_observations"]]
        articles = [NewsEvent.model_validate(row) for row in captured["news_events"]]
        for token in tokens:
            info = max(
                (p for p in prices if p.kind == "PRICE_INFO" and p.contract == token.contract),
                key=lambda p: p.source_timestamp,
            )
            assert info.volume_unit == "USD" and info.provider_metadata.get("liquidity") is None
            assert (
                LiquidityEvidenceService().evaluate(token, info, at, "LIVE").status == "UNAVAILABLE"
            )
            replay = service.evaluate_representation(
                token,
                info,
                None,
                info,
                articles,
                original.regime,
                at,
                complete=False,
                news_prefix_start=articles[-1].published_timestamp,
            )
            assert replay.classification == "INSUFFICIENT_EVIDENCE" and replay.confidence is None
            assert replay.economic_comparison is None and replay.features is None
            assert replay.baseline.sample_count == 0 and replay.baseline.status == "INSUFFICIENT"
            assert replay.analogues.retrieved_sample_count == 0
        for model in [TrustSample, TrustEpisode]:
            rows, truncated = service.repository.history(
                model, mode="LIVE", ticker="NVDA", at=at, start=at - timedelta(days=180)
            )
            assert rows == [] and not truncated
        service.repository.save(original)
        assert service.repository.get(original.assessment_id, "LIVE") == original
        assert service.repository.get(original.assessment_id, "DEMO") is None
        assert not original.transaction_broadcast and not original.execution_ready
        assert not original.llm_authoritative and original.trust_gate == "BLOCKED"
    finally:
        db.close()
