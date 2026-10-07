"""Shared route rules, exact economics, provenance, no first-row or issuer shortcuts."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.routing import RouteIdentity, RouteInput, RoutePolicy
from app.services.routing import RoutingService

NOW = datetime(2026, 10, 7, 15, tzinfo=UTC)


def candidate(issuer="issuer-a", price="50", ratio="1", mode="LIVE", **changes):
    return RouteInput.model_validate(
        dict(
            identity=RouteIdentity(
                underlying="NVDA",
                issuer=issuer,
                chain_id="56" if mode == "LIVE" else "DEMO",
                contract="test-only:" + issuer if mode == "LIVE" else "demo:" + issuer,
                token=issuer + "NVDA",
            ),
            data_mode=mode,
            token_price_usd=price,
            token_to_share_ratio=ratio,
            price_source="OFFLINE_TEST",
            price_timestamp=NOW,
            price_quality="LIVE" if mode == "LIVE" else "DEMO",
            ratio_source="OFFLINE_TEST_METADATA",
            ratio_observed_at=NOW,
            ratio_source_timestamp=NOW,
            market_state="regular",
            tradable=True,
            **changes,
        )
    )


def updated(model, **changes):
    return type(model).model_validate({**model.model_dump(), **changes})


def decide(rows, policy=None, mode="LIVE", notional="50"):
    return RoutingService().decide("NVDA", notional, rows, mode=mode, now=NOW, policy=policy)


def known(row, **changes):
    return updated(
        row,
        fees_usd="0.10",
        gas_usd="0.05",
        slippage_bps="20",
        cost_status="AVAILABLE",
        cost_source="TEST_QUOTE",
        cost_timestamp=NOW,
        **changes,
    )


def full(row, **changes):
    return updated(
        known(row),
        liquidity_usd="5000",
        liquidity_status="AVAILABLE",
        liquidity_source="TEST_LIQUIDITY_USD",
        liquidity_timestamp=NOW,
        trust_state="LIKELY_INFORMATION",
        trust_source="TEST_TRUST",
        trust_timestamp=NOW,
        trust_assessment_id=uuid4(),
        risk_state="PASS",
        risk_source="TEST_RISK",
        risk_timestamp=NOW,
        risk_id=uuid4(),
        risk_max_notional_usd="50",
        route_available=True,
        route_support="VERIFIED_PROVIDER_ROUTE",
        **changes,
    )


def strict():
    return RoutePolicy(
        purpose="OPPORTUNITY",
        require_costs=True,
        require_liquidity=True,
        require_trust=True,
        require_risk=True,
        min_liquidity_usd="1000",
        max_slippage_bps="50",
    )


def test_multiple_candidates_cheapest_share_cost_not_token_price_wins():
    result = decide([candidate(price="130"), candidate("issuer-b", price="250", ratio="2")])
    assert result.status == "ROUTE_SELECTED" and result.issuer == "issuer-b"
    assert result.selected_candidate.effective_cost_per_share_usd == 125
    assert len(result.candidates) == 2 and result.selected_candidate.rank == 1
    assert (
        result.ranking_basis == "TOKEN_PRICE_ONLY"
        and result.selected_candidate.estimated_costs_usd is None
    )
    assert not result.execution_ready and not result.transaction_broadcast


def test_costs_slippage_and_requested_notional_change_selection_with_explicit_formula():
    a = updated(known(candidate(price="50")), fees_usd="1", gas_usd="0", slippage_bps="0")
    b = updated(
        known(candidate("issuer-b", price="50.5")), fees_usd="0", gas_usd="0", slippage_bps="0"
    )
    result = decide([a, b])
    assert result.issuer == "issuer-b" and result.ranking_basis == "ALL_IN_ESTIMATE"
    assert (
        next(
            c for c in result.candidates if c.inputs.identity.issuer == "issuer-a"
        ).all_in_cost_per_share_usd
        == 51
    )
    assert decide([a, b], notional="200").issuer == "issuer-a"
    assert decide([updated(a, fees_usd="0"), b]).issuer == "issuer-a"
    assert decide([updated(a, fees_usd="0", slippage_bps="200"), b]).issuer == "issuer-b"
    assert result.policy.weights is None


def test_unknown_costs_use_common_price_only_basis_never_zero_or_mixed_scores():
    a = known(candidate(price="49"))
    b = candidate("issuer-b", price="50")
    result = decide([a, b])
    assert result.ranking_basis == "TOKEN_PRICE_ONLY"
    assert result.candidates[0].ranking_cost_per_share_usd == 49
    assert result.candidates[1].estimated_costs_usd is None
    required = decide([a, b], RoutePolicy(require_costs=True))
    assert required.ranking_basis == "ALL_IN_ESTIMATE" and required.issuer == "issuer-a"
    assert "REQUIRED_COSTS_UNAVAILABLE" in required.candidates[1].rejection_reasons


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"liquidity_usd": "999"}, "INSUFFICIENT_LIQUIDITY"),
        ({"liquidity_usd": "0"}, "INSUFFICIENT_LIQUIDITY"),
        ({"liquidity_status": "UNVERIFIED"}, "REQUIRED_LIQUIDITY_UNVERIFIED"),
        ({"liquidity_timestamp": NOW - timedelta(seconds=120)}, "REQUIRED_LIQUIDITY_STALE"),
        ({"trust_state": "LIKELY_NOISE"}, "TRUST_REQUIREMENT_FAILED"),
        ({"trust_state": "INSUFFICIENT_EVIDENCE"}, "TRUST_REQUIREMENT_FAILED"),
        ({"trust_timestamp": NOW - timedelta(seconds=120)}, "TRUST_REQUIREMENT_FAILED"),
        ({"risk_state": "FAIL"}, "RISK_FAILED"),
        ({"risk_max_notional_usd": "49"}, "RISK_NOTIONAL_LIMIT"),
        ({"slippage_bps": "51"}, "SLIPPAGE_LIMIT"),
        ({"tradable": False}, "REPRESENTATION_NOT_TRADABLE"),
        ({"market_state": "pause"}, "REPRESENTATION_NOT_TRADABLE"),
        ({"market_state": "overnight"}, "REPRESENTATION_NOT_TRADABLE"),
        ({"supported": False}, "UNSUPPORTED_OR_INVALID_NORMALIZATION"),
        ({"route_available": False}, "ROUTE_UNAVAILABLE"),
        ({"route_available": None}, "REQUIRED_ANALYTICAL_ROUTE_UNAVAILABLE"),
        ({"route_support": "INDICATIVE_ONLY"}, "REQUIRED_ANALYTICAL_ROUTE_UNAVAILABLE"),
        ({"token_price_usd": None}, "TOKEN_PRICE_UNAVAILABLE"),
        ({"price_timestamp": NOW - timedelta(seconds=120)}, "PRICE_OR_RATIO_NOT_FRESH_VERIFIED"),
        ({"price_timestamp": NOW + timedelta(seconds=1)}, "PRICE_OR_RATIO_NOT_FRESH_VERIFIED"),
        ({"cost_timestamp": NOW - timedelta(seconds=120)}, "REQUIRED_COSTS_STALE"),
    ],
)
def test_filters_reject_cheaper_invalid_candidate_before_ranking(changes, reason):
    bad = updated(full(candidate(price="49")), **changes)
    good = full(candidate("issuer-b", price="50"))
    result = decide([bad, good], strict())
    assert result.issuer == "issuer-b"
    rejected = next(c for c in result.candidates if c.inputs.identity.issuer == "issuer-a")
    assert not rejected.eligible and rejected.rank is None and reason in rejected.rejection_reasons


def test_no_routes_and_empty_unresolved_requests_are_safe():
    assert decide([]).status == "NO_ROUTE"
    result = decide([updated(candidate(), tradable=False)])
    assert result.selected_candidate is None and result.selected_representation is None
    assert RoutingService().decide(None, None, [], mode="LIVE", now=NOW).status == "NO_ROUTE"


def test_conflicting_labels_for_one_contract_reject_the_whole_comparison():
    a = candidate()
    b = candidate("issuer-b")
    b = updated(b, identity=updated(b.identity, contract=a.identity.contract))
    result = decide([a, b])
    assert result.status == "NO_ROUTE"
    assert all(
        "DUPLICATE_OR_MIXED_UNDERLYING_MODE" in c.rejection_reasons for c in result.candidates
    )


def test_exact_ranking_is_order_invariant_even_when_display_values_round_equal():
    a = candidate(price="50.0000000000000000002")
    b = candidate("issuer-b", price="50.0000000000000000001")
    one = decide([a, b])
    two = decide([b, a])
    assert one == two and one.issuer == "issuer-b"
    assert (
        one.candidates[0].effective_cost_per_share_usd
        == one.candidates[1].effective_cost_per_share_usd
    )
    assert decide([candidate("z"), candidate("a")]).issuer == "a"


def test_demo_and_live_share_exact_same_algorithm_and_selection():
    live = [candidate(price="51"), candidate("issuer-b", price="50")]
    demo = [candidate(price="51", mode="DEMO"), candidate("issuer-b", price="50", mode="DEMO")]
    assert decide(live).issuer == decide(demo, mode="DEMO").issuer == "issuer-b"
    assert decide(live).policy == decide(demo, mode="DEMO").policy
    assert decide([demo[0], live[1]]).status == "NO_ROUTE"


def test_duplicate_identity_and_conflicting_underlying_fail_entire_decision():
    a = candidate()
    assert decide([a, a]).status == "NO_ROUTE"
    b = updated(
        candidate("issuer-b"), identity=updated(candidate("issuer-b").identity, underlying="AAPL")
    )
    assert decide([a, b]).status == "NO_ROUTE"


def test_strict_missing_evidence_not_synthetic_execution_and_malformed_inputs_rejected():
    result = decide([candidate()], strict())
    assert result.status == "NO_ROUTE"
    with pytest.raises(ValidationError):
        RoutePolicy(purpose="OPPORTUNITY")
    with pytest.raises(ValidationError):
        candidate(price=50.0)
    with pytest.raises(ValidationError):
        candidate(ratio="NaN")
    with pytest.raises(ValidationError):
        candidate(fees_usd="-1")
    row = updated(full(candidate()), route_support="SYNTHETIC_DEMO_PREPARATION")
    assert decide([row], strict()).status == "NO_ROUTE"
