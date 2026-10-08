"""Phase 15 read inspection contract. Synthetic fixtures do not verify wallet/providers."""

from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.api.workspace import WorkspaceState
from app.models.agent_api import project_portfolio
from backend.tests.unit.test_portfolio import evaluate, setup


def test_workspace_is_bounded_non_executable_and_authoritative(client, application, monkeypatch):
    for obj, method in (
        (application.state.portfolio, "capture"),
        (application.state.safety_execution.gateway.adapter, "snapshot"),
        (application.state.safety_execution, "prepare"),
    ):
        monkeypatch.setattr(obj, method, Mock(side_effect=AssertionError("Forbidden path")))
    correlation = str(uuid4())
    response = client.get("/api/workspace", headers={"X-Correlation-ID": correlation})
    assert response.status_code == 200
    result = WorkspaceState.model_validate_json(response.content)
    assert result.correlation_id == correlation
    assert result.request_id == response.headers["x-request-id"]
    assert not result.broadcast and not result.execution_ready
    assert result.wallet.status == "WALLET_UNAVAILABLE"
    assert result.wallet.connection == "UNKNOWN" and result.wallet.balance is None
    assert result.portfolio == project_portfolio(application.state.portfolio.state())
    assert not result.positions and result.position_history_complete
    assert result.production_gates.TRUST_GATE == "BLOCKED"
    assert result.production_gates.OPPORTUNITY_GATE == "BLOCKED_BY_TRUST"


@pytest.mark.parametrize("confirmed", [True, False])
def test_workspace_preserves_existing_position_and_plan_states(client, application, confirmed):
    portfolio, position, _ = setup(confirmed=confirmed)
    try:
        plan = evaluate(portfolio)
        application.state.portfolio = portfolio
        application.state.positions = portfolio.positions
        result = WorkspaceState.model_validate(client.get("/api/workspace").json())
        assert result.portfolio.latest_decision.plan_id == plan.plan_id
        assert result.portfolio.latest_decision.rows == plan.rows
        assert result.positions[0].state == position.state
        assert result.positions[0].normalized_share_exposure == position.normalized_share_exposure
        assert "entry_execution" not in result.model_dump_json()
        if not confirmed:
            assert result.positions[0].state == "OPENING"
            assert result.positions[0].remaining_quantity_base_units == "0"
    finally:
        portfolio.store.close()
        portfolio.positions.store.close()
        portfolio.positions.execution.store.close()


def test_configured_host_worker_does_not_become_public_wallet(client, application):
    application.state.safety_execution.gateway.adapter.client = Mock(
        read=Mock(side_effect=AssertionError("Do not call host CLI"))
    )
    result = WorkspaceState.model_validate(client.get("/api/workspace").json())
    assert result.wallet.status == "UNKNOWN" and result.wallet.address is None
    assert not result.wallet.execution_ready


@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_workspace_has_no_mutation_surface(client, method):
    assert getattr(client, method)("/api/workspace").status_code == 405


def test_workspace_queries_cannot_override_modes(client):
    assert client.get("/api/workspace?execution_mode=LIVE").status_code == 422


def test_workspace_projection_errors_fail_closed(client, application, monkeypatch):
    monkeypatch.setattr(
        application.state.portfolio, "state", Mock(side_effect=ValueError("secret"))
    )
    result = client.get("/api/workspace")
    assert result.status_code == 503 and "secret" not in result.text


def test_workspace_unknown_position_remains_unowned(client, application):
    from backend.tests.unit.test_position import runtime

    manager, _, _ = runtime(confirmed=False, pending="EXECUTION_UNKNOWN")
    try:
        application.state.positions = manager
        result = WorkspaceState.model_validate(client.get("/api/workspace").json())
        row = result.positions[0]
        assert row.state == "UNKNOWN"
        assert row.remaining_quantity_base_units == "0"
        assert row.normalized_share_exposure == 0
    finally:
        manager.store.close()
        manager.execution.store.close()
