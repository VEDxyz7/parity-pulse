"""Economic and financial decisions are calculated from evidence, never scenario titles."""

from datetime import timedelta
from decimal import Decimal, localcontext

import pytest
from pydantic import ValidationError

from app.models.demo_opportunity import DemoOpportunityFixture
from app.models.demo_sandbox import DemoTrustDataset
from app.models.opportunity import OpportunityInputs
from app.models.risk import RiskInputs, RiskPolicy
from app.models.trust import RepresentationTrust, TrustAssessment
from app.services.demo_opportunity import DemoOpportunityFlow
from app.services.demo_sandbox import DemoTrustSandbox
from app.services.opportunity import OpportunityEngine, rounded
from app.services.risk import RiskEngine

IDS = dict(run_id="unit-demo", request_id="unit-demo", correlation_id="unit-demo")


def altered(model, **updates):
    return type(model).model_validate({**model.model_dump(), **updates})


@pytest.fixture
def inputs():
    sandbox = DemoTrustSandbox()
    fixture = DemoOpportunityFlow(sandbox).fixture
    assessment = sandbox.assess("supported-move", **IDS).assessment
    token = sandbox.datasets["supported-move"].token.record
    return assessment, token, fixture


def opportunity(
    inputs, *, economic_changes=None, row_changes=None, assessment_changes=None, offset=0
):
    assessment, token, fixture = inputs
    row = altered(assessment.representations[0], **(row_changes or {}))
    assessment = altered(assessment, representations=[row], **(assessment_changes or {}))
    economics = altered(fixture.economics, **(economic_changes or {}))
    return OpportunityEngine().evaluate(
        assessment,
        row,
        token,
        economics,
        now=assessment.evaluated_at + timedelta(seconds=offset),
    )


def test_correct_normalization_adjustment_and_cost_adjusted_usd_edge(inputs):
    result = opportunity(inputs)
    e = result.economics
    assert result.status == "ACTIONABLE" and result.action == "BUY"
    assert e.token_price_usd == 51 and e.token_to_share_ratio == Decimal("0.5")
    assert e.independent_share_price_usd == 100 and e.effective_price_per_share_usd == 102
    assert e.reference_deviation == Decimal("0.02")
    assert e.hypothetical_adjustment_per_share_usd == 4
    with localcontext() as context:
        context.prec = 256
        assert e.gross_hypothetical_edge_usd == rounded(Decimal(50) * 4 / 102)
        assert e.net_hypothetical_edge_usd == rounded(Decimal(50) * 4 / 102 - Decimal("0.35"))
    assert e.reference_deviation != e.hypothetical_return_fraction
    assert e.metric_basis == "HYPOTHETICAL_SCENARIO_ASSUMPTION"
    assert e.calibrated_prediction is False
    assert result.execution_ready is result.transaction_broadcast is False


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"target_share_price_usd": "100"}, "NO_POSITIVE_HYPOTHETICAL_ADJUSTMENT"),
        ({"fees_usd": "2"}, "NET_EDGE_BELOW_MINIMUM"),
        ({"gas_usd": "2"}, "NET_EDGE_BELOW_MINIMUM"),
        ({"execution_buffer_usd": "2"}, "NET_EDGE_BELOW_MINIMUM"),
        ({"slippage_bps": "500"}, "NET_EDGE_BELOW_MINIMUM"),
        ({"minimum_net_edge_usd": "2"}, "NET_EDGE_BELOW_MINIMUM"),
    ],
)
def test_information_label_does_not_override_economic_failures(inputs, changes, reason):
    result = opportunity(inputs, economic_changes=changes)
    assert result.source_trust_classification == "LIKELY_INFORMATION"
    assert result.status == "REJECTED" and result.action == "NONE"
    assert reason in result.reason_codes


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("missing-price", "TOKEN_PRICE_UNAVAILABLE"),
        ("missing-equity", "INDEPENDENT_CURRENT_EQUITY_UNAVAILABLE"),
        ("missing-liquidity", "LIQUIDITY_UNAVAILABLE"),
        ("missing-baseline", "TRUST_EVIDENCE_INSUFFICIENT"),
        ("missing-analogues", "TRUST_EVIDENCE_INSUFFICIENT"),
        ("skew", "TOKEN_EQUITY_TIMESTAMP_SKEW"),
        ("future", "STALE_MISSING_OR_FUTURE_OBSERVATION"),
        ("overnight", "REGIME_UNSUPPORTED_OPENING_MODEL_UNAVAILABLE"),
        ("reopening", "REGIME_UNSUPPORTED_OPENING_MODEL_UNAVAILABLE"),
    ],
)
def test_required_evidence_fails_closed(inputs, mutation, reason):
    assessment, token, fixture = inputs
    raw = assessment.model_dump()
    row = raw["representations"][0]
    if mutation == "missing-price":
        row["token_price_usd"] = None
    elif mutation == "missing-equity":
        row["reference"]["status"] = "UNAVAILABLE"
        row["reference"]["observation"] = None
    elif mutation == "missing-liquidity":
        row["liquidity"]["status"] = "UNAVAILABLE"
        row["liquidity"]["liquidity_usd"] = None
    elif mutation == "missing-baseline":
        row["baseline"]["sample_count"] = 29
    elif mutation == "missing-analogues":
        row["analogues"]["retrieved_sample_count"] = 2
    elif mutation == "skew":
        row["token_timestamp"] -= timedelta(seconds=31)
    elif mutation == "future":
        row["token_timestamp"] += timedelta(seconds=1)
    else:
        raw["regime"]["state"] = "WEEKDAY_OVERNIGHT" if mutation == "overnight" else "REOPENING"
    assessment = TrustAssessment.model_validate(raw)
    result = OpportunityEngine().evaluate(
        assessment,
        assessment.representations[0],
        token,
        fixture.economics,
        now=assessment.evaluated_at,
    )
    assert result.status == "REJECTED" and reason in result.reason_codes


