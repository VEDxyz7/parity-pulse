"""Offline integration evidence: presentation uses existing engines, never real observations."""

from decimal import Decimal as D

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect, text

from app.config import Settings
from app.main import create_app
from app.models.presentation import ScanRequest, ScenarioRequest
from app.models.trust import TrustPolicy
from app.services.presentation import PresentationService


@pytest.fixture
def service(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Presentation must not access an external transport")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    return PresentationService()


@pytest.mark.parametrize(
    "preset,classification,status",
    [
        ("normal", "NORMAL", "NO_OPPORTUNITY"),
        ("low-liquidity", "LIKELY_NOISE", "REJECTED_BY_TRUST"),
        ("news", "LIKELY_INFORMATION", "ACTIONABLE"),
        ("above", "INSUFFICIENT_EVIDENCE", "REJECTED_BY_TRUST"),
        ("below", "INSUFFICIENT_EVIDENCE", "REJECTED_BY_TRUST"),
    ],
)
def test_existing_engines_decide_from_inputs(service, preset, classification, status):
    result = service.analyze(ScenarioRequest(preset=preset))
    row = result.trust.representations[0]
    assert row.classification == classification
    assert result.opportunity.status == status
    assert result.trust.policy == TrustPolicy()
    assert result.provenance.production_eligible is False
    assert result.trust.trust_gate == "BLOCKED"
    assert result.opportunity.transaction_broadcast is False
    if status == "ACTIONABLE":
        assert result.risk.status == "PASS"
        assert result.route.status == "ROUTE_SELECTED"
        assert result.quote.status == "QUOTED"
        assert result.preparation.status == "PREPARED"
        assert result.simulation.simulation.status == "SIMULATION_PASS"
        assert result.quote.quote.executable is False
        assert result.preparation.transaction.signed is False
    else:
        assert result.quote is None
        assert result.simulation is None


@pytest.mark.parametrize("ticker", ["NVDA", "AAPL"])
@pytest.mark.parametrize("representation", ["atlas", "meridian"])
def test_identity_normalization_and_history_are_coherent(service, ticker, representation):
    result = service.analyze(ScenarioRequest(ticker=ticker, representation=representation))
    row = result.trust.representations[0]
    assert row.contract == result.contract
    assert row.token_to_share_ratio == result.share_ratio
    assert abs(result.effective_cost - result.token_price / result.share_ratio) < D("1e-25")
    assert abs(result.deviation - (result.effective_cost / result.equity_price - 1)) < D("1e-25")
    assert result.history[-1].token == result.token_price
    assert result.history[-1].equity == result.equity_price
    assert result.history[-1].effective == result.effective_cost
    assert result.history[-1].at == result.provenance.as_of
    assert len(result.history) == 48
    assert all(a.at < b.at for a, b in zip(result.history, result.history[1:], strict=False))
    assert abs(result.share_exposure - result.token_quantity * result.share_ratio) < D("1e-25")


def test_repeated_reads_and_saved_studies(service):
    request = ScenarioRequest()
    a, b = service.analyze(request), service.analyze(request)
    assert a == b
    service.save(a)
    assert service.inspect(a.id) == a
    service.capacity = 1
    service.save(service.analyze(ScenarioRequest(preset="normal")))
    with pytest.raises(LookupError):
        service.inspect(a.id)
    with pytest.raises(LookupError):
        service.inspect("not-a-study")


def test_research_controls_recompute_not_relabel(service):
    base = service.analyze(ScenarioRequest())
    changed = service.analyze(ScenarioRequest(token_price="55", equity_price="105", liquidity="20"))
    assert changed.effective_cost == D("110")
    assert changed.deviation != base.deviation
    assert changed.liquidity == 20
    assert changed.risk.status == "FAIL"
    assert changed.quote is None
    assert changed.trust.representations[0].classification != "LIKELY_INFORMATION"
    assert changed.inputs != base.inputs


@pytest.mark.parametrize(
    "inputs",
    [
        {"fees": "50"},
        {"slippage_bps": "1000"},
        {"risk_budget": "0.01"},
        {"liquidity": "0"},
        {"window": "reopening"},
    ],
)
def test_constraints_stand_down_without_bypass(service, inputs):
    result = service.analyze(ScenarioRequest(**inputs))
    assert result.risk.status == "FAIL"
    assert result.simulation is None
    assert result.preparation is None


def test_scan_uses_shared_lexicographic_policy_and_universe(service):
    result = service.scan(ScanRequest())
    assert [(r.inputs.ticker, r.inputs.representation, r.rank) for r in result.candidates] == [
        ("NVDA", "atlas", 1),
        ("NVDA", "meridian", 2),
        ("AAPL", "atlas", None),
        ("AAPL", "meridian", None),
    ]
    restricted = service.scan(ScanRequest(universe=["AAPL"]))
    assert len(restricted.candidates) == 2
    assert all(r.rank is None for r in restricted.candidates)
    reopening = service.scan(ScanRequest(window="reopening"))
    assert all(r.rank is None and r.opportunity.status == "REJECTED" for r in reopening.candidates)


def test_shared_router_compares_actual_costs(service):
    route = service.exposure("NVDA", D("60"))
    assert len(route.candidates) == 2
    assert route.status == "ROUTE_SELECTED"
    selected = route.selected_candidate
    assert selected.inputs.identity.issuer == "presentation-atlas"
    assert selected.ranking_cost_per_share_usd == min(
        c.ranking_cost_per_share_usd for c in route.candidates
    )
    assert not route.execution_ready
    assert not route.transaction_broadcast


def test_portfolio_and_scorecard_derive_from_underlying_records(service):
    workspace = service.workspace()
    assert workspace.portfolio_value == sum(h.value for h in workspace.holdings)
    assert workspace.portfolio_pnl == sum(h.pnl for h in workspace.holdings)
    assert workspace.portfolio_cost == sum(h.cost_basis for h in workspace.holdings)
    assert abs(sum(h.weight for h in workspace.holdings) - 1) < D("1e-25")
    assert abs(sum(h.suggested_notional for h in workspace.holdings)) < D("1e-20")
    for h in workspace.holdings:
        a = next(
            a for a in workspace.assets if a.inputs.ticker == h.ticker and a.issuer_name == h.issuer
        )
        assert h.value == h.quantity * a.token_price
    assert workspace.evaluation_count == len(workspace.evaluations) == 60
    assert workspace.correct_count == sum(r.correct for r in workspace.evaluations)
    assert workspace.accuracy == D(workspace.correct_count) / workspace.evaluation_count
    assert all(r.correct == (r.prediction == r.outcome) for r in workspace.evaluations)
    assert service.workspace() == workspace


@pytest.mark.parametrize(
    "body",
    [
        {"ticker": "TSLA"},
        {"token_price": "NaN"},
        {"token_price": 50.1},
        {"liquidity": "-1"},
        {"budget": "0"},
        {"fees": "Infinity"},
        {"token_price": "1e1000"},
        {"budget": "0.0000000000001"},
        {"execution_ready": True},
    ],
)
def test_invalid_inputs_fail_closed(body):
    with pytest.raises(ValidationError):
        ScenarioRequest.model_validate(body)


def test_api_available_without_demo_runtime_and_no_production_writes(tmp_path):
    app = create_app(Settings(_env_file=None, app_env="test", database_url="sqlite:///:memory:"))
    with TestClient(app) as client:

        def counts():
            with app.state.database.engine.connect() as db:
                return {
                    t: db.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
                    for t in inspect(db).get_table_names()
                }

        before = counts()
        status = client.get("/api/system-status").json()
        assert client.get("/api/health").status_code == 200
        w = client.get("/api/presentation/workspace")
        assert w.status_code == 200
        assert w.json()["provenance"]["source_kind"] == "PRESENTATION_SCENARIO"
        study = client.post("/api/presentation/research", json={"preset": "news"})
        assert study.status_code == 200
        identifier = study.json()["id"]
        assert client.get("/api/presentation/research/" + identifier).json() == study.json()
        assert client.post("/api/presentation/scan", json={}).status_code == 200
        assert client.post("/api/presentation/exposure", json={}).status_code == 200
        assert (
            client.post("/api/presentation/research", json={"ticker": "UNKNOWN"}).status_code == 422
        )
        assert client.get("/api/presentation/research/missing").status_code == 404
        assert counts() == before
        after = client.get("/api/system-status").json()
        assert after["gates"] == status["gates"]
        assert after["live_trading_enabled"] is False
        assert after["execution_mode"] == "DRY_RUN"
        assert client.post("/api/presentation/execute", json={}).status_code == 404


def test_large_budget_is_capped_by_existing_policy(service):
    result = service.analyze(ScenarioRequest(budget="10000"))
    assert result.risk.status == "PASS"
    assert result.risk.proposed_notional_usd == D("50")
    assert result.risk.proposed_notional_usd <= result.risk.maximum_allowed_notional_usd
    assert result.quote.quote.total_cash_required_usd <= D("100")
