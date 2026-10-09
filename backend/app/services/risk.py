"""Deterministic financial limits; a PASS is solely synthetic analytical approval."""

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, localcontext
from uuid import uuid4

from app.models.risk import OpportunityRiskContext, RiskCheck, RiskDecision
from app.services.demo_sandbox import MARKER
from app.services.normalization import bounded_decimal
from app.services.opportunity import rounded

CONFIDENCE = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


class RiskEngine:
    def evaluate_execution(self, evidence, *, now):
        """Independent hard controls for exact preparation, never live authorization.

        Shared caps from Phases 3A/7; no LLM input or inferred risk tolerance.
        """
        from app.models.execution import (
            ExecutionRiskDecision,
            ExecutionRiskEvidence,
            fingerprint,
        )

        e = ExecutionRiskEvidence.model_validate_json(evidence.model_dump_json())
        c = e.context
        checks = []

        def check(code, passed):
            checks.append(RiskCheck(code=code, passed=bool(passed), detail=code))

        check("RISK_CONTEXT_AVAILABLE", c is not None)
        check("REQUIRED_EVIDENCE_VALID", e.required_evidence_valid)
        check("SYSTEM_RESOLVED", e.system_resolved and c is not None and c.system_resolved)
        check("TRADABLE_ROUTE", e.tradable and e.route_available)
        times = (e.token_observed_at, e.equity_observed_at, e.evidence_observed_at)
        check("DATA_FRESHNESS", all(0 <= (now - t).total_seconds() <= 120 for t in times))
        check("TIMESTAMP_ALIGNMENT", abs((times[0] - times[1]).total_seconds()) <= 30)
        # Without Trust (configured rebalance only) the Trust-history checks do not apply;
        # every financial, liquidity, freshness and wallet limit below still does.
        trust = e.trust_required
        check("TRUST_REQUIRED", not trust or e.trust_state in ("NORMAL", "LIKELY_INFORMATION"))
        check(
            "OPPORTUNITY_TRUST", e.purpose != "OPPORTUNITY" or e.trust_state == "LIKELY_INFORMATION"
        )
        check("PRODUCTION_TRUST_GATE", not trust or e.data_mode == "DEMO")
        check("PRODUCTION_OPPORTUNITY_GATE", e.purpose != "OPPORTUNITY" or e.data_mode == "DEMO")
        stress, maximum = None, None
        if c is not None:
            check("RISK_CONTEXT_FRESH", 0 <= (now - c.observed_at).total_seconds() <= 120)
            check("WALLET_ALLOWED", c.wallet_allowed)
            check("RISK_BUDGET_LIMIT", e.risk_budget_usd <= c.max_risk_budget_usd)
            check("DAILY_LOSS_LIMIT", c.daily_loss_usd < c.max_daily_loss_usd)
            check("TRADE_COUNT_LIMIT", c.trades_today < c.max_trades_per_day)
            check(
                "COOLDOWN",
                c.last_trade_at is None
                or (now - c.last_trade_at).total_seconds() >= c.cooldown_seconds,
            )
            check("CONFIDENCE_MINIMUM", CONFIDENCE[e.confidence] >= CONFIDENCE[c.min_confidence])
            check("SLIPPAGE_LIMIT", e.slippage_bps <= c.max_slippage_bps)
            check(
                "LIQUIDITY_MINIMUM",
                e.liquidity_usd is not None and e.liquidity_usd >= c.min_liquidity_usd,
            )
            check(
                "LIQUIDITY_PERCENTILE",
                not trust
                or e.liquidity_usd is not None
                and e.liquidity_p50_usd is not None
                and e.liquidity_usd >= e.liquidity_p50_usd,
            )
            check(
                "NET_EDGE_MINIMUM",
                e.purpose != "OPPORTUNITY" or e.net_expected_edge_usd >= c.min_net_edge_usd,
            )
            with localcontext() as ctx:
                ctx.prec = 256
                fixed = e.costs_usd + e.conversion_cost_usd
                slip = e.slippage_bps / Decimal(10000)
                caps = position_caps(
                    budget=e.budget_usd,
                    risk_budget=e.risk_budget_usd,
                    wallet=c.wallet_available_usd,
                    existing=c.existing_exposure_usd,
                    daily_loss=c.daily_loss_usd,
                    liquidity=e.liquidity_usd or Decimal(0),
                    policy=c,
                    fixed=fixed,
                    slippage_fraction=slip,
                    loss_fraction=c.stress_adverse_move_fraction + slip,
                )
                for code, cap in caps.items():
                    check(code, e.notional_usd <= cap)
                maximum = rounded(min(caps.values()))
                stress = e.notional_usd * (c.stress_adverse_move_fraction + slip) + fixed
                check("COST_INCLUSIVE_STRESS", stress <= e.risk_budget_usd)
        return ExecutionRiskDecision(
            evidence_digest=fingerprint(e),
            evaluated_at=now,
            decision_id=e.decision_id,
            data_mode=e.data_mode,
            status="PASS" if all(c.passed for c in checks) else "FAIL",
            checks=tuple(checks),
            stress_loss_usd=stress,
            maximum_notional_usd=maximum,
        )

    def size_opportunity(self, mandate, constraints, costs, liquidity, *, now, mode):
        """Phase 7 ex-ante sizing, stricter cost-inclusive stress and system caps.

        This is an analytical preview only. Existing final Risk validation remains mandatory.
        No confidence input is accepted. Unknown wallet/system constraints never become zero.
        """
        if constraints is None or costs is None or liquidity is None:
            return None, None, ("RISK_CONSTRAINTS_UNAVAILABLE",)
        c = OpportunityRiskContext.model_validate(constraints.model_dump())
        for v in (mandate.budget_usd, mandate.risk_budget_usd, liquidity):
            bounded_decimal(v)
        reasons = []
        if c.data_mode != mode or costs.data_mode != mode:
            raise ValueError("Mixed risk sizing modes")
        if not c.system_resolved or not c.wallet_allowed:
            reasons.append("WALLET_OR_SYSTEM_RESTRICTED")
        if not 0 <= (now - c.observed_at).total_seconds() <= 120:
            reasons.append("STALE_RISK_CONSTRAINTS")
        if mandate.risk_budget_usd > c.max_risk_budget_usd:
            reasons.append("RISK_BUDGET_LIMIT")
        if c.daily_loss_usd >= c.max_daily_loss_usd:
            reasons.append("DAILY_LOSS_LIMIT")
        if c.trades_today >= c.max_trades_per_day:
            reasons.append("TRADE_COUNT_LIMIT")
        if (
            c.last_trade_at is not None
            and (now - c.last_trade_at).total_seconds() < c.cooldown_seconds
        ):
            reasons.append("COOLDOWN")
        with localcontext() as context:
            context.prec = 256
            fixed = costs.fees_usd + costs.gas_usd + costs.execution_buffer_usd
            slip = costs.slippage_bps / Decimal(10000)
            loss_fraction = c.stress_adverse_move_fraction + slip
            caps = position_caps(
                budget=mandate.budget_usd,
                risk_budget=mandate.risk_budget_usd,
                wallet=c.wallet_available_usd,
                existing=c.existing_exposure_usd,
                daily_loss=c.daily_loss_usd,
                liquidity=liquidity,
                policy=c,
                fixed=fixed,
                slippage_fraction=slip,
                loss_fraction=loss_fraction,
            )
            size = rounded(min(costs.quoted_notional_usd, *caps.values()))
            if size <= 0:
                reasons.append("NO_POSITIVE_RISK_SIZE")
            # Real quotes/costs are size-specific: require a new observed quote rather than
            # estimating a more favorable fee or liquidity at a different size.
            if mode != "DEMO" and size != costs.quoted_notional_usd:
                reasons.append("COST_NOTIONAL_MISMATCH_REQUOTE_REQUIRED")
            stress = (size * c.stress_adverse_move_fraction).quantize(
                Decimal("1e-18"), rounding=ROUND_CEILING
            )
            if stress > mandate.risk_budget_usd:
                reasons.append("STRESS_RISK_BUDGET")
        return (None, None, tuple(reasons)) if reasons else (size, stress, ())

    def evaluate(self, opportunity, inputs, policy, *, now):
        checks = []

        def check(code, passed, detail):
            checks.append(RiskCheck(code=code, passed=bool(passed), detail=detail))

        check(
            "OPPORTUNITY_ACTIONABLE",
            opportunity.status == "ACTIONABLE" and opportunity.action == "BUY",
            "Only an actionable calculated decision qualifies.",
        )
        check(
            "TRUST_REQUIRED",
            opportunity.source_trust_classification == "LIKELY_INFORMATION"
            and opportunity.evidence_quality == "SYNTHETIC_DEMO",
            "Synthetic Information evidence is required; no production eligibility is granted.",
        )
        check(
            "CONFIDENCE_MINIMUM",
            CONFIDENCE.get(opportunity.confidence, -1) >= CONFIDENCE[policy.min_confidence],
            f"Minimum {policy.min_confidence} for DEMO; confidence remains uncalibrated.",
        )
        check(
            "DECISION_VALID",
            opportunity.evaluated_at <= now < opportunity.valid_until,
            "Expired or future decisions cannot pass.",
        )
        times = [
            opportunity.token_observed_at,
            opportunity.equity_observed_at,
            opportunity.liquidity_observed_at,
            opportunity.inputs.observed_at,
        ]
        check(
            "DATA_FRESHNESS",
            all(
                t is not None
                and 0 <= (now - t).total_seconds() <= policy.max_data_staleness_seconds
                for t in times
            ),
            "Required synthetic observations must be within 120 seconds of the synthetic clock.",
        )
        check(
            "TIMESTAMP_ALIGNMENT",
            times[0] is not None
            and times[1] is not None
            and abs((times[0] - times[1]).total_seconds()) <= policy.max_timestamp_skew_seconds,
            "Token/equity observations must align within 30 seconds.",
        )
        check(
            "RISK_BUDGET_LIMIT",
            inputs.risk_budget_usd <= policy.max_risk_budget_usd,
            "The supplied risk budget cannot exceed the policy maximum.",
        )
        check(
            "DAILY_LOSS_LIMIT",
            inputs.daily_loss_usd < policy.max_daily_loss_usd,
            "No approval at or above the daily loss limit.",
        )
        check(
            "TRADE_COUNT_LIMIT",
            inputs.trades_today < policy.max_trades_per_day,
            "Trade count must remain below the configured daily limit.",
        )
        check(
            "COOLDOWN",
            inputs.last_trade_at is None
            or (now - inputs.last_trade_at).total_seconds() >= policy.cooldown_seconds,
            "No future last trade and no approval within cooldown.",
        )
        check(
            "SLIPPAGE_LIMIT",
            opportunity.inputs.slippage_bps <= policy.max_slippage_bps,
            "Supplied synthetic slippage must not exceed tolerance.",
        )
        liquidity = opportunity.liquidity_usd
        floor = opportunity.liquidity_p50_usd
        check(
            "LIQUIDITY_MINIMUM",
            liquidity is not None and liquidity >= policy.min_liquidity_usd,
            "Required synthetic USD liquidity must be available and above the absolute floor.",
        )
        check(
            "LIQUIDITY_PERCENTILE",
            liquidity is not None and floor is not None and liquidity >= floor,
            "Liquidity must meet the same-scope Trust baseline p50; unavailable floor fails.",
        )
        economics = opportunity.economics
        check(
            "NET_EDGE_MINIMUM",
            economics is not None
            and economics.net_hypothetical_edge_usd
            >= max(policy.min_net_edge_usd, opportunity.inputs.minimum_net_edge_usd),
            "Cost-adjusted hypothetical USD edge must meet both economic and risk thresholds.",
        )
        check(
            "TOKEN_SIZE_METADATA",
            opportunity.decimals is not None,
            "Token decimals must be known for conservative analytical sizing.",
        )
        with localcontext() as context:
            context.prec = 256
            costs = opportunity.inputs
            fixed = costs.fees_usd + costs.gas_usd + costs.execution_buffer_usd
            slippage_fraction = costs.slippage_bps / Decimal(10000)
            loss_fraction = inputs.adverse_move_fraction + slippage_fraction
            liquidity_cap = (liquidity or Decimal(0)) * policy.max_liquidity_fraction
            caps = position_caps(
                budget=inputs.budget_usd,
                risk_budget=inputs.risk_budget_usd,
                wallet=inputs.wallet_available_usd,
                existing=inputs.existing_exposure_usd,
                daily_loss=inputs.daily_loss_usd,
                liquidity=liquidity or Decimal(0),
                policy=policy,
                fixed=fixed,
                slippage_fraction=slippage_fraction,
                loss_fraction=loss_fraction,
            )
            requested = costs.requested_notional_usd
            for code, cap in caps.items():
                check(
                    code,
                    requested <= cap,
                    f"Requested USD {requested} must not exceed USD {rounded(cap)}.",
                )
            maximum = rounded(min(caps.values()))
            passed = all(c.passed for c in checks)
            quantity = None
            shares = None
            if passed and economics is not None:
                quantum = Decimal(1).scaleb(-min(opportunity.decimals, 18))
                quantity = (requested / economics.token_price_usd).quantize(
                    quantum, rounding=ROUND_FLOOR
                )
                shares = rounded(quantity * economics.token_to_share_ratio)
                check(
                    "NONZERO_SIZE",
                    quantity > 0,
                    "Rounded-down synthetic token quantity must be positive.",
                )
                passed = all(c.passed for c in checks)
            return RiskDecision(
                **MARKER,
                risk_id=uuid4(),
                opportunity_id=opportunity.opportunity_id,
                evaluated_at=now,
                status="PASS" if passed else "FAIL",
                approved_for_demo_analysis=passed,
                reason_codes=(
                    ["ALL_DEMO_ANALYTICAL_CHECKS_PASSED"]
                    if passed
                    else [c.code for c in checks if not c.passed]
                ),
                checks=checks,
                inputs=inputs,
                policy=policy,
                maximum_allowed_notional_usd=maximum,
                proposed_notional_usd=requested if passed else None,
                proposed_token_quantity=quantity if passed else None,
                proposed_share_exposure=shares if passed else None,
                stress_loss_usd=rounded(requested * loss_fraction + fixed) if passed else None,
                slippage_tolerance_bps=policy.max_slippage_bps,
                liquidity_notional_cap_usd=rounded(liquidity_cap),
            )


def position_caps(
    *,
    budget,
    risk_budget,
    wallet,
    existing,
    daily_loss,
    liquidity,
    policy,
    fixed,
    slippage_fraction,
    loss_fraction,
):
    """Shared exact caps used by existing DEMO Risk and full-universe sizing."""
    return {
        "POSITION_CAP": policy.max_position_usd,
        "BUDGET_CAP": max(Decimal(0), (budget - fixed) / (1 + slippage_fraction)),
        "WALLET_LIMIT": max(Decimal(0), (wallet - fixed) / (1 + slippage_fraction)),
        "PORTFOLIO_CAP": max(Decimal(0), policy.max_portfolio_exposure_usd - existing),
        "STRESS_RISK_BUDGET": max(Decimal(0), (risk_budget - fixed) / loss_fraction),
        "STRESS_DAILY_LOSS": max(
            Decimal(0), (policy.max_daily_loss_usd - daily_loss - fixed) / loss_fraction
        ),
        "LIQUIDITY_POSITION_CAP": liquidity * policy.max_liquidity_fraction,
    }
