"""Explicitly synthetic research controls; never production data-gate evidence."""

from datetime import date, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.research import AvailableRecord, ReplayCosts, ResearchFrame, ResearchPolicy
from app.repositories.research import ResearchStore
from app.services.calendar import USEquityCalendar
from app.services.demo_sandbox import DemoTrustSandbox
from app.services.research_episodes import ResearchEpisodeBuilder, candidate_frames, fingerprint
from app.services.research_model import (
    HistoricalRetrieval,
    RollingOpeningModel,
    cosine,
    qr_fit,
    vector,
)
from app.services.research_replay import HistoricalReplay

D = Decimal


def changed(record, **updates):
    return type(record).model_validate({**record.model_dump(), **updates})


@pytest.fixture(scope="module")
def calendar():
    result = USEquityCalendar(mode="DEMO")
    # Test-only earlier schedule availability. The actual published schedule is never changed.
    result.data["verified_at"] = "2026-01-01T00:00:00+00:00"
    return result


@pytest.fixture(scope="module")
def fixture():
    return DemoTrustSandbox().datasets["steady"]


def proof(record):
    return AvailableRecord(
        record_digest=fingerprint(record),
        effective_at=record.source_timestamp,
        available_at=record.ingestion_timestamp,
        revision_verified=True,
        source="SYNTHETIC_TEST_LEDGER_NOT_REAL_EVIDENCE",
    )


def frame(calendar, fixture, day=date(2026, 10, 12), deviation=None):
    deviation = D("0.007") if deviation is None else deviation
    opening = calendar.session(day)[0]
    at = opening - timedelta(seconds=60)
    previous = calendar.previous_session(opening)[1]
    metadata = changed(fixture.token.record, source_timestamp=at, ingestion_timestamp=at)
    price = changed(
        fixture.price.record,
        source_timestamp=at,
        ingestion_timestamp=at,
        token_price=D(50) * (1 + deviation),
        token_to_share_ratio=D("0.5"),
        volume=D(1000),
        volume_unit="USD",
    )
    reference = changed(
        fixture.equity.record,
        source_timestamp=previous - timedelta(minutes=1),
        ingestion_timestamp=previous,
        kind="BAR",
        interval="1minute",
        open=D(100),
        high=D(100),
        low=D(100),
        close=D(100),
        price=D(100),
        adjusted=False,
    )
    opening_return = D("0.005") + D("0.4") * deviation
    target = changed(
        reference,
        source_timestamp=opening,
        ingestion_timestamp=opening + timedelta(minutes=5),
        interval="5minute",
        close=D(100) * (1 + opening_return),
        price=D(100) * (1 + opening_return),
        high=D(110),
        low=D(90),
    )
    history = []
    for i, wrapped in enumerate(fixture.baseline_episodes):
        e = wrapped.record
        time = at - timedelta(days=i + 1)
        f = changed(e.sample.features, asof=time, available_at=time)
        sample = changed(e.sample, features=f, regime="PREMARKET", reference_kind="REGULAR_CLOSE")
        history.append(
            changed(
                e,
                sample=sample,
                started_at=time - timedelta(minutes=15),
                ended_at=time + timedelta(minutes=15),
                outcome_available_at=time + timedelta(minutes=15),
            )
        )
    return ResearchFrame(
        decision_at=at,
        ticker=metadata.ticker,
        issuer=metadata.platform_id,
        chain_id=metadata.chain_id,
        contract=metadata.contract,
        data_mode="DEMO",
        metadata=(metadata,),
        tokens=(price,),
        equities=(reference, target),
        baseline_episodes=tuple(history),
        proofs=tuple(proof(r) for r in (metadata, reference, target)),
        news_coverage_available_at=at,
        news_prefix_start=at - timedelta(days=1),
    )


