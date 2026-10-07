"""Constrained interpretation. BUY means a non-executable DEMO recommendation only."""

from app.agents.schemas import DecisionOutput


def risk_preview(context, tools, candidate_id, mandate):
    downstream = tools.read("constraints")
    selected = next((d for d in downstream if d.candidate_id == candidate_id), None)
    if selected is None or context.mode != "DEMO":
        return "UNAVAILABLE"
    risk, route, opportunity = selected.risk, selected.route, selected.opportunity
    candidate = next((c for c in context.candidates if c.candidate_id == candidate_id), None)
    economics = opportunity.economics
    if (
        candidate is None
        or economics is None
        or candidate.net_edge_usd != economics.net_hypothetical_edge_usd
        or candidate.effective_cost != economics.effective_price_per_share_usd
        or candidate.slippage_bps != opportunity.inputs.slippage_bps
        or candidate.liquidity_usd != opportunity.liquidity_usd
        or candidate.trust != opportunity.source_trust_classification
        or risk.status != "PASS"
        or not risk.approved_for_demo_analysis
        or opportunity.status != "ACTIONABLE"
        or route.status != "ROUTE_SELECTED"
        or route.selected_representation is None
        or route.selected_representation.issuer != opportunity.issuer
        or route.selected_representation.contract != opportunity.contract
        or risk.opportunity_id != opportunity.opportunity_id
        or risk.proposed_notional_usd != opportunity.inputs.requested_notional_usd
        or mandate is None
        or mandate.budget_usd is None
        or mandate.risk_budget_usd is None
        # This preview must be bound to the user's actual mandate, not fixture risk tolerance.
        or risk.inputs.budget_usd != mandate.budget_usd
        or risk.inputs.risk_budget_usd != mandate.risk_budget_usd
        or not opportunity.evaluated_at <= context.at < opportunity.valid_until
        or not route.timestamp <= context.at < route.valid_until
    ):
        return "FAIL"
    return "PASS"


class DecisionAgent:
    name = "DECISION"

    async def run(self, context, tools, previous):
        intent, market, news, research, opportunity = previous
        mandate = intent.output.mandate
        conflicts = tuple(sorted({code for r in previous for code in r.conflicts}))
        choice = opportunity.output
        candidate = next(
            (c for c in context.candidates if c.candidate_id == choice.candidate_id), None
        )
        preview = risk_preview(context, tools, choice.candidate_id, mandate)
        reasons = []
        action = choice.action
        if choice.action == "NO_QUALIFYING_OPPORTUNITY" and intent.status == "OK":
            reasons.append("NO_QUALIFYING_DETERMINISTIC_CANDIDATE")
            if context.candidates and all(c.trust == "NORMAL" for c in context.candidates):
                reasons.append("NORMAL_MARKET_STAND_DOWN")
            elif context.candidates and all(c.trust == "LIKELY_NOISE" for c in context.candidates):
                reasons.append("NOISE_SUPPRESSED_BY_DETERMINISTIC_TRUST")
        elif (
            intent.status != "OK"
            or mandate is None
            or mandate.mode == "AUTOPILOT"
            or mandate.risk_budget_usd is None
        ):
            action = "DEFER"
            reasons.append("MANDATE_INCOMPLETE_OR_UNSUPPORTED")
        elif conflicts or any(r.status != "OK" for r in (market, news, research, opportunity)):
            action = "DEFER"
            reasons.append("CONFLICTING_OR_INSUFFICIENT_REQUIRED_EVIDENCE")
        elif candidate is None or (
            mandate.ticker is not None and mandate.ticker != candidate.ticker
        ):
            action = "DEFER"
            reasons.append("NO_MANDATE_BOUND_CANDIDATE")
        elif context.mode != "DEMO":
            action = "DEFER"
            reasons.append("PRODUCTION_OPPORTUNITY_GATE_BLOCKED_BY_TRUST")
        elif preview != "PASS":
            action = "DEFER"
            reasons.append("DETERMINISTIC_RISK_OR_ROUTE_NOT_APPROVED")
        else:
            reasons.append("DEMO_ANALYTICAL_BUY_ONLY_NO_EXECUTION_AUTHORITY")
        return (
            "CONFLICT" if conflicts else "OK" if action != "DEFER" else "ABSTAIN",
            DecisionOutput(
                decision=action,
                candidate_id=candidate.candidate_id if candidate else None,
                ticker=candidate.ticker if candidate else None,
                issuer=candidate.issuer if candidate else None,
                reasons=tuple(reasons),
                risk_preview_status=preview,
            ),
            conflicts,
            ("ALL_LIVE_GATES_REMAIN_BLOCKED", "NO_REAL_FUNDS_MOVE"),
        )
