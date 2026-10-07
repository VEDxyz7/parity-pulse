"""Deterministic financial limits; a PASS is solely synthetic analytical approval."""

from decimal import ROUND_FLOOR, Decimal, localcontext
from uuid import uuid4

from app.models.risk import RiskCheck, RiskDecision
from app.services.demo_sandbox import MARKER
from app.services.opportunity import rounded

CONFIDENCE = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


class RiskEngine:
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
            caps = {
                "POSITION_CAP": policy.max_position_usd,
                "BUDGET_CAP": max(
                    Decimal(0), (inputs.budget_usd - fixed) / (1 + slippage_fraction)
                ),
                "WALLET_LIMIT": max(
                    Decimal(0), (inputs.wallet_available_usd - fixed) / (1 + slippage_fraction)
                ),
                "PORTFOLIO_CAP": max(
                    Decimal(0), policy.max_portfolio_exposure_usd - inputs.existing_exposure_usd
                ),
                "STRESS_RISK_BUDGET": max(
                    Decimal(0), (inputs.risk_budget_usd - fixed) / loss_fraction
                ),
                "STRESS_DAILY_LOSS": max(
                    Decimal(0),
                    (policy.max_daily_loss_usd - inputs.daily_loss_usd - fixed) / loss_fraction,
                ),
                "LIQUIDITY_POSITION_CAP": liquidity_cap,
            }
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