@pytest.fixture(scope="module")
def dataset(calendar, fixture):
    builder = ResearchEpisodeBuilder(calendar)
    rows = []
    day = date(2026, 7, 1)
    while len(rows) < 45:
        if calendar.session(day) and day != date(2026, 7, 6):
            # Varied measured support, not a monotonic extrapolation task.
            deviation = D("0.002") + D(len(rows) % 11) / 1000
            rows.append(builder.build(frame(calendar, fixture, day, deviation)))
        day += timedelta(days=1)
    return rows


def test_episode_construction_reuses_trust_and_exact_normalization(calendar, fixture):
    value = frame(calendar, fixture)
    e = ResearchEpisodeBuilder(calendar).build(value)
    d = e.decision
    assert d.data_quality == "ELIGIBLE", d.reasons
    assert d.sample.features.deviation == D("0.007")
    assert d.sample.features.effective_price_per_share_usd == D("100.7")
    assert d.trust.reference.reference_asof == d.previous_close_at
    assert d.trust.baseline.sample_count >= 30
    assert d.volume_percentile == d.trust.baseline.volume_percentile
    assert e.target.status == "AVAILABLE" and e.target.opening_return == D("0.0078")
    assert e.target.completed_at == d.opening_at + timedelta(minutes=5)
    assert e.target.available_at > d.decision_at
    assert e.evidence_kind == "SYNTHETIC_TEST" and not d.transaction_broadcast


@pytest.mark.parametrize("mutation", ["ratio", "reference", "liquidity", "news", "baseline"])
def test_missing_required_historical_inputs_fail_closed(calendar, fixture, mutation):
    value = frame(calendar, fixture)
    if mutation == "ratio":
        value = changed(value, proofs=value.proofs[1:])
    elif mutation == "reference":
        value = changed(value, equities=value.equities[1:])
    elif mutation == "liquidity":
        value = changed(value, tokens=(changed(value.tokens[0], provider_metadata={}),))
    elif mutation == "news":
        value = changed(value, news_coverage_available_at=None)
    else:
        value = changed(value, baseline_episodes=value.baseline_episodes[:29])
    e = ResearchEpisodeBuilder(calendar).build(value)
    assert e.decision.data_quality == "REJECTED"
    assert RollingOpeningModel().predict([], e.decision).status == "NOT_READY"


@pytest.mark.parametrize("mutation", ["token", "news", "liquidity", "ratio", "open", "baseline"])
def test_changing_future_information_never_changes_earlier_decision(calendar, fixture, mutation):
    value = frame(calendar, fixture)
    builder = ResearchEpisodeBuilder(calendar)
    before = builder.decision(value)
    future = value.decision_at + timedelta(seconds=1)
    if mutation in {"token", "liquidity"}:
        extra = changed(
            value.tokens[0],
            ingestion_timestamp=future,
            source_timestamp=future,
            token_price=D(500),
            provider_metadata={"liquidity": "99999999"},
        )
        value = changed(value, tokens=(*value.tokens, extra))
    elif mutation == "news":
        article = DemoTrustSandbox().datasets["supported-move"].news[0].record
        article = changed(
            article,
            ingestion_timestamp=future,
            published_timestamp=value.decision_at - timedelta(minutes=2),
        )
        value = changed(value, news=(article,))
    elif mutation == "ratio":
        m = changed(
            value.metadata[0],
            ingestion_timestamp=future,
            source_timestamp=future,
            token_to_share_ratio=D(10),
        )
        value = changed(value, metadata=(*value.metadata, m), proofs=(*value.proofs, proof(m)))
    elif mutation == "open":
        b = changed(value.equities[-1], close=D(109), price=D(109))
        value = changed(value, equities=(value.equities[0], b))
    else:
        history = [changed(e, outcome_available_at=future) for e in value.baseline_episodes]
        value = changed(value, baseline_episodes=(*value.baseline_episodes, *history))
    assert builder.decision(value) == before


