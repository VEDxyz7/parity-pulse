"""Phase 12 projections; financial examples are isolated synthetic verification only."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.agents.adapters import DemoEvidenceAdapter
from app.agents.orchestrator import AgentOrchestrator
from app.main import create_app
from app.models.data import EquityObservation, TokenMetadata
from app.models.research import ResearchPolicy
from app.models.terminal import EpisodeQuery, TerminalQuery
from app.providers.demo import load_data_fixture
from app.repositories.research import ResearchStore
from app.services.demo_sandbox import DemoTrustSandbox
from app.services.normalization import comparable_economics
from app.services.research_replay import HistoricalReplay
from backend.tests.fixtures.execution_fixtures import allowance
from backend.tests.unit.test_agents import REQUEST
from backend.tests.unit.test_portfolio import evaluate, setup
from backend.tests.unit.test_research import calendar, dataset, fixture

NOW = datetime(2026, 10, 8, 15, tzinfo=UTC)
D = Decimal


def change(record, **updates):
    return type(record).model_validate({**record.model_dump(), **updates})


@pytest.fixture
def terminal(settings, tmp_path):
    app = create_app(settings, terminal_research_store=ResearchStore(tmp_path / "replay"))
    with TestClient(app) as client:
        service = app.state.terminal
        service.clock = lambda: NOW
        records = load_data_fixture()
        token = next(r for r in records["metadata"] if r.ticker == "NVDA")
        price = next(r for r in records["tokens"] if r.ticker == "NVDA")
        equity = next(r for r in records["equities"] if r.ticker == "NVDA")
        stamp = dict(
            source_timestamp=NOW, ingestion_timestamp=NOW, raw_source_timestamp=NOW.isoformat()
        )
        token = change(token, **stamp, token_to_share_ratio="0.1")
        price = change(
            price,
            **stamp,
            token_to_share_ratio="0.1",
            token_price="10.2",
            binance_reference_price="987654",
        )
        equity = change(equity, **stamp, kind="SNAPSHOT", price="100")
        service.layer.repository.save([token, price, equity])
        yield client, service, token, price, equity


def board(terminal):
    return terminal[0].get("/api/terminal/issuers?ticker=NVDA").json()["page"]["items"]


def test_spread_normalization_provenance_and_no_binance_reference(terminal):
    row = board(terminal)[0]
    assert row["effective_price_per_share_usd"] == "102"
    assert row["independent_equity_price_usd"] == "100"
    assert row["deviation"] == "0.02" and row["deviation_percent"] == "2.00"
    assert row["absolute_deviation"] == "0.02" and row["spread_usd_per_share"] == "2"
    assert (
        D(row["effective_price_per_share_usd"])
        == comparable_economics("10.2", "0.1", "100")["effective_price_per_share_usd"]
    )
    assert len(row["observations"]) == 3 and all(
        len(o["digest"]) == 64 for o in row["observations"]
    )
    assert row["reference"]["timestamp_skew_seconds"] == "0"
    assert row["route_status"] == "NOT_QUOTED" and row["provider_route_id"] is None
    assert row["eligibility"] == "INSUFFICIENT_EVIDENCE"


def test_multiple_issuers_and_ratio_are_not_conflated(terminal):
    _, s, token, price, _ = terminal
    records = load_data_fixture()
    issuer = change(records["issuers"][0], platform_id="alternate", provider_identifier="alternate")
    token2 = change(
        token,
        platform_id="alternate",
        contract="demo:NVDA-alternate",
        token_to_share_ratio="0.05",
        provider_identifier="alternate",
    )
    price2 = change(
        price,
        issuer="alternate",
        contract=token2.contract,
        token_to_share_ratio="0.05",
        token_price="4.9",
        provider_identifier="alternate",
    )
    s.layer.repository.save([issuer, token2, price2])
    rows = board(terminal)
    assert len(rows) == 2
    assert {r["effective_price_per_share_usd"] for r in rows} == {"102", "98"}
    assert {r["deviation_percent"] for r in rows} == {"2.00", "-2.00"}


@pytest.mark.parametrize("field", ["token", "equity", "ratio"])
def test_stale_required_inputs_are_not_current_economics(terminal, field):
    _, s, token, price, equity = terminal
    # Use a later query cutoff, or a fresh mark with an old independent reference.
    if field in {"token", "ratio"}:
        s.clock = lambda: NOW + timedelta(seconds=121)
    else:
        s.layer.repository.save(
            [
                change(
                    equity,
                    source_timestamp=NOW - timedelta(seconds=121),
                    raw_source_timestamp="old",
                    provider_identifier="stale-equity",
                )
            ]
        )
        # Remove the existing current equity only in this disposable fixture database.
        from app.models.data_tables import EquityObservationRow

        with s.layer.repository.database.sessions.begin() as db:
            for row in (
                db.query(EquityObservationRow).filter(EquityObservationRow.ticker == "NVDA").all()
            ):
                if '"provider_identifier":"stale-equity"' not in row.payload.replace(" ", ""):
                    db.delete(row)
    row = board(terminal)[0]
    assert row["deviation"] is None and row["independent_equity_price_usd"] is None
    assert row["freshness"] == "STALE"
    assert row["eligibility"] == "INSUFFICIENT_EVIDENCE"


def test_missing_equity_does_not_remove_valid_token_normalization(terminal):
    _, s, _, _, _ = terminal
    original = s.layer.repository.list
    s.layer.repository.list = lambda model, **kw: (
        [] if model is EquityObservation else original(model, **kw)
    )
    row = board(terminal)[0]
    assert row["effective_price_per_share_usd"] == "102"
    assert row["deviation"] is None and row["reference"]["status"] == "UNAVAILABLE"
    assert "INDEPENDENT_REFERENCE_UNAVAILABLE" in row["reasons"]


@pytest.mark.parametrize("kind", ["price", "equity", "metadata", "mapping"])
def test_conflicting_or_unresolved_inputs_fail_safely(terminal, kind):
    _, s, t, p, e = terminal
    record = (
        change(p, token_price="11", provider_identifier="contradiction")
        if kind == "price"
        else change(e, price="101", provider_identifier="contradiction")
        if kind == "equity"
        else change(t, token_to_share_ratio="0.2", provider_identifier="contradiction")
    )
    if kind == "mapping":
        original = s.layer.repository.list
        from app.models.data import Issuer

        s.layer.repository.list = lambda model, **kw: (
            [] if model is Issuer else original(model, **kw)
        )
    else:
        s.layer.repository.save([record])
    row = board(terminal)[0]
    assert row["effective_price_per_share_usd"] is None
    assert row["deviation"] is None
    assert any("CONFLICT" in r or "MAPPING_UNRESOLVED" in r for r in row["reasons"])


def test_skew_and_future_availability_do_not_join(terminal):
    _, s, _, _, e = terminal
    original = s.layer.repository.list
    s.layer.repository.list = lambda model, **kw: (
        [change(e, source_timestamp=NOW - timedelta(seconds=31))]
        if model is EquityObservation
        else original(model, **kw)
    )
    assert "TIMESTAMP_SKEW_EXCEEDED" in board(terminal)[0]["reasons"]
    s.layer.repository.list = lambda model, **kw: (
        [change(e, ingestion_timestamp=NOW + timedelta(seconds=1))]
        if model is EquityObservation
        else original(model, **kw)
    )
    assert board(terminal)[0]["deviation"] is None


def test_closed_session_reference_is_actual_previous_regular_close(terminal):
    _, s, t, p, e = terminal
    at = NOW + timedelta(days=2)
    s.clock = lambda: at
    regime = s.trust.regimes.evaluate(at)
    fresh = dict(source_timestamp=at, ingestion_timestamp=at, raw_source_timestamp=at.isoformat())
    s.layer.repository.save([change(t, **fresh), change(p, **fresh)])
    previous = change(
        e,
        kind="REGULAR_CLOSE",
        interval="1minute",
        source_timestamp=regime.previous_regular_close - timedelta(minutes=1),
        ingestion_timestamp=at,
        raw_source_timestamp="close",
    )
    s.layer.repository.save([previous])
    row = board(terminal)[0]
    assert row["reference"]["status"] == "AVAILABLE"
    assert row["regime"] == "WEEKEND" and row["deviation"] == "0.02"


def test_trust_monitor_uses_persisted_engine_result_and_stale_abstention(terminal):
    client, s, _, _, _ = terminal
    sandbox = DemoTrustSandbox()
    result = sandbox.assess(
        "supported-move", run_id="test", request_id="test", correlation_id="test"
    ).assessment
    s.trust.repository.save(result)
    s.clock = lambda: result.evaluated_at
    q = TerminalQuery(ticker=result.ticker)
    rep = result.representations[0]
    row = s._monitor(result.ticker, s.clock(), rep.issuer, rep.contract)
    assert row.classification == rep.classification == "LIKELY_INFORMATION"
    assert row.stored_evidence.model_dump_json() == rep.model_dump_json()
    s.clock = lambda: result.evaluated_at + timedelta(seconds=121)
    row = s._monitor(result.ticker, s.clock(), rep.issuer, rep.contract)
    assert row.classification == "INSUFFICIENT_EVIDENCE" and row.confidence is None
    assert row.stored_evidence.classification == "LIKELY_INFORMATION"
    assert s.trust_monitor(q, s.clock()).items
    assert (
        client.get("/api/terminal/trust?ticker=UNSUPPORTED").json()["page"]["items"][0][
            "classification"
        ]
        == "INSUFFICIENT_EVIDENCE"
    )


def test_agent_evidence_is_bounded_structured_and_read_only(terminal):
    _, s, _, _, _ = terminal
    bundle = DemoEvidenceAdapter().load("supported-move")
    run = asyncio.run(AgentOrchestrator(store=s.agents).analyze(REQUEST, bundle))
    rows = s.agent_evidence(TerminalQuery(), run.timestamp + timedelta(seconds=1)).items
    assert len(rows) == 1 and len(rows[0].agents) == 6
    assert rows[0].decision == run.decision
    assert rows[0].evidence == run.evidence
    payload = rows[0].model_dump_json()
    assert "reasoning_summary" not in payload and "chain_of_thought" not in payload
    assert rows[0].agents[1].output == run.responses[1].output
    assert not s.agent_evidence(TerminalQuery(), run.timestamp - timedelta(seconds=1)).items
    assert not s.agents.list_runs("LIVE_READ_ONLY", run.timestamp)


def test_execution_analytics_use_canonical_positions_and_fixture_labels(terminal):
    _, s, _, _, _ = terminal
    portfolio, p, time = setup()
    try:
        s.execution, s.positions = portfolio.positions.execution.store, portfolio.positions
        plan = evaluate(portfolio)
        portfolio.prepare(
            plan.plan_id,
            plan.actions[0].action_id,
            allowance=allowance(),
        )
        rows = s.executions(TerminalQuery(), NOW).items
        confirmed = next(r for r in rows if r.category == "CONFIRMED")
        simulated = next(r for r in rows if r.category == "SIMULATED")
        assert confirmed.filled_base_units == p.filled_quantity_base_units
        assert confirmed.position_id == str(p.position_id)
        assert confirmed.remaining_base_units == "400000"
        assert confirmed.synthetic and not confirmed.actual_completed_trade
        assert simulated.simulation_status == "PASS" and simulated.filled_base_units is None
        assert simulated.quote_id and simulated.fingerprint and not simulated.actual_completed_trade
        assert simulated.realized_net_pnl_usd is None
        # A journal update can precede Phase 10 reconciliation. The old position snapshot
        # must not continue to advertise current ownership or realized financial metrics.
        canonical = s.execution.get(p.entry_execution.execution_id, mode=s.mode)
        older_snapshot = change(canonical, version=canonical.version - 1)
        stale_position = type(p).model_validate(
            {**p.model_dump(exclude_computed_fields=True), "entry_execution": older_snapshot}
        )
        s.positions.store.list = lambda **kwargs: [stale_position]
        behind = next(
            r
            for r in s.executions(TerminalQuery(), NOW).items
            if r.position_id == str(p.position_id)
        )
        assert behind.category == "RECONCILIATION_REQUIRED"
        assert behind.remaining_base_units is None and behind.realized_net_pnl_usd is None
        assert not behind.actual_completed_trade
        assert "POSITION_EXECUTION_SNAPSHOT_BEHIND_JOURNAL" in behind.reasons
    finally:
        portfolio.store.close()
        portfolio.positions.store.close()
        portfolio.positions.execution.store.close()


@pytest.fixture(scope="module")
def replay():
    cal = calendar.__wrapped__()
    episodes = dataset.__wrapped__(cal, fixture.__wrapped__())
    return HistoricalReplay(ResearchPolicy(model_features=("deviation",))).run(
        episodes, provenance=("SYNTHETIC_TEST",)
    )


def test_historical_episode_cutoff_separates_outcome_from_decision(terminal, replay):
    _, s, _, _, _ = terminal
    s.research.save(replay)
    episode = replay.episodes[0]
    at = episode.decision.decision_at
    before = s.episodes(EpisodeQuery(as_of=at), NOW).items
    assert len(before) == 1 and before[0].opening_outcome is None
    assert before[0].outcome_state == "NOT_YET_AVAILABLE"
    after = s.episodes(EpisodeQuery(as_of=episode.target.available_at), NOW).items
    assert after[0].opening_outcome == episode.target
    assert after[0].prediction == before[0].prediction
    assert after[0].retrieval == before[0].retrieval
    assert after[0].deviation == before[0].deviation
    assert after[0].evidence_kind == "SYNTHETIC_TEST"


def test_historical_pagination_mode_corruption_and_bounds(terminal, replay):
    _, s, _, _, _ = terminal
    file = s.research.save(replay)
    assert len(s.episodes(EpisodeQuery(limit=3, offset=3), NOW).items) == 3
    assert s.episodes(EpisodeQuery(limit=3), NOW).has_more
    assert not s.research.list("LIVE")
    file.write_text(file.read_text().replace('"sha256": "', '"sha256": "bad'))
    assert terminal[0].get("/api/terminal/episodes").status_code == 503


@pytest.mark.parametrize(
    "path", ["", "/issuers", "/prices", "/trust", "/agents", "/executions", "/episodes"]
)
def test_api_contracts_get_only_and_do_not_invoke_provider_or_mutations(terminal, path):
    client, s, _, _, _ = terminal

    def denied(*args, **kwargs):
        raise AssertionError("Terminal attempted a provider or state mutation")

    s.layer.discovery.resolve = denied
    s.trust.assess = denied
    s.portfolio.evaluate = denied
    s.positions.reconcile = denied
    before = s.layer.repository.list(TokenMetadata, mode="DEMO")
    response = client.get("/api/terminal" + path)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["broadcast"] is False and data["execution_ready"] is False
    assert data["request_id"] == response.headers["X-Request-ID"]
    assert data["production_gates"]["TRUST_GATE"] == "BLOCKED"
    assert s.layer.repository.list(TokenMetadata, mode="DEMO") == before
    assert client.post("/api/terminal" + path, json={"execute": True}).status_code == 405


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "offset=-1",
        "offset=10001",
        "ticker=../bad",
        "data_mode=LIVE",
        "execute=true",
        "as_of=2026-10-08T00:00:00Z",
    ],
)
def test_invalid_or_authorizing_query_rejected(terminal, query):
    assert terminal[0].get("/api/terminal?" + query).status_code == 422


def test_future_cutoff_and_missing_asset_stay_safe(terminal):
    client, _, _, _, _ = terminal
    assert client.get("/api/terminal/episodes?as_of=2027-01-01T00:00:00Z").status_code == 503
    payload = client.get("/api/terminal?ticker=ZZZZ").json()
    assert (
        not payload["issuers"]["items"]
        and payload["trust"]["items"][0]["classification"] == "INSUFFICIENT_EVIDENCE"
    )
    assert payload["portfolio"]["status"] == "NOT_CONFIGURED"


@pytest.mark.parametrize(
    "state,category", [("EXECUTION_PENDING", "SUBMITTED"), ("EXECUTION_UNKNOWN", "UNKNOWN")]
)
def test_pending_unknown_quantity_is_not_a_fill_or_owned_balance(terminal, state, category):
    from backend.tests.unit.test_position import runtime

    _, s, _, _, _ = terminal
    manager, p, time = runtime(confirmed=False, pending=state)
    try:
        s.execution, s.positions = manager.execution.store, manager
        row = s.executions(TerminalQuery(), NOW).items[0]
        assert row.category == category and row.filled_base_units is None
        assert row.remaining_base_units is None and row.realized_net_pnl_usd is None
        assert not row.actual_completed_trade
    finally:
        manager.store.close()
        manager.execution.store.close()


def test_live_cached_pipeline_is_not_demo_only(terminal):
    _, s, t, p, e = terminal

    issuer = load_data_fixture()["issuers"][0]
    live = dict(data_mode="LIVE", data_quality="LIVE")
    s.layer.repository.save(
        [
            change(t, **live, source="BINANCE_RWA", chain_id="56", contract="0x" + "1" * 40),
            change(p, **live, source="BINANCE_RWA", chain_id="56", contract="0x" + "1" * 40),
            change(e, **live, source="MASSIVE"),
            change(issuer, **live, source="BINANCE_RWA", chains=("56",)),
        ]
    )
    s.layer.mode = "LIVE"
    rows = s.issuers(TerminalQuery(ticker="NVDA"), NOW).items
    assert len(rows) == 1 and rows[0].effective_price_per_share_usd == D("102")
    assert rows[0].reference.observation.source == "MASSIVE"
    assert not any(o.source.startswith("DEMO") for o in rows[0].observations)
    assert rows[0].route_status == "NOT_QUOTED"


def test_bounded_catalog_and_malformed_financial_data_fail_closed(terminal):
    client, s, token, _, _ = terminal
    original = s.layer.repository.list
    s.layer.repository.list = lambda model, **kw: (
        [token] * 1000 if model is TokenMetadata else original(model, **kw)
    )
    assert client.get("/api/terminal").status_code == 503
    for ratio in ["0", "-1", "NaN", 0.1, True]:
        with pytest.raises(ValueError):
            change(token, token_to_share_ratio=ratio)


def test_portfolio_context_is_existing_persisted_decision_only(terminal):
    from backend.tests.integration.test_portfolio_api import body

    client, s, _, _, _ = terminal
    assert client.post("/api/autopilot", json=body()).status_code == 200
    before = s.portfolio.store.audit(mode=s.mode)
    context = client.get("/api/terminal").json()["portfolio"]
    assert context["config_version"] == 1 and context["status"] == "NO_PENDING_PLAN"
    assert s.portfolio.store.audit(mode=s.mode) == before


@pytest.mark.parametrize(
    "key",
    ["chain_of_thought", "hidden_reasoning", "private_key", "userSignature", "typedDataToSign"],
)
def test_no_hidden_or_execution_payload_projection(key):
    from app.api.terminal import safe_projection

    with pytest.raises(ValueError):
        safe_projection({"nested": [{key: "not exposed"}]})