def test_staleness_boundary_and_restricted_token(inputs):
    assert opportunity(inputs, offset=120).status == "ACTIONABLE"
    assert opportunity(inputs, offset=121).status == "REJECTED"
    assessment, token, fixture = inputs
    restricted = altered(token, open_state=False, market_state="pause")
    decision = OpportunityEngine().evaluate(
        assessment,
        assessment.representations[0],
        restricted,
        fixture.economics,
        now=assessment.evaluated_at,
    )
    assert "TOKEN_RESTRICTED_OR_MARKET_STATE_UNVERIFIED" in decision.reason_codes
    assert decision.status == "REJECTED"


def test_identity_and_ratio_conflicts_and_production_inputs_are_rejected(inputs):
    assessment, token, fixture = inputs
    for bad_token in (
        altered(token, token_to_share_ratio="1"),
        altered(token, contract="demo:OTHER"),
        altered(token, data_mode="LIVE", data_quality="LIVE"),
    ):
        with pytest.raises(ValueError):
            OpportunityEngine().evaluate(
                assessment,
                assessment.representations[0],
                bad_token,
                fixture.economics,
                now=assessment.evaluated_at,
            )


def test_scenario_titles_and_selection_do_not_determine_decision():
    sandbox = DemoTrustSandbox()
    raw = sandbox.datasets["supported-move"].model_dump()
    raw.update(scenario_id="steady", title="NORMAL")
    sandbox.datasets["steady"] = DemoTrustDataset.model_validate(raw)
    flow = DemoOpportunityFlow(sandbox, clock=lambda: 0)
    trust = flow.remember(sandbox.assess("steady", **IDS))
    result = flow.opportunity(trust.assessment.assessment_id)
    assert result.scenario_id == "steady" and result.opportunity.status == "ACTIONABLE"


def test_financial_risk_math_and_determinism(inputs):
    decision = opportunity(inputs)
    fixture = inputs[2]
    engine = RiskEngine()
    first = engine.evaluate(
        decision, fixture.risk_inputs, fixture.risk_policy, now=decision.evaluated_at
    )
    second = engine.evaluate(
        decision, fixture.risk_inputs, fixture.risk_policy, now=decision.evaluated_at
    )
    assert first.model_dump(exclude={"risk_id"}) == second.model_dump(exclude={"risk_id"})
    assert first.status == "PASS" and all(c.passed for c in first.checks)
    assert first.maximum_allowed_notional_usd == first.proposed_notional_usd == 50
    assert first.proposed_token_quantity == Decimal("0.980392156862745098")
    assert first.proposed_share_exposure == Decimal("0.490196078431372549")
    assert first.stress_loss_usd == Decimal("1.35")
    assert first.slippage_tolerance_bps == 50 and first.liquidity_notional_cap_usd == 50
    assert first.execution_ready is first.transaction_broadcast is False
    assert (
        first.quote_status == first.preparation_status == first.simulation_status == "UNAVAILABLE"
    )