@pytest.mark.parametrize(
    "day,close_hour,open_hour",
    [
        (date(2026, 11, 30), 18, 14),  # Black Friday early close, Monday reopening.
        (date(2026, 7, 6), 20, 13),  # Holiday weekend; prior Thursday.
        (date(2026, 3, 9), 21, 13),  # US DST transition.
        (date(2026, 11, 2), 20, 14),  # Fall DST transition.
    ],
)
def test_actual_calendar_reference_and_target(calendar, fixture, day, close_hour, open_hour):
    e = ResearchEpisodeBuilder(calendar).build(frame(calendar, fixture, day))
    assert e.decision.previous_close_at.hour == close_hour
    assert e.decision.opening_at.hour == open_hour
    assert e.decision.independent_equity.source_timestamp + timedelta(minutes=1) == (
        e.decision.previous_close_at
    )
    assert e.target.status == "AVAILABLE"


def test_target_posthoc_without_revision_proof_and_exact_first_bar(calendar, fixture):
    value = frame(calendar, fixture)
    e = ResearchEpisodeBuilder(calendar).build(changed(value, proofs=value.proofs[:2]))
    assert e.target.status == "POSTHOC_ONLY"
    late = changed(
        value.equities[-1],
        source_timestamp=value.equities[-1].source_timestamp + timedelta(minutes=5),
    )
    e = ResearchEpisodeBuilder(calendar).build(changed(value, equities=(value.equities[0], late)))
    assert e.target.status == "UNSCORABLE" and e.target.opening_return is None


def test_vector_determinism_cosine_symmetry_and_no_outcome_features(dataset):
    v = vector(dataset[0].decision)
    assert vector(dataset[0].decision) == v
    assert len(v) == 7 + 5 + 6
    assert abs(cosine(v, v) - 1) < D("1e-250")
    assert cosine(v, vector(dataset[1].decision)) == cosine(vector(dataset[1].decision), v)
    with pytest.raises(ValueError):
        cosine([D(0)], [D(0)])
    with pytest.raises(ValueError):
        cosine([D(1)], [D(1), D(1)])


def test_top_k_ordering_counts_future_outcomes_and_insufficiency(dataset):
    current = dataset[-1].decision
    engine = HistoricalRetrieval()
    result = engine.evaluate(dataset, current)
    assert result.status == "SUFFICIENT" and result.retrieved_count == 3
    assert result == engine.evaluate(list(reversed(dataset)), current)
    assert all(m.outcome_available_at <= current.decision_at for m in result.matches)
    assert dataset[-1].episode_id not in result.rejected  # No future outcome metadata at T.
    assert engine.evaluate(dataset[:2], current).status == "INSUFFICIENT_DATA"
    shifted = changed(
        dataset[0],
        target=changed(dataset[0].target, available_at=current.decision_at + timedelta(seconds=1)),
    )
    result = engine.evaluate([shifted], current)
    assert result.eligible_count == 0
    assert "FUTURE_OR_UNAVAILABLE_OUTCOME" in result.rejected[shifted.episode_id]


def test_rolling_ols_known_local_coefficients_and_reproducibility(dataset):
    policy = ResearchPolicy(model_features=("deviation",), rolling_window=30)
    model = RollingOpeningModel(policy)
    value = model.predict(dataset, dataset[-1].decision)
    assert value.status == "READY", value.reason
    assert value.sample_count == 30 and value.eligible_count == 44
    assert abs(value.coefficients["intercept"] - D("0.005")) < D("1e-250")
    # Regression uses the explicit deviation/0.01 feature scale.
    assert abs(value.coefficients["deviation"] - D("0.004")) < D("1e-250")
    assert abs(value.predicted_return - dataset[-1].target.opening_return) < D("1e-250")
    assert value.interval_low <= value.predicted_return <= value.interval_high
    assert value.historical_directional_accuracy is None
    assert value.confidence == "UNCALIBRATED"
    assert value == model.predict(list(reversed(dataset)), dataset[-1].decision)


