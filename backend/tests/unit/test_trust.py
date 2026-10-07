"""Synthetic, exact analytical scenarios; not provider entitlement or empirical calibration."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.clients.common import ProviderError
from app.database import Database
from app.models.data import NewsEvent
from app.models.trust import TrustEpisode, TrustFeatures, TrustSample
from app.providers.demo import load_data_fixture
from app.repositories.trust import TrustRepository
from app.services.calendar import USEquityCalendar
from app.services.normalization import comparable_economics, effective_price_per_share
from app.services.trust import TrustService
from app.services.trust_classifier import TrustClassifier
from app.services.trust_evidence import (
    IndependentReferenceService,
    LiquidityEvidenceService,
    MarketRegimeService,
    NewsAlignmentService,
)
from app.services.trust_history import (
    AnalogueService,
    BaselineService,
    EpisodeBuilder,
    distribution,
)

NOW = datetime(2026, 10, 6, 16, tzinfo=UTC)
D = Decimal


def inputs():
    fixture = load_data_fixture()
    token = next(t for t in fixture["metadata"] if t.ticker == "NVDA").model_copy(
        update={
            "company_name": "Nvidia",
            "ingestion_timestamp": NOW,
            "source_timestamp": NOW,
            "token_to_share_ratio": D("0.5"),
        }
    )
    price = next(t for t in fixture["tokens"] if t.ticker == "NVDA").model_copy(
        update={
            "token_price": D("50"),
            "token_to_share_ratio": D("0.5"),
            "source_timestamp": NOW,
            "ingestion_timestamp": NOW,
            "source": "DEMO_MARKET",
            "kind": "PRICE_INFO",
            "volume": D("1000"),
            "volume_unit": "USD",
            "trade_count": 20,
            "provider_metadata": {
                "liquidity": "5000",
                "buyVolume24H": "600",
                "sellVolume24H": "400",
                "buyTxs24H": 12,
                "sellTxs24H": 8,
            },
        }
    )
    equity = next(t for t in fixture["equities"] if t.ticker == "NVDA").model_copy(
        update={
            "source_timestamp": NOW,
            "ingestion_timestamp": NOW,
            "price": D("100"),
            "close": D("100"),
        }
    )
    regime = MarketRegimeService(USEquityCalendar(mode="DEMO")).evaluate(NOW)
    return token, price, equity, regime


def sample(
    at=NOW,
    *,
    deviation="0.01",
    volume="1000",
    liquidity="5000",
    persistence="600",
    news="NO_RELEVANT_NEWS",
    ticker="NVDA",
    regime="REGULAR",
    ratio="0.5",
    mode="DEMO",
):
    with localcontext() as context:
        context.prec = 256
        features = TrustFeatures(
            effective_price_per_share_usd=D("100") * (1 + D(deviation)),
            comparable_token_value_usd=D("50"),
            deviation=D(deviation),
            absolute_deviation=abs(D(deviation)),
            volume_24h_usd=D(volume),
            liquidity_usd=D(liquidity),
            persistence_seconds=D(persistence),
            time_to_open_seconds=D("77400"),
            starting_deviation=D(deviation),
            ending_deviation=D(deviation),
            news_state=news,
            asof=at,
            available_at=at,
        )
    return TrustSample(
        sample_id=at.isoformat(),
        data_mode=mode,
        ticker=ticker,
        issuer="synthetic-issuer",
        chain_id="DEMO",
        contract="demo:NVDA",
        regime=regime,
        ratio=D(ratio),
        reference_kind="CURRENT",
        features=features,
    )


def history(*, outcome="REVERSED", news="NO_RELEVANT_NEWS", count=40):
    episodes = []
    for i in range(count):
        at = NOW - timedelta(days=i + 1)
        with localcontext() as context:
            context.prec = 256
            deviation = D("0.005") + D(i % 10) / 1000
        point = sample(
            at,
            deviation=str(deviation),
            volume=str(1000 + i * 10),
            liquidity=str(1000 + i * 50),
            persistence=str(300 + i * 20),
            news=news,
        )
        episodes.append(
            TrustEpisode(
                episode_id=f"synthetic-{i}",
                sample=point,
                started_at=at - timedelta(minutes=15),
                ended_at=at + timedelta(minutes=15),
                outcome_available_at=at + timedelta(minutes=15),
                outcome_deviation=D("0") if outcome == "REVERSED" else deviation,
                outcome=outcome,
                observation_count=16,
                evidence_kind="SYNTHETIC_TEST",
            )
        )
    return episodes


def news_event(headline="Nvidia raises guidance", **changes):
    data = dict(
        source="DEMO_NEWS",
        provider_identifier="synthetic-news",
        data_mode="DEMO",
        data_quality="DEMO",
        ticker="NVDA",
        headline=headline,
        publisher="Synthetic publisher",
        url="https://example.test/news",
        published_timestamp=NOW - timedelta(minutes=10),
        source_timestamp=NOW - timedelta(minutes=10),
        ingestion_timestamp=NOW,
    )
    data.update(changes)
    return NewsEvent(**data)


@pytest.mark.parametrize(
    "ratio,price,expected",
    [("1", "100", "100"), ("0.5", "50", "100"), ("2", "200", "100"), ("0.01", "1", "100")],
)
def test_shared_normalization_and_comparable_units(ratio, price, expected):
    result = comparable_economics(price, ratio, "100")
    assert result["effective_price_per_share_usd"] == D(expected)
    assert result["comparable_token_value_usd"] == D(price)
    assert result["deviation"] == 0
    assert effective_price_per_share(price, ratio, presentation=True) == D(expected)


@pytest.mark.parametrize("bad", [None, "0", "-1", "NaN", "Infinity", 0.5, True, "1e99"])
def test_invalid_or_missing_ratio_fails_closed(bad):
    with pytest.raises((ValueError, TypeError)):
        comparable_economics("50", bad, "100")


def test_precision_and_positive_negative_deviation():
    assert comparable_economics("55", "0.5", "100")["deviation"] == D("0.1")
    assert comparable_economics("45", "0.5", "100")["deviation"] == D("-0.1")
    assert comparable_economics("150.9876543210987654321", "1.000000000000000001", "149")[
        "comparable_token_value_usd"
    ] == D("149.000000000000000149")
    assert effective_price_per_share("1", "3", presentation=True) == D("0.333333333333333334")


@pytest.mark.parametrize(
    "moment,state,early,reopen",
    [
        ("2026-10-06T16:00:00+00:00", "REGULAR", False, False),
        ("2026-10-06T12:00:00+00:00", "PREMARKET", False, False),
        ("2026-10-06T21:00:00+00:00", "POSTMARKET", False, False),
        ("2026-10-07T03:00:00+00:00", "WEEKDAY_OVERNIGHT", False, False),
        ("2026-10-10T16:00:00+00:00", "WEEKEND", False, False),
        ("2026-11-26T16:00:00+00:00", "HOLIDAY", False, False),
        ("2026-11-27T17:30:00+00:00", "REGULAR", True, True),
        ("2026-11-27T18:00:00+00:00", "POSTMARKET", True, True),
        ("2026-09-08T12:00:00+00:00", "PREMARKET", False, True),
    ],
)
def test_calendar_regimes_reuse_verified_schedule(moment, state, early, reopen):
    at = datetime.fromisoformat(moment)
    regime = MarketRegimeService(USEquityCalendar(mode="DEMO")).evaluate(at)
    assert regime.state == state and regime.early_close is early and regime.reopening is reopen
    assert regime.previous_regular_close <= at
    assert regime.scheduled_not_halt_status is True


def test_actual_previous_close_holiday_and_early_close_not_friday_guess():
    service = MarketRegimeService(USEquityCalendar(mode="DEMO"))
    holiday = service.evaluate(datetime(2026, 7, 4, 16, tzinfo=UTC))
    assert holiday.previous_regular_close == datetime(2026, 7, 2, 20, tzinfo=UTC)
    early = service.evaluate(datetime(2026, 11, 28, 16, tzinfo=UTC))
    assert early.previous_regular_close == datetime(2026, 11, 27, 18, tzinfo=UTC)
    assert (
        service.evaluate(datetime(2026, 9, 7, 16, tzinfo=UTC)).baseline_bucket == "MULTI_DAY_REOPEN"
    )
    with pytest.raises(ProviderError):
        service.evaluate(datetime(2025, 10, 6, tzinfo=UTC))


@pytest.mark.parametrize(
    "override,reason",
    [
        ({"source_timestamp": NOW - timedelta(seconds=121)}, "REFERENCE_STALE_OR_FUTURE"),
        ({"source_timestamp": NOW - timedelta(seconds=31)}, "TIMESTAMP_SKEW_EXCEEDED"),
        ({"source_timestamp": NOW + timedelta(seconds=1)}, "REFERENCE_STALE_OR_FUTURE"),
        ({"kind": "BAR"}, "CURRENT_REFERENCE_REQUIRED"),
        ({"data_quality": "HISTORICAL"}, "CURRENT_REFERENCE_NOT_VERIFIED"),
        ({"data_quality": "UNKNOWN"}, "CURRENT_REFERENCE_NOT_VERIFIED"),
        ({"source": "BINANCE_RWA"}, "REFERENCE_SOURCE_NOT_INDEPENDENT_VERIFIED"),
        ({"ingestion_timestamp": NOW + timedelta(seconds=1)}, "REFERENCE_NOT_YET_AVAILABLE"),
        ({"ticker": "AAPL"}, "REFERENCE_IDENTITY_OR_MODE_CONFLICT"),
    ],
)
def test_reference_fail_closed(override, reason):
    token, price, equity, regime = inputs()
    result = IndependentReferenceService().evaluate(
        token, price, equity.model_copy(update=override), regime, NOW, "DEMO"
    )
    assert result.status != "AVAILABLE" and reason in result.reason_codes


def test_reference_available_missing_token_missing_reference_cross_mode():
    token, price, equity, regime = inputs()
    service = IndependentReferenceService()
    assert service.evaluate(token, price, equity, regime, NOW, "DEMO").status == "AVAILABLE"
    assert service.evaluate(token, price, None, regime, NOW, "DEMO").status == "UNAVAILABLE"
    assert service.evaluate(token, None, equity, regime, NOW, "DEMO").status == "UNAVAILABLE"
    assert (
        service.evaluate(
            token, price.model_copy(update={"token_price": None}), equity, regime, NOW, "DEMO"
        ).status
        == "UNAVAILABLE"
    )
    assert service.evaluate(token, price, equity, regime, NOW, "LIVE").status != "AVAILABLE"


def test_closed_session_reference_is_explicit_historical_and_actual_close_bound():
    token, price, equity, _ = inputs()
    at = datetime(2026, 11, 28, 16, tzinfo=UTC)
    regime = MarketRegimeService(USEquityCalendar(mode="DEMO")).evaluate(at)
    token = token.model_copy(update={"ingestion_timestamp": at, "source_timestamp": None})
    price = price.model_copy(update={"source_timestamp": at, "ingestion_timestamp": at})
    equity = equity.model_copy(
        update={
            "kind": "REGULAR_CLOSE",
            "interval": "1minute",
            "source_timestamp": regime.previous_regular_close - timedelta(minutes=1),
            "ingestion_timestamp": at,
        }
    )
    service = IndependentReferenceService()
    result = service.evaluate(token, price, equity, regime, at, "DEMO")
    assert result.status == "AVAILABLE" and result.reference_asof == regime.previous_regular_close
    assert result.timestamp_skew_seconds > 120
    assert result.observation.kind == "REGULAR_CLOSE"
    assert (
        service.evaluate(
            token, price, equity.model_copy(update={"kind": "BAR"}), regime, at, "DEMO"
        ).status
        != "AVAILABLE"
    )


@pytest.mark.parametrize(
    "override,status",
    [
        ({"kind": "TRADE"}, "AMBIGUOUS"),
        ({"kind": "CANDLE"}, "AMBIGUOUS"),
        ({"volume_unit": "UNKNOWN"}, "AMBIGUOUS"),
        ({"volume_unit": "TOKEN"}, "AMBIGUOUS"),
        ({"source": "MASSIVE"}, "CONFLICTING"),
        ({"contract": "demo:OTHER"}, "CONFLICTING"),
        ({"source_timestamp": NOW - timedelta(seconds=121)}, "STALE"),
        ({"provider_metadata": {"liquidity": "NaN"}}, "CONFLICTING"),
        ({"provider_metadata": {"liquidity": 1.2}}, "CONFLICTING"),
        ({"provider_metadata": {}}, "UNAVAILABLE"),
    ],
)
def test_liquidity_excludes_unverified_units_and_malformed_values(override, status):
    token, price, _, _ = inputs()
    assert (
        LiquidityEvidenceService()
        .evaluate(token, price.model_copy(update=override), NOW, "DEMO")
        .status
        == status
    )


def test_verified_liquidity_preserves_exact_units_and_activity():
    token, price, _, _ = inputs()
    result = LiquidityEvidenceService().evaluate(token, price, NOW, "DEMO")
    assert result.status == "AVAILABLE" and result.volume_24h_usd == D("1000")
    assert result.liquidity_usd == D("5000") and result.trade_count_24h == 20
    assert result.buy_volume_24h_usd == D("600") and result.sell_transactions_24h == 8
    assert result.estimated_slippage == "UNAVAILABLE"
    assert LiquidityEvidenceService().evaluate(token, None, NOW, "DEMO").status == "UNAVAILABLE"


@pytest.mark.parametrize(
    "headlines,complete,state",
    [
        ([], True, "NO_RELEVANT_NEWS"),
        (["Nvidia announces a meeting"], True, "RELEVANT_NEWS"),
        (["Nvidia raises guidance"], True, "CORROBORATING"),
        (["Nvidia cuts outlook"], True, "CONFLICTING"),
        (["Nvidia raises guidance", "Nvidia cuts guidance"], True, "CONFLICTING"),
        (["Nvidia raises guidance"], False, "PARTIAL"),
        (["Unrelated company raises guidance"], True, "RELEVANT_NEWS"),
    ],
)
def test_news_temporal_direction_and_partial_coverage(headlines, complete, state):
    events = [news_event(h, provider_identifier=str(i)) for i, h in enumerate(headlines)]
    result = NewsAlignmentService().evaluate(
        events,
        ticker="NVDA",
        company="Nvidia",
        deviation=D("0.1"),
        at=NOW,
        mode="DEMO",
        complete=complete,
    )
    assert result.state == state
    assert (
        result.absence_proves_no_information is False
        and result.provider_llm_sentiment_used is False
    )


def test_news_future_publication_first_seen_old_wrong_stock_and_mode_excluded():
    valid = news_event()
    invalid = [
        valid.model_copy(update=change)
        for change in [
            {"published_timestamp": NOW + timedelta(seconds=1)},
            {"ingestion_timestamp": NOW + timedelta(seconds=1)},
            {"ticker": "AAPL"},
            {"published_timestamp": NOW - timedelta(hours=2)},
            {"data_mode": "LIVE"},
        ]
    ]
    result = NewsAlignmentService().evaluate(
        [valid, *invalid],
        ticker="NVDA",
        company="Nvidia",
        deviation=D("0.1"),
        at=NOW,
        mode="DEMO",
        complete=True,
    )
    assert result.article_ids == ["synthetic-news"]
    negative = NewsAlignmentService().evaluate(
        [news_event("Nvidia cuts guidance")],
        ticker="NVDA",
        company="Nvidia",
        deviation=D("-0.1"),
        at=NOW,
        mode="DEMO",
        complete=True,
    )
    assert negative.state == "CORROBORATING"


def test_decimal_baseline_statistics_and_minimum_count():
    stats = distribution([D("1"), D("2"), D("3"), D("4")])
    assert stats.mean == D("2.5") and stats.median == D("2.5") and stats.mad == 1
    assert stats.quantiles["25"] == D("1.75") and stats.quantiles["95"] == D("3.85")
    baseline = BaselineService()
    current = sample()
    assert baseline.evaluate(history(count=29), current, NOW).status == "INSUFFICIENT"
    result = baseline.evaluate(history(count=30), current, NOW)
    assert result.status == "SUFFICIENT" and result.sample_count == 30
    assert result.deviation.standard_deviation > 0 and result.z_score is not None
    assert result.research_coefficients_used is False
    assert baseline.evaluate(history(), current, NOW, truncated=True).status == "TRUNCATED"


def test_baseline_stock_regime_ratio_issuer_mode_and_future_leakage():
    episodes = history(count=30)
    current = sample()
    for change in [
        {"ticker": "AAPL"},
        {"regime": "WEEKEND"},
        {"ratio": D("1")},
        {"issuer": "other"},
        {"data_mode": "LIVE"},
        {"contract": "other"},
    ]:
        assert (
            BaselineService()
            .evaluate(episodes, current.model_copy(update=change), NOW)
            .sample_count
            == 0
        )
    future = episodes[0].model_copy(
        update={"episode_id": "future", "outcome_available_at": NOW + timedelta(seconds=1)}
    )
    assert BaselineService().evaluate([*episodes, future], current, NOW).sample_count == 30
    old = episodes[0].model_copy(update={"sample": sample(NOW - timedelta(days=181))})
    assert BaselineService().evaluate([*episodes, old], current, NOW).sample_count == 30
    bad = episodes[0].model_copy(update={"sample": sample(NOW + timedelta(seconds=1))})
    assert BaselineService().evaluate([*episodes, bad], current, NOW).sample_count == 30


def test_degenerate_baseline_does_not_create_infinite_z_score():
    episodes = [e.model_copy(update={"sample": sample(e.sample.features.asof)}) for e in history()]
    result = BaselineService().evaluate(episodes, sample(), NOW)
    assert result.status == "DEGENERATE" and result.z_score is None


def test_analogue_retrieval_deterministic_future_outcome_excluded():
    episodes = history()
    current = sample(deviation="0.02")
    baseline = BaselineService().evaluate(episodes, current, NOW)
    service = AnalogueService()
    first = service.evaluate(episodes, current, baseline, NOW)
    second = service.evaluate(list(reversed(episodes)), current, baseline, NOW)
    assert first.model_dump_json() == second.model_dump_json()
    assert first.status == "SUFFICIENT" and first.retrieved_sample_count == 3
    changed = [
        e.model_copy(update={"outcome": "PERSISTED", "outcome_deviation": D("9999")})
        for e in episodes
    ]
    third = service.evaluate(changed, current, baseline, NOW)
    assert [(m["episode_id"], m["similarity"]) for m in first.matches] == [
        (m["episode_id"], m["similarity"]) for m in third.matches
    ]
    future = episodes[0].model_copy(
        update={
            "episode_id": "future-perfect",
            "sample": current,
            "outcome_available_at": NOW + timedelta(seconds=1),
        }
    )
    assert (
        service.evaluate([*episodes, future], current, baseline, NOW).model_dump()
        == first.model_dump()
    )
    assert service.evaluate(episodes[:2], current, baseline, NOW).status == "INSUFFICIENT"


def test_episode_builder_completion_coverage_dedup_and_immutable_availability():
    start = NOW - timedelta(minutes=30)
    points = [sample(start + timedelta(minutes=i * 2)) for i in range(15)]
    builder = EpisodeBuilder()
    assert builder.build(points, NOW - timedelta(seconds=1)) == []
    result = builder.build([*points, points[-1]], NOW)
    assert len(result) == 1 and result[0].observation_count == 15
    assert result[0].sample.features.asof <= start + timedelta(minutes=15)
    assert result[0].outcome_available_at == NOW
    assert builder.build(points[:3] + points[10:], NOW) == []
    with pytest.raises(ValidationError):
        TrustEpisode.model_validate(dict(result[0].model_dump(), outcome_available_at=start))


@pytest.mark.parametrize("state", ["NORMAL", "LIKELY_NOISE", "LIKELY_INFORMATION"])
def test_all_three_deterministic_classifications(state):
    token, price, equity, regime = inputs()
    reference = IndependentReferenceService().evaluate(token, price, equity, regime, NOW, "DEMO")
    liquidity = LiquidityEvidenceService().evaluate(token, price, NOW, "DEMO")
    info = state == "LIKELY_INFORMATION"
    current = sample(
        deviation="0.007" if state == "NORMAL" else "0.02",
        volume="3000" if info else "1000" if state == "NORMAL" else "100",
        liquidity="5000" if info or state == "NORMAL" else "10",
        persistence="1500" if info else "600" if state == "NORMAL" else "60",
        news="CORROBORATING" if info else "NO_RELEVANT_NEWS",
    )
    episodes = history(
        outcome="PERSISTED" if info else "REVERSED", news=current.features.news_state
    )
    baseline = BaselineService().evaluate(episodes, current, NOW)
    analogues = AnalogueService().evaluate(episodes, current, baseline, NOW)
    news = NewsAlignmentService().evaluate(
        [news_event()] if info else [],
        ticker="NVDA",
        company="Nvidia",
        deviation=current.features.deviation,
        at=NOW,
        mode="DEMO",
        complete=True,
    )
    classifier = TrustClassifier()
    args = dict(
        reference=reference,
        liquidity=liquidity,
        news=news,
        baseline=baseline,
        analogues=analogues,
        features=current.features,
        mode="DEMO",
    )
    first = classifier.classify(**args)
    assert first == classifier.classify(**args)
    assert first[0] == state and first[1] == "LOW"
    assert first[2]
    for override in [
        dict(features=None),
        dict(reference=reference.model_copy(update={"status": "UNAVAILABLE"})),
        dict(baseline=baseline.model_copy(update={"status": "INSUFFICIENT"})),
        dict(analogues=analogues.model_copy(update={"status": "INSUFFICIENT"})),
        dict(news=news.model_copy(update={"coverage": "PARTIAL"})),
        dict(liquidity=liquidity.model_copy(update={"status": "AMBIGUOUS"})),
    ]:
        assert classifier.classify(**dict(args, **override))[0] == "INSUFFICIENT_EVIDENCE"


def test_trust_repository_mode_isolation_and_availability(tmp_path):
    db = Database(f"sqlite:///{tmp_path}/trust.db")
    db.initialize()
    repo = TrustRepository(db)
    point = sample()
    repo.save(point)
    repo.save(
        point.model_copy(
            update={
                "features": point.features.model_copy(
                    update={"available_at": NOW + timedelta(minutes=1)}
                )
            }
        )
    )
    stored, truncated = repo.history(
        TrustSample, mode="DEMO", ticker="NVDA", at=NOW, start=NOW - timedelta(days=1)
    )
    assert stored == [point] and not truncated
    assert (
        repo.history(
            TrustSample, mode="LIVE", ticker="NVDA", at=NOW, start=NOW - timedelta(days=1)
        )[0]
        == []
    )
    assert (
        repo.history(
            TrustSample,
            mode="DEMO",
            ticker="NVDA",
            at=NOW - timedelta(seconds=1),
            start=NOW - timedelta(days=1),
        )[0]
        == []
    )
    with pytest.raises(ValueError):
        repo.history(TrustSample, mode="INVALID", ticker="NVDA", at=NOW, start=NOW)
    db.close()


def test_composed_assessment_exact_features_and_persistence_with_existing_providers(tmp_path):
    token, price, equity, _ = inputs()
    db = Database(f"sqlite:///{tmp_path}/composed.db")
    db.initialize()
    layer = SimpleNamespace(mode="DEMO", calendar=USEquityCalendar(mode="DEMO"))
    service = TrustService(layer, db, clock=lambda: NOW)
    result = service.evaluate_representation(
        token, price, equity, price, [], service.regimes.evaluate(NOW), NOW, complete=True
    )
    assert result.economic_comparison["deviation"] == 0 and result.features is not None
    assert (
        result.classification == "INSUFFICIENT_EVIDENCE"
        and "BASELINE_INSUFFICIENT" in result.reason_codes
    )
    points, _ = service.repository.history(
        TrustSample, mode="DEMO", ticker="NVDA", at=NOW, start=NOW - timedelta(days=1)
    )
    assert len(points) == 1
    assert result.baseline.sample_count == 0
    db.close()


def test_repeating_decimal_features_preserve_precision_without_context_rounding():
    economics = comparable_economics("1", "3", "7")
    features = TrustFeatures(
        **economics,
        volume_24h_usd=D("1"),
        liquidity_usd=D("1"),
        persistence_seconds=D("0"),
        time_to_open_seconds=D("1"),
        starting_deviation=economics["deviation"],
        ending_deviation=economics["deviation"],
        news_state="NO_RELEVANT_NEWS",
        asof=NOW,
        available_at=NOW,
    )
    assert len(features.deviation.as_tuple().digits) == 256
    assert features.absolute_deviation == features.deviation.copy_abs()
    assert TrustFeatures.model_validate_json(features.model_dump_json()) == features


@pytest.mark.parametrize(
    "headline",
    [
        "Nvidia may raise guidance",
        "Nvidia never raises guidance",
        "Nvidia expects earnings, cuts outlook may follow",
    ],
)
def test_speculation_negation_not_directional_news(headline):
    result = NewsAlignmentService().evaluate(
        [news_event(headline)],
        ticker="NVDA",
        company="Nvidia",
        deviation=D("0.1"),
        at=NOW,
        mode="DEMO",
        complete=True,
    )
    assert result.directional_state == "UNKNOWN"


def test_classifier_conflicts_and_mixed_evidence_never_force_a_classification():
    token, price, equity, regime = inputs()
    point = sample(deviation="0.02", volume="1100", persistence="600")
    episodes = history()
    baseline = BaselineService().evaluate(episodes, point, NOW)
    args = dict(
        reference=IndependentReferenceService().evaluate(token, price, equity, regime, NOW, "DEMO"),
        liquidity=LiquidityEvidenceService().evaluate(token, price, NOW, "DEMO"),
        baseline=baseline,
        analogues=AnalogueService().evaluate(episodes, point, baseline, NOW),
        features=point.features,
        mode="DEMO",
    )
    for events in [[], [news_event("Nvidia cuts guidance")]]:
        news = NewsAlignmentService().evaluate(
            events,
            ticker="NVDA",
            company="Nvidia",
            deviation=D("0.02"),
            at=NOW,
            mode="DEMO",
            complete=True,
        )
        assert TrustClassifier().classify(**args, news=news)[0] == "INSUFFICIENT_EVIDENCE"


def test_live_closed_reference_retains_historical_quality_and_actual_close():
    token, price, equity, _ = inputs()
    at = datetime(2026, 11, 28, 16, tzinfo=UTC)
    regime = MarketRegimeService(USEquityCalendar()).evaluate(at)
    token = token.model_copy(
        update={
            "source": "BINANCE_RWA",
            "data_mode": "LIVE",
            "data_quality": "UNKNOWN",
            "chain_id": "56",
            "contract": "0x" + "a" * 40,
            "ingestion_timestamp": at,
            "source_timestamp": None,
        }
    )
    price = price.model_copy(
        update={
            "source": "BINANCE_MARKET",
            "data_mode": "LIVE",
            "data_quality": "LIVE",
            "chain_id": token.chain_id,
            "contract": token.contract,
            "source_timestamp": at,
            "ingestion_timestamp": at,
        }
    )
    equity = equity.model_copy(
        update={
            "source": "MASSIVE",
            "data_mode": "LIVE",
            "data_quality": "HISTORICAL",
            "kind": "REGULAR_CLOSE",
            "interval": "1minute",
            "source_timestamp": regime.previous_regular_close - timedelta(minutes=1),
            "ingestion_timestamp": at,
        }
    )
    service = IndependentReferenceService()
    result = service.evaluate(token, price, equity, regime, at, "LIVE")
    assert result.status == "AVAILABLE"
    assert result.observation.data_quality == "HISTORICAL"
    assert result.reference_asof == datetime(2026, 11, 27, 18, tzinfo=UTC)
    assert (
        service.evaluate(
            token, price, equity.model_copy(update={"data_quality": "LIVE"}), regime, at, "LIVE"
        ).status
        != "AVAILABLE"
    )


@pytest.mark.parametrize(
    "override,reason",
    [
        ({"source_timestamp": NOW - timedelta(seconds=121)}, "TOKEN_STALE_OR_FUTURE"),
        ({"source_timestamp": NOW + timedelta(seconds=1)}, "TOKEN_STALE_OR_FUTURE"),
        ({"source_timestamp": None}, "TOKEN_TIMESTAMP_UNAVAILABLE"),
        ({"kind": "TRADE"}, "TOKEN_PRICE_UNITS_UNVERIFIED"),
        ({"kind": "CANDLE"}, "TOKEN_PRICE_UNITS_UNVERIFIED"),
        ({"token_to_share_ratio": D("1")}, "TOKEN_IDENTITY_OR_MODE_CONFLICT"),
        (
            {"source_timestamp": NOW, "ingestion_timestamp": NOW + timedelta(seconds=1)},
            "TOKEN_NOT_YET_AVAILABLE",
        ),
    ],
)
def test_price_units_time_identity_and_availability_fail_closed(override, reason):
    token, price, equity, regime = inputs()
    result = IndependentReferenceService().evaluate(
        token, price.model_copy(update=override), equity, regime, NOW, "DEMO"
    )
    assert result.status != "AVAILABLE" and reason in result.reason_codes


def test_timestamp_skew_boundary_is_exact():
    token, price, equity, regime = inputs()
    service = IndependentReferenceService()
    assert (
        service.evaluate(
            token,
            price,
            equity.model_copy(update={"source_timestamp": NOW - timedelta(seconds=30)}),
            regime,
            NOW,
            "DEMO",
        ).status
        == "AVAILABLE"
    )
    assert (
        service.evaluate(
            token,
            price,
            equity.model_copy(
                update={"source_timestamp": NOW - timedelta(seconds=30, microseconds=1)}
            ),
            regime,
            NOW,
            "DEMO",
        ).status
        == "STALE"
    )