@pytest.mark.parametrize(
    "kind,changes,reason",
    [
        ("input", {"risk_budget_usd": "0.5"}, "STRESS_RISK_BUDGET"),
        ("input", {"risk_budget_usd": "6"}, "RISK_BUDGET_LIMIT"),
        ("input", {"adverse_move_fraction": "0.1"}, "STRESS_RISK_BUDGET"),
        ("input", {"budget_usd": "50"}, "BUDGET_CAP"),
        ("input", {"wallet_available_usd": "50"}, "WALLET_LIMIT"),
        ("input", {"existing_exposure_usd": "60"}, "PORTFOLIO_CAP"),
        ("input", {"daily_loss_usd": "19"}, "STRESS_DAILY_LOSS"),
        ("input", {"daily_loss_usd": "20"}, "DAILY_LOSS_LIMIT"),
        ("input", {"trades_today": 5}, "TRADE_COUNT_LIMIT"),
        ("policy", {"min_confidence": "MEDIUM"}, "CONFIDENCE_MINIMUM"),
        ("policy", {"min_liquidity_usd": "6000"}, "LIQUIDITY_MINIMUM"),
        ("policy", {"max_slippage_bps": "19"}, "SLIPPAGE_LIMIT"),
        ("policy", {"min_net_edge_usd": "2"}, "NET_EDGE_MINIMUM"),
        ("policy", {"max_position_usd": "49"}, "POSITION_CAP"),
        ("policy", {"max_liquidity_fraction": "0.009"}, "LIQUIDITY_POSITION_CAP"),
        ("decision", {"liquidity_p50_usd": None}, "LIQUIDITY_PERCENTILE"),
        ("decision", {"liquidity_p50_usd": "6000"}, "LIQUIDITY_PERCENTILE"),
        ("decision", {"liquidity_usd": None}, "LIQUIDITY_MINIMUM"),
        ("decision", {"decimals": None}, "TOKEN_SIZE_METADATA"),
        ("decision", {"decimals": 0}, "NONZERO_SIZE"),
    ],
)
def test_risk_constraints_expose_explicit_rejections_and_never_approve_size(
    inputs, kind, changes, reason
):
    decision = opportunity(inputs)
    fixture = inputs[2]
    mandate, policy = fixture.risk_inputs, fixture.risk_policy
    if kind == "input":
        mandate = altered(mandate, **changes)
    elif kind == "policy":
        policy = altered(policy, **changes)
    else:
        decision = altered(decision, **changes)
    result = RiskEngine().evaluate(decision, mandate, policy, now=decision.evaluated_at)
    assert result.status == "FAIL" and not result.approved_for_demo_analysis
    assert reason in result.reason_codes
    assert any(c.code == reason and not c.passed for c in result.checks)
    assert result.proposed_notional_usd is result.proposed_token_quantity is None


def test_expiry_freshness_alignment_and_cooldown_are_not_bypassed(inputs):
    decision = opportunity(inputs)
    fixture = inputs[2]
    engine = RiskEngine()
    for offset in (60, 121, -1):
        result = engine.evaluate(
            decision,
            fixture.risk_inputs,
            fixture.risk_policy,
            now=decision.evaluated_at + timedelta(seconds=offset),
        )
        assert result.status == "FAIL" and "DECISION_VALID" in result.reason_codes
    skewed = altered(
        decision, token_observed_at=decision.equity_observed_at - timedelta(seconds=31)
    )
    assert (
        "TIMESTAMP_ALIGNMENT"
        in engine.evaluate(
            skewed, fixture.risk_inputs, fixture.risk_policy, now=decision.evaluated_at
        ).reason_codes
    )
    for offset in (-1, 0, 59):
        mandate = altered(
            fixture.risk_inputs, last_trade_at=decision.evaluated_at - timedelta(seconds=offset)
        )
        assert (
            "COOLDOWN"
            in engine.evaluate(
                decision, mandate, fixture.risk_policy, now=decision.evaluated_at
            ).reason_codes
        )
    mandate = altered(
        fixture.risk_inputs, last_trade_at=decision.evaluated_at - timedelta(seconds=60)
    )
    assert (
        engine.evaluate(decision, mandate, fixture.risk_policy, now=decision.evaluated_at).status
        == "PASS"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("target_share_price_usd", 106.0),
        ("fees_usd", "NaN"),
        ("gas_usd", "-1"),
        ("requested_notional_usd", "0"),
        ("target_share_price_usd", "1e1000"),
        ("slippage_bps", "10001"),
        ("observed_at", "2026-10-06T16:00:00"),
        ("synthetic", False),
        ("production_eligible", True),
    ],
)
def test_malformed_economic_data_and_contamination_are_rejected(inputs, field, value):
    with pytest.raises(ValidationError):
        OpportunityInputs.model_validate({**inputs[2].economics.model_dump(), field: value})


def test_missing_inputs_and_invalid_risk_policy_fail_closed(inputs):
    fixture = inputs[2]
    raw = fixture.model_dump()
    raw["economics"].pop("gas_usd")
    with pytest.raises(ValidationError):
        DemoOpportunityFixture.model_validate(raw)
    for field, value in (("adverse_move_fraction", "0"), ("trades_today", 1.0)):
        with pytest.raises(ValidationError):
            RiskInputs.model_validate({**fixture.risk_inputs.model_dump(), field: value})
    for field, value in (("max_data_staleness_seconds", 121), ("max_timestamp_skew_seconds", 31)):
        with pytest.raises(ValidationError):
            RiskPolicy.model_validate({**fixture.risk_policy.model_dump(), field: value})


def test_detached_trust_representation_cannot_be_used(inputs):
    assessment, token, fixture = inputs
    row = altered(assessment.representations[0], confidence="HIGH")
    assert isinstance(row, RepresentationTrust)
    with pytest.raises(ValueError):
        OpportunityEngine().evaluate(
            assessment, row, token, fixture.economics, now=assessment.evaluated_at
        )