def test_model_insufficient_degenerate_and_invalid_regime(dataset):
    current = dataset[-1].decision
    model = RollingOpeningModel(ResearchPolicy(model_features=("deviation",)))
    assert model.predict(dataset[:29], current).status == "INSUFFICIENT_DATA"
    default = RollingOpeningModel().predict(dataset, current)
    assert default.status == "NOT_READY" and default.reason == "RANK_DEFICIENT_DESIGN"
    with pytest.raises(ValidationError):
        changed(current, regime="REGULAR")
    with pytest.raises(ValidationError):
        ResearchPolicy(min_model_samples=29)
    with pytest.raises(ValidationError):
        ResearchPolicy(model_features=("opening_return",))


def test_future_target_mutation_cannot_change_current_model_or_retrieval(dataset):
    current = dataset[35].decision
    altered = list(dataset)
    future = dataset[-1]
    target = changed(future.target, first_bar_close=D(200), opening_return=D(1))
    altered[-1] = changed(future, target=target)
    policy = ResearchPolicy(model_features=("deviation",))
    assert RollingOpeningModel(policy).predict(dataset, current) == (
        RollingOpeningModel(policy).predict(altered, current)
    )
    assert HistoricalRetrieval().evaluate(dataset, current) == (
        HistoricalRetrieval().evaluate(altered, current)
    )


def test_replay_reproducible_all_rows_isolated_and_walkforward_accuracy(dataset, tmp_path):
    engine = HistoricalReplay(ResearchPolicy(model_features=("deviation",)))
    first = engine.run(dataset, provenance=("SYNTHETIC_TEST",))
    assert first == engine.run(list(reversed(dataset)), provenance=("SYNTHETIC_TEST",))
    assert first.episode_count == 45 and first.eligible_episode_count == 45
    assert first.prediction_count == 15
    assert first.directional_accuracy == 1
    assert first.rows[30].prediction.historical_directional_accuracy is None
    assert first.rows[31].prediction.accuracy_sample_count == 1
    assert all(r.hypothetical_decision == "DEFER" for r in first.rows)
    assert all(r.hypothetical_outcome["pnl"] is None for r in first.rows)
    assert first.production_writes == first.execution_calls == 0
    assert first.trust_gate == "BLOCKED" and first.opportunity_gate == "BLOCKED_BY_TRUST"
    store = ResearchStore(tmp_path / "research")
    path = store.save(first)
    assert store.save(first) == path and store.load(first.run_id) == first
    assert len(list(store.directory.glob("*.json"))) == 1


def test_replay_costs_known_at_decision_use_existing_economics(dataset):
    e = dataset[-1]
    cost = ReplayCosts(
        observed_at=e.decision.decision_at,
        available_at=e.decision.decision_at,
        requested_notional="50",
        slippage_bps="10",
        fees="0.1",
        gas="0.01",
        execution_buffer="0.05",
        source="SYNTHETIC_TEST_COSTS",
    )
    engine = HistoricalReplay(ResearchPolicy(model_features=("deviation",)))
    result = engine.run(dataset, costs={e.episode_id: cost}).rows[-1]
    assert result.expected_adjustment_per_share is not None
    assert result.cost_adjusted_edge_usd is not None
    later = changed(cost, available_at=cost.available_at + timedelta(seconds=1))
    rejected = engine.run(dataset, costs={e.episode_id: later}).rows[-1]
    assert rejected.cost_adjusted_edge_usd is None
    assert "ASOF_COSTS_UNAVAILABLE" in rejected.reasons
    assert not rejected.transaction_broadcast


@pytest.mark.parametrize("value", [True, 0.1, "NaN", "Infinity"])
def test_malformed_financial_policy_rejected(value):
    with pytest.raises(ValidationError):
        ResearchPolicy(deviation_scale=value)


