"""Phase 13 synthetic acceptance, never provider verification or real settlement."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models.research import ResearchPolicy
from app.models.scorecard import AuditEvent, Scorecard, ScorecardQuery
from app.repositories.research import ResearchStore
from app.repositories.scorecard import ScorecardStore
from app.services.research_replay import HistoricalReplay
from app.services.scorecard import quality, route_evaluation
from backend.tests.integration.test_demo_paper_api import steps
from backend.tests.unit.test_agents import REQUEST
from backend.tests.unit.test_opportunity_scan import request, scan, snapshot
from backend.tests.unit.test_portfolio import evaluate, setup
from backend.tests.unit.test_research import calendar, dataset, fixture

NOW = datetime(2026, 10, 8, 15, tzinfo=UTC)


@pytest.fixture
def scoring(settings, tmp_path):
    app = create_app(settings, terminal_research_store=ResearchStore(tmp_path / "replay"))
    with TestClient(app) as c:
        s = app.state.scorecard
        s.clock = lambda: NOW
        s.audit.clock = s.clock
        app.state.terminal.clock = s.clock
        app.state.exposure.clock = s.clock
        yield c, s


def ask(c, text="I have $50 of Nvidia"):
    r = c.post("/api/exposure/quote", json={"text": text})
    assert r.status_code == 200
    return r.json()


@pytest.mark.parametrize(
    "facts,expected",
    [
        (dict(action=True, permitted=True), "CORRECT_ACTION"),
        (dict(action=True, blocked=True), "INCORRECT_ACTION"),
        (dict(action=False, blocked=True), "CORRECT_ABSTENTION"),
        (dict(action=False, required=True), "INCORRECT_ABSTENTION"),
        (dict(action=False, permitted=True), "UNSCORABLE"),
        (dict(action=True), "UNSCORABLE"),
    ],
)
def test_control_consistency_is_explicit_and_permission_never_forces_purchase(facts, expected):
    assert quality(**facts) == expected


def test_direct_exposure_original_decision_trace_and_no_realized_costs(scoring):
    c, s = scoring
    proposal = ask(c)
    cards = c.get("/api/scorecard?scorecard_type=DIRECT_EXPOSURE").json()["page"]["items"]
    assert len(cards) == 1
    card = cards[0]
    assert card["decision_id"] == proposal["proposal_id"]
    assert card["requested_exposure_usd"] == "50"
    assert card["outcome"] in {"PROPOSED", "REJECTED"}
    assert not card["executions"] and card["route"]["actual_total_cost_usd"] is None
    assert card["score"] is None
    trace = c.get("/api/audit/decisions/" + card["decision_id"])
    assert trace.status_code == 200, trace.text
    t = trace.json()
    assert t["complete_for_recorded_scope"]
    types = {e["event_type"] for e in t["events"]}
    assert {"INPUT", "OUTCOME", "SCORECARD"} <= types
    assert {e["correlation_id"] for e in t["events"]} == {proposal["correlation_id"]}
    old = s.store.list(Scorecard, mode="DEMO")
    s.clock = lambda: NOW + timedelta(days=5)
    s.capture()
    assert s.store.list(Scorecard, mode="DEMO") == old  # Expiry never rewrites original inputs.


def test_unsupported_and_malformed_requests_are_correct_safe_abstentions(scoring):
    c, _ = scoring
    for text in ["$50 UnsupportedTickerZZZ", "not a stock request"]:
        p = ask(c, text)
        result = c.get("/api/scorecard", params={"decision_id": p["proposal_id"]})
        assert result.status_code == 200, result.text
        row = result.json()["page"]["items"][0]
        assert row["abstained"] and row["control_quality"] == "CORRECT_ABSTENTION"
        assert row["outcome"] == "REJECTED" and row["abstention_reasons"]


@pytest.mark.parametrize(
    "scenario,abstained",
    [
        ("steady", True),
        ("thin-move", True),
        ("supported-move", False),
    ],
)
def test_opportunity_scan_evaluation_uses_actual_candidates_and_risk(scoring, scenario, abstained):
    c, s = scoring
    result = scan(snapshot(scenario), request(scenario))
    s.scans.save(result)
    r = c.get("/api/scorecard", params={"decision_id": result.decision_id})
    assert r.status_code == 200, r.text
    card = r.json()["page"]["items"][0]
    assert card["abstained"] is abstained
    assert card["control_quality"] == ("CORRECT_ABSTENTION" if abstained else "CORRECT_ACTION")
    assert card["prediction"]["actual_opening_return"] is None
    assert card["prediction"]["classification_correct"] is None
    assert not card["executions"]
    trace = c.get("/api/audit/decisions/" + result.decision_id).json()
    assert "CANDIDATE_SCAN" in {e["event_type"] for e in trace["events"]}
    assert "AGENT_RUN" in {e["event_type"] for e in trace["events"]} or result.agent_run is None
    assert "reasoning_summary" not in str(trace) and "chain_of_thought" not in str(trace)


def test_route_efficiency_uses_recorded_eligible_common_basis_only(scoring):
    _, s = scoring
    result = scan(snapshot(), request())
    route = result.candidates[0].route
    evaluated = route_evaluation(route)
    assert (
        evaluated.selected_cost_per_share_usd == route.selected_candidate.ranking_cost_per_share_usd
    )
    assert evaluated.excess_cost_per_share_usd == Decimal(0)
    assert evaluated.minimum_cost_selected
    assert evaluated.actual_total_cost_usd is None and evaluated.simulated_cost_usd is None
    assert evaluated.estimated_costs_usd == route.selected_candidate.estimated_costs_usd
    assert not route_evaluation(None).alternative_costs_per_share_usd


def test_agent_only_decision_preserves_control_evidence_without_invented_execution(scoring):
    c, s = scoring
    from app.agents.adapters import DemoEvidenceAdapter
    from app.agents.orchestrator import AgentOrchestrator

    adapter = DemoEvidenceAdapter()
    bundle = adapter.load("supported-move")
    run = asyncio.run(AgentOrchestrator(store=s.terminal.agents).analyze(REQUEST, bundle))
    r = c.get("/api/scorecard", params={"decision_id": run.decision_id})
    assert r.status_code == 200, r.text
    assert r.json()["page"]["items"][0]["origin"] == "AGENT_RUN"


@pytest.mark.parametrize("weight,side", [("0.5", "BUY"), ("0.1", "SELL")])
def test_autopilot_consumes_original_drift_actions_and_canonical_execution(scoring, weight, side):
    c, s = scoring
    portfolio, position, _ = setup(weight=weight)
    try:
        plan = evaluate(portfolio)
        s.terminal.portfolio = portfolio
        s.terminal.positions = portfolio.positions
        s.terminal.execution = portfolio.positions.execution.store
        result = c.get("/api/scorecard?scorecard_type=AUTOPILOT")
        assert result.status_code == 200, result.text
        card = result.json()["page"]["items"][0]
        assert card["decision_id"] == plan.plan_id
        assert card["allocations"][0]["target_weight"] == str(plan.rows[0].target_weight)
        assert card["proposed_actions"][0]["notional_usd"] == str(plan.actions[0].notional_usd)
        assert card["outcome"] == "REBALANCE_REQUIRED"
        assert not card["executions"]
        assert card["proposed_actions"][0]["side"] == side
        assert card["control_quality"] == "CORRECT_ACTION"
    finally:
        portfolio.store.close()
        portfolio.positions.store.close()
        portfolio.positions.execution.store.close()


def test_historical_cutoff_preserves_decision_and_prediction_when_outcome_arrives(scoring):
    c, s = scoring
    cal = calendar.__wrapped__()
    episodes = dataset.__wrapped__(cal, fixture.__wrapped__())
    replay = HistoricalReplay(ResearchPolicy(model_features=("deviation",))).run(episodes)
    s.terminal.research.save(replay)
    e = replay.episodes[-1]
    before = s.list(
        ScorecardQuery(as_of=e.decision.decision_at, decision_id=e.decision.decision_id)
    )[0]
    assert before.prediction.actual_opening_return is None
    after = s.list(ScorecardQuery(as_of=e.target.available_at, decision_id=e.decision.decision_id))[
        0
    ]
    assert after.input_digest == before.input_digest
    assert after.prediction.predicted_return == before.prediction.predicted_return
    assert after.prediction.actual_opening_return == e.target.opening_return
    assert after.prediction.absolute_magnitude_error == abs(
        after.prediction.predicted_return - after.prediction.actual_opening_return
    )
    assert after.evaluation_id != before.evaluation_id
    assert before in s.store.list(Scorecard, mode="DEMO")
    assert all(x.timestamp <= e.decision.decision_at for x in s.events((before,)))
    assert (
        s.list(ScorecardQuery(as_of=e.decision.decision_at, decision_id=e.decision.decision_id))[0]
        == before
    )


@pytest.mark.parametrize(
    "q",
    [
        "limit=0",
        "limit=101",
        "offset=-1",
        "execute=true",
        "data_mode=LIVE_READ_ONLY",
        "as_of=2027-01-01T00:00:00Z",
        "ticker=../bad",
    ],
)
def test_invalid_or_future_or_cross_mode_query_fails_closed(scoring, q):
    c, _ = scoring
    assert c.get("/api/scorecard?" + q).status_code in {422, 503}


@pytest.mark.parametrize("endpoint", ["/api/scorecard", "/api/audit"])
def test_read_oriented_api_no_execution_and_no_authorizing_input(scoring, endpoint, monkeypatch):
    c, s = scoring
    p = ask(c)

    def forbidden(*a, **kw):
        raise AssertionError("Evaluation attempted a provider or financial mutation")

    monkeypatch.setattr(s.terminal.trust, "assess", forbidden)
    monkeypatch.setattr(s.terminal.layer.discovery, "resolve", forbidden)
    monkeypatch.setattr(s.terminal.portfolio, "evaluate", forbidden)
    monkeypatch.setattr(s.terminal.positions, "reconcile", forbidden)
    r = c.get(endpoint)
    assert r.status_code == 200, r.text
    assert r.json()["broadcast"] is False and r.json()["execution_ready"] is False
    assert r.json()["request_id"] == r.headers["X-Request-ID"]
    assert c.post(endpoint, json={"execute": True}).status_code == 405
    assert c.get("/api/scorecard?decision_id=" + p["proposal_id"]).status_code == 200
    assert r.json()["production_gates"]["TRUST_GATE"] == "BLOCKED"


def test_persistence_restart_idempotency_and_tampering_fail_closed(scoring, tmp_path):
    c, s = scoring
    ask(c)
    cards = s.capture()
    events = s.events(cards)
    first = ScorecardStore(tmp_path / "audit")
    try:
        first.append(cards, events)
        first.append(cards, events)
        assert len(first.list(Scorecard, mode="DEMO")) == len(cards)
    finally:
        first.close()
    second = ScorecardStore(tmp_path / "audit")
    try:
        assert second.list(Scorecard, mode="DEMO") == cards
        assert not second.list(Scorecard, mode="LIVE_READ_ONLY")
        table = second.tables["audit_events"]
        with second.engine.begin() as db:
            db.execute(table.update().values(digest="bad"))
        with pytest.raises(ValueError):
            second.list(AuditEvent, mode="DEMO")
    finally:
        second.close()


@pytest.mark.parametrize(
    "key",
    [
        "chain_of_thought",
        "hidden_reasoning",
        "private_key",
        "api_key",
        "userSignature",
        "typedDataToSign",
    ],
)
def test_unsafe_material_never_enters_evaluation_journal(scoring, key):
    c, s = scoring
    ask(c)
    event = s.events(s.capture())[0]
    poisoned = event.model_copy(update={"input_summary": {key: "forbidden"}})
    with pytest.raises(ValueError):
        s.audit.append((), (poisoned,))
    assert "forbidden" not in str(s.store.list(AuditEvent, mode="DEMO"))


def test_no_secret_persistence_or_echo(scoring):
    c, s = scoring
    ask(c)
    event = s.events(s.capture())[0]
    s.audit.secrets = ("synthetic-sensitive-value",)
    with pytest.raises(ValueError):
        s.audit.append(
            (),
            (event.model_copy(update={"output_summary": {"issuer": "synthetic-sensitive-value"}}),),
        )


def test_demo_paper_scorecard_reuses_accounting_and_is_never_confirmed(tmp_path):
    app = create_app(
        Settings(_env_file=None, app_env="test", runtime_mode="DEMO"),
        terminal_research_store=ResearchStore(tmp_path / "history"),
    )
    with TestClient(app) as c:
        s = app.state.scorecard
        s.clock = lambda: NOW
        s.audit.clock = s.clock
        t, o, r, q, p, sim = steps(c)
        fill = c.post(
            "/api/demo/paper/fills",
            json={
                "transaction_id": p["transaction"]["transaction_id"],
                "simulation_id": sim["simulation"]["simulation_id"],
            },
        ).json()
        base = "/api/demo/paper/positions/" + fill["position"]["position_id"]
        monitor = c.post(base + "/monitor").json()
        exited = c.post(
            base + "/exit", json={"observation_id": monitor["observation"]["observation_id"]}
        ).json()
        response = c.get(
            "/api/scorecard", params={"decision_id": o["opportunity"]["opportunity_id"]}
        )
        assert response.status_code == 200, response.text
        card = response.json()["page"]["items"][0]
        assert card["synthetic"] and card["outcome"] == "PAPER_EXITED"
        assert card["paper_pnl"] == exited["pnl"]
        assert not card["executions"] and not card["broadcast"]
        assert "EXECUTION_CONFIRMED" not in {e.event_type for e in s.events(s.capture())}


def test_completed_request_is_captured_without_scorecard_get(scoring):
    c, s = scoring
    p = ask(c)
    rows = s.store.list(Scorecard, mode="DEMO")
    assert any(r.decision_id == p["proposal_id"] for r in rows)
    events = s.store.list(AuditEvent, mode="DEMO")
    assert {"INPUT", "OUTCOME", "SCORECARD"} <= {e.event_type for e in events}


def test_simulation_only_has_audit_without_paper_fill_and_immutable_versions(tmp_path):
    app = create_app(
        Settings(_env_file=None, app_env="test", runtime_mode="DEMO"),
        terminal_research_store=ResearchStore(tmp_path / "history"),
    )
    with TestClient(app) as c:
        s = app.state.scorecard
        s.clock = lambda: NOW
        s.audit.clock = s.clock
        t, o, r, q, p, sim = steps(c)
        assert not s.paper.list()
        cards = s.list(ScorecardQuery(decision_id=o["opportunity"]["opportunity_id"]))
        card = cards[0]
        assert card.outcome == "SIMULATED" and not card.executions and card.paper_pnl is None
        assert card.route.actual_total_cost_usd is None and card.route.simulated_cost_usd is None
        events = s.events(cards)
        assert {"RISK_APPROVE", "QUOTE", "BUILD", "SIMULATION"} <= {e.event_type for e in events}
        assert all(e.timestamp <= card.evidence_asof for e in events)
        assert list(events) == sorted(events, key=s.audit.order)
        assert "EXECUTION_CONFIRMED" not in {e.event_type for e in events}
        saved = s.store.list(Scorecard, mode="DEMO")
        assert any(x.outcome == "PROPOSED" for x in saved)
        assert any(x.outcome == "PREPARED" for x in saved)
        assert all(
            x.input_digest == card.input_digest for x in saved if x.decision_id == card.decision_id
        )


@pytest.mark.parametrize(
    "state,expected",
    [
        ("EXECUTION_PENDING", "SUBMITTED"),
        ("EXECUTION_UNKNOWN", "UNKNOWN"),
        ("CONFIRMED", "CONFIRMED"),
        ("STALE_SNAPSHOT", "RECONCILIATION_REQUIRED"),
    ],
)
def test_canonical_execution_projection_never_infers_fills_or_settlement(scoring, state, expected):
    from backend.tests.integration.test_terminal import change
    from backend.tests.unit.test_position import runtime

    c, s = scoring
    manager, position, time = runtime(
        confirmed=state in {"CONFIRMED", "STALE_SNAPSHOT"},
        pending=state if state.startswith("EXECUTION_") else "EXECUTION_PENDING",
    )
    try:
        s.terminal.execution, s.terminal.positions = manager.execution.store, manager
        if state == "STALE_SNAPSHOT":
            canonical = manager.execution.store.get(
                position.entry_execution.execution_id, mode="DEMO"
            )
            behind = change(canonical, version=canonical.version - 1)
            stale = type(position).model_validate(
                {**position.model_dump(exclude_computed_fields=True), "entry_execution": behind}
            )
            manager.store.list = lambda **kw: [stale]
        response = c.get("/api/scorecard")
        assert response.status_code == 200, response.text
        card = next(
            x for x in response.json()["page"]["items"] if x["origin"] == "EXECUTION_JOURNAL"
        )
        assert card["outcome"] == expected
        row = card["executions"][0]
        assert not row[
            "actual_completed_trade"
        ]  # Authenticated synthetic settlement is still synthetic.
        if expected != "CONFIRMED":
            assert row["filled_base_units"] is None and row["remaining_base_units"] is None
            assert row["realized_net_pnl_usd"] is None
        else:
            assert row["filled_base_units"] == position.filled_quantity_base_units
        trace = c.get("/api/audit/decisions/" + card["decision_id"])
        assert trace.status_code == 200 and trace.json()["complete_for_recorded_scope"]
        assert all(e["execution_id"] in {None, row["execution_id"]} for e in trace.json()["events"])
    finally:
        manager.store.close()
        manager.execution.store.close()


def test_autopilot_simulation_child_links_and_no_false_completion(scoring):
    from backend.tests.fixtures.execution_fixtures import allowance

    c, s = scoring
    portfolio, position, time = setup()
    try:
        plan = evaluate(portfolio)
        portfolio.prepare(plan.plan_id, plan.actions[0].action_id, allowance=allowance())
        s.terminal.portfolio, s.terminal.positions = portfolio, portfolio.positions
        s.terminal.execution = portfolio.positions.execution.store
        r = c.get("/api/scorecard", params={"decision_id": plan.plan_id})
        assert r.status_code == 200, r.text
        card = r.json()["page"]["items"][0]
        assert card["outcome"] == "SIMULATED"
        assert card["executions"][0]["decision_id"] == plan.actions[0].execution_decision_id
        assert card["executions"][0]["filled_base_units"] is None
        trace = c.get("/api/audit/decisions/" + plan.plan_id).json()
        assert any(e["event_type"] == "SIMULATION" for e in trace["events"])
        assert not any(e["event_type"] == "EXECUTION_CONFIRMED" for e in trace["events"])
    finally:
        portfolio.store.close()
        portfolio.positions.store.close()
        portfolio.positions.execution.store.close()


def test_atomic_references_cross_worker_idempotence_and_immutable_conflicts(scoring, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    c, s = scoring
    ask(c)
    cards, events = s.capture(), s.events(s.capture())
    stores = [ScorecardStore(tmp_path / "workers") for _ in range(2)]
    try:
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(lambda store: store.append(cards, events), stores))
        assert len(stores[0].list(Scorecard, mode="DEMO")) == len(cards)
        assert len(stores[1].list(AuditEvent, mode="DEMO")) == len(events)
        poisoned = cards[0].model_copy(update={"outcome": "CONFIRMED"})
        with pytest.raises(ValueError):
            stores[0].append((poisoned,), ())
        dangling = cards[0].model_copy(update={"event_ids": ("unrecorded",)})
        dangling = dangling.model_copy(update={"evaluation_id": s.audit.evaluation_id(dangling)})
        with pytest.raises(ValueError, match="Missing atomic"):
            stores[0].append((dangling,), ())
        assert dangling not in stores[0].list(Scorecard, mode="DEMO")
        rewritten = cards[0].model_copy(update={"input_digest": "0" * 64})
        rewritten = rewritten.model_copy(update={"evaluation_id": s.audit.evaluation_id(rewritten)})
        with pytest.raises(ValueError, match="Original decision inputs"):
            stores[0].append((rewritten,), ())
        assert rewritten not in stores[0].list(Scorecard, mode="DEMO")
    finally:
        for store in stores:
            store.close()


def test_current_and_historical_api_versions_filters_and_unknown_outcomes(scoring):
    c, s = scoring
    p = ask(c)
    cards = s.capture()
    card = cards[0]
    r = c.get("/api/scorecard/" + card.evaluation_id)
    assert (
        r.status_code == 200 and r.json()["page"]["items"][0]["input_digest"] == card.input_digest
    )
    assert "IMMUTABLE_HISTORICAL" in r.json()["page"]["reasons"][0]
    assert c.get("/api/scorecard/" + card.evaluation_id + "?execute=true").status_code == 422
    assert c.get("/api/audit/decisions/not-recorded").status_code == 404
    assert not c.get("/api/scorecard?outcome=CONFIRMED").json()["page"]["items"]
    assert c.get("/api/audit", params={"decision_id": p["proposal_id"], "limit": 1}).json()["page"][
        "has_more"
    ]
    assert not c.get("/api/scorecard?after=2026-10-09T00:00:00Z").json()["page"]["items"]


def test_missing_classification_truth_and_no_scored_outcomes_are_unknown(scoring):
    c, s = scoring
    ask(c)
    result = c.get("/api/scorecard").json()
    assert result["metrics"]["directional_accuracy"] is None
    assert result["metrics"]["abstention_outcome_accuracy"] is None
    assert result["metrics"]["classification_accuracy"] is None
    assert result["metrics"]["statistical_validation"] == "NOT_CLAIMED"
    for card in result["page"]["items"]:
        assert card["prediction"]["classification_correct"] is None
        assert card["prediction"]["correctly_ignored_noise"] is None


def test_corrupt_source_or_journal_is_unavailable_not_a_fake_success(scoring, monkeypatch):
    c, s = scoring
    ask(c)

    def broken(*a, **kw):
        raise ValueError("untrusted raw source body")

    monkeypatch.setattr(s.exposure, "list_original", broken)
    r = c.get("/api/scorecard")
    assert r.status_code == 503
    assert "untrusted raw" not in r.text
    assert r.json()["error"] == {"code": "HTTP_ERROR", "message": "Request could not be handled"}


def test_confirmed_autopilot_completion_links_existing_phase10_ownership(scoring):
    from app.models.execution import ExecutionControls
    from app.services.execution import SafetyExecutionService
    from app.services.position import change
    from backend.tests.fixtures.execution_fixtures import TXHASH, FixtureProvider, allowance
    from backend.tests.integration.test_settlement_remediation import filled, observe
    from backend.tests.unit.test_position import instrument

    c, scoring_service = scoring
    portfolio, _, _ = setup()
    try:
        provider = FixtureProvider(execution_mode="RFQ")
        portfolio.positions.execution = SafetyExecutionService(
            provider,
            portfolio.positions.execution.store,
            ExecutionControls(data_mode="DEMO"),
            clock=portfolio.clock,
        )
        portfolio.positions.execution.position_guard = portfolio.positions.has_unresolved
        plan = evaluate(portfolio)
        action = plan.actions[0]
        prepared = portfolio.prepare(plan.plan_id, action.action_id, allowance=allowance())
        attempt = portfolio.positions.execution.store.get(
            prepared.preparations[0].execution_id, mode="DEMO"
        )
        pending = change(
            attempt,
            state="EXECUTION_PENDING",
            external_tracking_only=True,
            order_id="synthetic_portfolio_scorecard",
            tx_hash=TXHASH,
            version=attempt.version + 1,
            updated_at=portfolio.clock(),
        )
        portfolio.positions.execution.store.save(pending, expected_version=attempt.version)
        confirmed = observe(provider, portfolio.positions.execution.store, pending, filled(pending))
        owned = portfolio.register_confirmed_entry(plan.plan_id, action.action_id, instrument())
        completed = portfolio.complete(plan.plan_id)
        scoring_service.terminal.portfolio = portfolio
        scoring_service.terminal.positions = portfolio.positions
        scoring_service.terminal.execution = portfolio.positions.execution.store
        r = c.get("/api/scorecard", params={"decision_id": plan.plan_id})
        assert r.status_code == 200, r.text
        card = r.json()["page"]["items"][0]
        assert card["outcome"] == "COMPLETED" and completed.status == "COMPLETED"
        assert card["executions"][0]["filled_base_units"] == confirmed.filled_quantity_base_units
        assert card["executions"][0]["position_id"] == str(owned.position_id)
        assert not card["executions"][0]["actual_completed_trade"] and card["synthetic"]
        assert card["route"]["actual_total_cost_usd"] is None
        trace = c.get("/api/audit/decisions/" + plan.plan_id).json()
        assert trace["complete_for_recorded_scope"]
        assert {"EXECUTION_CONFIRMED", "POSITION", "OUTCOME"} <= {
            e["event_type"] for e in trace["events"]
        }
        assert all(e["decision_id"] == plan.plan_id for e in trace["events"])
    finally:
        portfolio.store.close()
        portfolio.positions.store.close()
        portfolio.positions.execution.store.close()


def test_decimal_accuracy_is_descriptive_not_classification_or_profitability(scoring):
    _, s = scoring
    from app.models.scorecard import PredictionEvaluation

    base = s._card("OPPORTUNITY", "TEST_FIXTURE", "test", "test", NOW, {"fixture": True})
    cards = tuple(
        base.model_copy(
            update={
                "confidence": "HIGH",
                "prediction": PredictionEvaluation(
                    predicted_return="0.0000000000000000000000001",
                    actual_opening_return="0.0000000000000000000000002",
                    direction_correct=correct,
                ),
            }
        )
        for correct in (True, False, True)
    )
    metrics = s.metrics(cards)
    assert metrics.directional_samples == 3 and metrics.high_confidence_samples == 3
    assert isinstance(metrics.directional_accuracy, Decimal)
    assert metrics.directional_accuracy == metrics.high_confidence_accuracy
    assert str(metrics.directional_accuracy).startswith("0.666666666666666666666666666666")
    assert metrics.classification_accuracy is None and metrics.abstention_outcome_accuracy is None
    assert metrics.statistical_validation == "NOT_CLAIMED"


def test_successful_direct_proposal_preserves_authoritative_normalization(scoring):
    c, s = scoring
    proposal = ask(c)
    assert proposal["selected"] is not None
    response = c.get("/api/scorecard", params={"decision_id": proposal["proposal_id"]})
    assert response.status_code == 200
    card = response.json()["page"]["items"][0]
    selected = proposal["selected"]
    assert card["outcome"] == "PROPOSED" and card["control_quality"] == "CORRECT_ACTION"
    assert card["selected_issuer"] == selected["issuer"]
    assert card["estimated_share_exposure"] == selected["estimated_real_share_exposure"]
    assert card["route"]["effective_cost_per_share_usd"] == selected["effective_cost_per_share_usd"]
    assert card["route"]["shares_per_token"] == selected["token_to_share_ratio"]
    assert card["route"]["token_price_usd"] == selected["token_price_usd"]
    assert card["route"]["actual_total_cost_usd"] is None and card["route"]["liquidity_usd"] is None
    trail = c.get("/api/audit/decisions/" + card["decision_id"]).json()
    assert {"ASSET_DISCOVERY", "NORMALIZATION", "ROUTE", "QUOTE"} <= {
        e["event_type"] for e in trail["events"]
    }


def test_live_readonly_missing_provider_inputs_never_seed_demo_evaluations(tmp_path):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            data_mode="LIVE_READ_ONLY",
            database_url=f"sqlite:///{tmp_path}/live.db",
        ),
        terminal_research_store=ResearchStore(tmp_path / "live-history"),
    )
    with TestClient(app) as c:
        proposal = ask(c)
        assert proposal["data_mode"] == "LIVE" and proposal["selected"] is None
        response = c.get("/api/scorecard", params={"decision_id": proposal["proposal_id"]})
        assert response.status_code == 200, response.text
        envelope = response.json()
        card = envelope["page"]["items"][0]
        assert envelope["data_mode"] == "LIVE_READ_ONLY" and card["data_mode"] == "LIVE_READ_ONLY"
        assert card["outcome"] == "REJECTED" and card["control_quality"] == "CORRECT_ABSTENTION"
        assert not card["synthetic"] and not card["executions"] and not card["broadcast"]
        assert app.state.demo_opportunity is None and app.state.demo_preparation is None
        assert not app.state.scorecard.store.list(Scorecard, mode="DEMO")


@pytest.mark.parametrize("stage", ["quote", "preparation"])
def test_blocked_demo_artifact_attempt_is_audited_without_invented_execution(tmp_path, stage):
    from backend.tests.integration.test_terminal import change

    app = create_app(
        Settings(_env_file=None, app_env="test", runtime_mode="DEMO"),
        terminal_research_store=ResearchStore(tmp_path / "history"),
    )
    with TestClient(app) as c:
        s = app.state.scorecard
        s.clock = lambda: NOW
        s.audit.clock = s.clock
        t, o, r, q, p, sim = steps(c)
        flow = app.state.demo_opportunity
        flow.fixture = change(
            flow.fixture, risk_inputs=change(flow.fixture.risk_inputs, wallet_available_usd="0")
        )
        if stage == "quote":
            result = c.post("/api/demo/quote", json={"risk_id": r["risk"]["risk_id"]})
        else:
            result = c.post("/api/demo/prepare", json={"quote_id": q["quote"]["quote_id"]})
        assert result.status_code == 200 and result.json()["status"] == "BLOCKED"
        response = c.get(
            "/api/scorecard", params={"decision_id": o["opportunity"]["opportunity_id"]}
        )
        assert response.status_code == 200, response.text
        card = response.json()["page"]["items"][0]
        assert card["outcome"] == "BLOCKED" and card["abstention_scope"] == "EXECUTION"
        assert card["abstention_reasons"] == result.json()["reason_codes"]
        assert not card["executions"] and card["paper_pnl"] is None
        trail = c.get("/api/audit/decisions/" + card["decision_id"]).json()
        failed = [
            e
            for e in trail["events"]
            if e["event_type"] == ("QUOTE" if stage == "quote" else "BUILD")
            and e["status"] == "BLOCKED"
        ]
        assert failed and failed[-1]["reasons"] == result.json()["reason_codes"]
        assert not any(e["event_type"] == "EXECUTION_CONFIRMED" for e in trail["events"])
