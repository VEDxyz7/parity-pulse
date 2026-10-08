"""SUCCESS must satisfy the exact artifact's bounded allowance safety envelope."""

from decimal import Decimal

import pytest

from app.clients.execution_gateway import DryRunExecutionGateway
from app.models.execution import (
    ExecutionControls,
    PreparedApproval,
    SimulationResponse,
    fingerprint,
)
from app.services.execution_builders import ApprovalService, ExecutionRouteBuilder
from app.services.execution_simulation import ExecutionSimulationService
from backend.tests.fixtures.execution_fixtures import (
    BUY,
    NOW,
    SELL,
    SPENDER,
    WALLET,
    FixtureProvider,
    allowance,
    approval_response,
    build,
    funding,
    mutate,
    quote,
    request,
)
from backend.tests.unit.test_agentic_wallet import prepared


def artifacts():
    q = quote(request())
    route = ExecutionRouteBuilder().build(
        q, build(q), slippage_bps=Decimal(50), allowance=allowance("0"), now=NOW
    )
    approval = ApprovalService().prepare(route, approval_response(q.request.amount), now=NOW)
    return route, approval


def response(**changes):
    value = dict(
        tokenAddress=SELL, owner=WALLET, spender=SPENDER, preAmount="0", postAmount=request().amount
    )
    value.update(changes)
    return SimulationResponse(status="SUCCESS", balanceChanges=(), allowanceChanges=(value,))


def test_correct_bounded_approval_passes_and_exact_allowance_confirms():
    route, approval = artifacts()
    provider = FixtureProvider()
    provider.response_override = response()
    result = ExecutionSimulationService(provider).simulate(approval, now=NOW, mode="DEMO")
    assert result.status == "PASS"
    assert ExecutionSimulationService.matches(result, approval, now=NOW, mode="DEMO")
    assert ApprovalService().confirmed(approval, route, allowance(approval.amount), now=NOW)
    assert not ApprovalService().confirmed(approval, route, allowance(str(2**256 - 1)), now=NOW)


@pytest.mark.parametrize(
    "change",
    [
        {"postAmount": str(2**256 - 1)},
        {"tokenAddress": BUY},
        {"spender": BUY},
        {"owner": BUY},
        {"preAmount": "1"},
        {"postAmount": "0"},
        {"postAmount": "1"},
    ],
)
def test_approval_wrong_token_owner_spender_amount_or_unlimited_fails(change):
    _, approval = artifacts()
    p = FixtureProvider()
    p.response_override = response(**change)
    service = ExecutionSimulationService(p)
    result = service.simulate(approval, now=NOW, mode="DEMO")
    assert result.status == "FAIL"
    assert "ALLOWANCE_SAFETY_ENVELOPE_VIOLATED" in result.reason_codes
    assert not service.matches(result, approval, now=NOW, mode="DEMO")
    assert not service.matches(mutate(result, status="PASS"), approval, now=NOW, mode="DEMO")


@pytest.mark.parametrize("changes", [(), (response().allowanceChanges[0],) * 2])
def test_missing_or_duplicate_expected_approval_fails(changes):
    _, approval = artifacts()
    p = FixtureProvider()
    p.response_override = SimulationResponse(
        status="SUCCESS", balanceChanges=(), allowanceChanges=changes
    )
    assert ExecutionSimulationService(p).simulate(approval, now=NOW, mode="DEMO").status == "FAIL"


@pytest.mark.parametrize(
    "field,value",
    [
        ("preAmount", "-1"),
        ("postAmount", "-1"),
        ("postAmount", "NaN"),
        ("postAmount", True),
        ("postAmount", 1),
        ("postAmount", str(2**256)),
    ],
)
def test_malformed_allowance_even_constructed_provider_success_fails(field, value):
    _, approval = artifacts()
    good = response()
    bad = good.allowanceChanges[0].model_copy(update={field: value})
    p = FixtureProvider()
    p.response_override = good.model_copy(update={"allowanceChanges": (bad,)})
    result = ExecutionSimulationService(p).simulate(approval, now=NOW, mode="DEMO")
    assert result.status == "FAIL" and result.response is None


@pytest.mark.parametrize(
    "change",
    [
        {"postAmount": "100000001"},
        {"postAmount": str(2**256 - 1)},
        {"spender": BUY},
        {"tokenAddress": BUY},
        {"owner": BUY},
        {"postAmount": "0"},
    ],
)
def test_swap_unexpected_grant_cannot_pass_simulation_or_gateway(change):
    _, attempt = prepared()
    p = FixtureProvider()
    p.response_override = response(preAmount=attempt.route.allowance.amount, **change)
    simulation = ExecutionSimulationService(p).simulate(attempt.route, now=NOW)
    assert simulation.status == "FAIL"
    # Forging PASS is insufficient: the gateway repeats the same envelope predicate.
    forged = mutate(attempt, simulation=mutate(simulation, status="PASS"))
    reasons = DryRunExecutionGateway(ExecutionControls(data_mode="DEMO")).submit(
        forged, now=NOW, funding_state=funding()
    )
    assert "EXACT_SIMULATION_REQUIRED" in reasons and "DRY_RUN_STOP_NO_EXECUTION" in reasons


def test_swap_no_change_or_bounded_consumption_passes_without_live_equivalence():
    _, attempt = prepared()
    p = FixtureProvider()
    s = ExecutionSimulationService(p)
    assert s.simulate(attempt.route, now=NOW).status == "PASS"
    p.response_override = response(
        preAmount=attempt.route.allowance.amount,
        postAmount=str(int(attempt.route.allowance.amount) - int(attempt.quote.request.amount)),
    )
    result = s.simulate(attempt.route, now=NOW)
    assert result.status == "PASS" and not result.live_equivalence_verified


def test_refingerprinted_approval_cannot_hide_different_calldata_or_grant():
    _, approval = artifacts()
    for changes in (
        {"data": approval.transaction.data[:-64] + "f" * 64},
        {"to": BUY},
        {"value": "1"},
    ):
        raw = approval.model_dump(mode="json", by_alias=True)
        raw["transaction"].update(changes)
        raw["fingerprint"] = fingerprint({k: v for k, v in raw.items() if k != "fingerprint"})
        with pytest.raises(ValueError, match="Exact bounded approval"):
            PreparedApproval.model_validate(raw)


def test_rebound_approval_wallet_cannot_confirm_against_the_original_route():
    route, approval = artifacts()
    raw = approval.model_dump(mode="json", by_alias=True)
    raw["transaction"]["from"] = BUY
    raw["fingerprint"] = fingerprint({k: v for k, v in raw.items() if k != "fingerprint"})
    rebound = PreparedApproval.model_validate(raw)
    assert not ApprovalService().confirmed(
        rebound, route, allowance(approval.amount, owner=BUY), now=NOW
    )