def test_dataset_mode_scope_duplicates_and_store_boundaries(dataset, tmp_path):
    live = dataset[-1].model_dump()
    live["decision"]["data_mode"] = "LIVE"
    with pytest.raises(ValidationError):
        type(dataset[-1]).model_validate(live)
    engine = RollingOpeningModel(ResearchPolicy(model_features=("deviation",)))
    assert engine.predict([*dataset[:29], *dataset[:29]], dataset[-1].decision).sample_count == 29
    with pytest.raises(ValueError):
        HistoricalReplay().run([])
    with pytest.raises(ValueError):
        ResearchStore(tmp_path / "production.db")
    folder = tmp_path / "application"
    folder.mkdir()
    (folder / "app.db").touch()
    with pytest.raises(ValueError):
        ResearchStore(folder)
    with pytest.raises(ValueError):
        ResearchStore(tmp_path / "research").load("../../app.db")


def test_calendar_verification_not_backdated(fixture):
    calendar = USEquityCalendar(mode="DEMO")
    e = ResearchEpisodeBuilder(calendar).build(frame(calendar, fixture, date(2026, 10, 5)))
    assert "CALENDAR_VERSION_NOT_YET_VERIFIED" in e.decision.reasons


def test_candidate_enumeration_no_padding_or_synthetic_in_real_inputs(calendar, fixture):
    f = frame(calendar, fixture)
    # Fixture price is observed BEFORE the session opens, so it is a real raw candidate in
    # the explicitly DEMO test mode; one captured opening, no implied continuous history.
    result = list(
        candidate_frames(
            calendar, metadata=f.metadata, tokens=f.tokens, equities=f.equities, mode="DEMO"
        )
    )
    assert len(result) == 1
    assert result[0].data_mode == "DEMO"
    assert not list(candidate_frames(calendar, metadata=(), tokens=(), equities=f.equities))


def test_research_has_no_execution_or_scorecard_dependencies():
    root = Path(__file__).parents[2] / "app"
    for relative in (
        "services/research_episodes.py",
        "services/research_model.py",
        "services/research_replay.py",
        "repositories/research_source.py",
    ):
        content = (root / relative).read_text()
        assert "app.clients.binance" not in content and "app.clients.massive" not in content
        assert "app.services.paper" not in content
        assert "scorecard" not in content or relative == "services/research_replay.py"
    # No configurable execution gateway in the research API.
    assert set(HistoricalReplay.__init__.__annotations__) <= {"return"}


def test_multivariate_qr_fit_recovers_independent_coefficients():
    with localcontext() as context:
        context.prec = 256
        matrix = [[D(1), D(i) / 20, D(i % 7) / 10] for i in range(40)]
        targets = [D("0.01") + D("0.03") * row[1] - D("0.02") * row[2] for row in matrix]
        beta, _, variance = qr_fit(matrix, targets, D("1e-40"))
        assert all(
            abs(actual - expected) < D("1e-250")
            for actual, expected in zip(beta, [D("0.01"), D("0.03"), D("-0.02")], strict=True)
        )
        assert variance < D("1e-500")


@pytest.mark.parametrize("offset,eligible", [(120, True), (121, False)])
def test_historical_price_freshness_boundary(calendar, fixture, offset, eligible):
    f = frame(calendar, fixture)
    p = changed(f.tokens[0], source_timestamp=f.decision_at - timedelta(seconds=offset))
    result = ResearchEpisodeBuilder(calendar).decision(changed(f, tokens=(p,)))
    assert (result.data_quality == "ELIGIBLE") is eligible


def test_model_rejects_forged_future_features_and_unknown_regime(dataset):
    current = dataset[-1].decision
    forged = current.model_copy(update={"regime": "UNVERIFIED"})
    assert RollingOpeningModel().predict(dataset, forged).status == "NOT_READY"
    feature = current.sample.features.model_copy(
        update={
            "available_at": current.decision_at + timedelta(seconds=1),
        }
    )
    forged = current.model_copy(
        update={
            "sample": current.sample.model_copy(
                update={
                    "features": feature,
                }
            )
        }
    )
    assert RollingOpeningModel().predict(dataset, forged).status == "NOT_READY"


def test_replay_information_does_not_override_costs_or_risk_gates(dataset):
    e = dataset[-1]
    # Contract-level test input only; no modified Trust service or production evidence.
    d = changed(e.decision, trust=changed(e.decision.trust, classification="LIKELY_INFORMATION"))
    altered = [*dataset[:-1], changed(e, decision=d)]
    c = ReplayCosts(
        observed_at=d.decision_at,
        available_at=d.decision_at,
        requested_notional="50",
        slippage_bps="0",
        fees="0",
        gas="0",
        execution_buffer="0",
        source="SYNTHETIC_TEST_EXPLICIT_ZERO_COSTS",
    )
    engine = HistoricalReplay(ResearchPolicy(model_features=("deviation",)))
    row = engine.run(altered, costs={e.episode_id: c}).rows[-1]
    assert row.cost_adjusted_edge_usd > 0
    assert row.hypothetical_decision == "PROPOSE_RESEARCH_ONLY"
    assert row.hypothetical_risk == "REJECTED_PRODUCTION_GATES"
    assert row.execution_ready is row.transaction_broadcast is False
    row = engine.run(altered, costs={e.episode_id: changed(c, fees="100")}).rows[-1]
    assert row.hypothetical_decision == "DEFER"
    assert row.cost_adjusted_edge_usd < 0


def test_saved_dataset_replays_independently_and_corruption_fails(dataset, tmp_path):
    import json

    engine = HistoricalReplay(ResearchPolicy(model_features=("deviation",)))
    run = engine.run(dataset, provenance=("SYNTHETIC_TEST",))
    store = ResearchStore(tmp_path / "research")
    path = store.save(run)
    loaded = store.load(run.run_id)
    assert engine.run(loaded.episodes, costs=loaded.costs, provenance=loaded.provenance) == loaded
    artifact = json.loads(path.read_text())
    artifact["record"] += " "
    path.write_text(json.dumps(artifact))
    with pytest.raises(ValueError, match="Corrupt"):
        store.load(run.run_id)


def test_future_corporate_action_proof_and_scorecard_never_enter_features(calendar, fixture):
    f = frame(calendar, fixture)
    builder = ResearchEpisodeBuilder(calendar)
    reference_proof = changed(f.proofs[1], available_at=f.decision_at + timedelta(seconds=1))
    future = changed(f, proofs=(f.proofs[0], reference_proof, f.proofs[2]))
    d = builder.decision(future)
    assert d.data_quality == "REJECTED"
    assert "ASOF_EQUITY_REVISION_UNVERIFIED" in d.reasons
    with pytest.raises(ValidationError):
        ResearchFrame.model_validate({**f.model_dump(), "future_scorecards": []})


def test_wrong_regular_close_extended_hours_and_conflicting_target(calendar, fixture):
    f = frame(calendar, fixture)
    extended = changed(
        f.equities[0], source_timestamp=f.equities[0].source_timestamp + timedelta(minutes=1)
    )
    d = ResearchEpisodeBuilder(calendar).decision(changed(f, equities=(extended, f.equities[-1])))
    assert "KNOWN_PREVIOUS_REGULAR_CLOSE_UNAVAILABLE" in d.reasons
    conflict = changed(f.equities[-1], close=D(109), price=D(109))
    e = ResearchEpisodeBuilder(calendar).build(changed(f, equities=(*f.equities, conflict)))
    assert e.target.status == "UNSCORABLE"


def test_current_regular_session_fails_opening_model_without_weakening_alignment(calendar, fixture):
    from app.services.trust_evidence import IndependentReferenceService, MarketRegimeService

    f = frame(calendar, fixture)
    at = f.decision_at + timedelta(minutes=2)
    d = ResearchEpisodeBuilder(calendar).decision(changed(f, decision_at=at))
    assert d.data_quality == "REJECTED"
    assert "OPENING_MODEL_REQUIRES_OFF_HOURS_DECISION" in d.reasons
    regime = MarketRegimeService(calendar).evaluate(at)
    metadata = changed(f.metadata[0], ingestion_timestamp=at, source_timestamp=at)
    token = changed(f.tokens[0], ingestion_timestamp=at, source_timestamp=at)
    equity = changed(
        f.equities[0], ingestion_timestamp=at, source_timestamp=at, kind="QUOTE", interval=None
    )
    reference = IndependentReferenceService()
    assert reference.evaluate(metadata, token, equity, regime, at, "DEMO").status == "AVAILABLE"
    equity = changed(equity, source_timestamp=at - timedelta(seconds=30))
    assert reference.evaluate(metadata, token, equity, regime, at, "DEMO").status == "AVAILABLE"
    equity = changed(equity, source_timestamp=at - timedelta(seconds=31))
    assert reference.evaluate(metadata, token, equity, regime, at, "DEMO").status == "STALE"


def test_off_hours_return_requires_two_asof_ratios_without_constant_ratio_assumption(
    calendar, fixture
):
    f = frame(calendar, fixture)
    close = calendar.previous_session(f.decision_at)[1]
    m = changed(
        f.metadata[0],
        source_timestamp=close,
        ingestion_timestamp=close,
        token_to_share_ratio=D("0.25"),
    )
    p = changed(
        f.tokens[0],
        source_timestamp=close,
        ingestion_timestamp=close,
        token_to_share_ratio=D("0.25"),
        token_price=D(25),
        kind="PRICE",
    )
    full = changed(
        f, metadata=(m, *f.metadata), tokens=(p, *f.tokens), proofs=(proof(m), *f.proofs)
    )
    d = ResearchEpisodeBuilder(calendar).decision(full)
    assert d.data_quality == "ELIGIBLE"
    assert d.closure_token.token_to_share_ratio == D("0.25")
    assert d.off_hours_return == D("0.007")
    assert ResearchEpisodeBuilder(calendar).decision(f).off_hours_return is None
    late = changed(m, ingestion_timestamp=f.decision_at)
    bad = changed(full, metadata=(late, *f.metadata))
    assert ResearchEpisodeBuilder(calendar).decision(bad).off_hours_return is None


def test_configured_off_hours_feature_missing_never_fits_proxy_or_prior(dataset):
    policy = ResearchPolicy(model_features=("off_hours_return", "deviation"))
    p = RollingOpeningModel(policy).predict(dataset, dataset[-1].decision)
    assert p.status == "NOT_READY" and p.reason == "MISSING_MODEL_FEATURES"
    assert p.predicted_return is None and not p.coefficients


def test_future_outcome_quality_and_malformed_values_are_not_inspected_at_earlier_time(dataset):
    current = dataset[35].decision
    future = dataset[-1]
    # Deliberately corrupt a future payload through model_copy; it must not reach a prior fit.
    bad = future.model_copy(
        update={
            "target": future.target.model_copy(
                update={
                    "first_bar_close": D("NaN"),
                    "opening_return": D("NaN"),
                    "status": "UNSCORABLE",
                }
            )
        }
    )
    altered = [*dataset[:-1], bad]
    policy = ResearchPolicy(model_features=("deviation",))
    assert RollingOpeningModel(policy).predict(dataset, current) == (
        RollingOpeningModel(policy).predict(altered, current)
    )
    assert HistoricalRetrieval().evaluate(dataset, current) == (
        HistoricalRetrieval().evaluate(altered, current)
    )
    assert future.episode_id not in HistoricalRetrieval().evaluate(dataset, current).rejected
