"""Interpret a bounded backend table; no scanning, new candidates or financial arithmetic."""

from app.agents.schemas import OpportunityOutput

TIERS = {"HIGH": 2, "MEDIUM": 1, "LOW": 0, None: -1}


def rejection(c, at):
    reasons = list(c.risk_flags)
    if c.eligibility != "ELIGIBLE":
        reasons.append("DETERMINISTICALLY_INELIGIBLE")
    if not 0 <= (at - c.observed_at).total_seconds() <= 120:
        reasons.append("STALE_CANDIDATE")
    if c.trust != "LIKELY_INFORMATION" or c.baseline_samples < 30 or c.analogue_count < 3:
        reasons.append("TRUST_OR_HISTORY_INSUFFICIENT")
    if c.tradable is not True:
        reasons.append("TRADABILITY_UNAVAILABLE")
    if any(
        v is None
        for v in (
            c.deviation,
            c.volume_percentile,
            c.effective_cost,
            c.liquidity_usd,
            c.slippage_bps,
            c.net_edge_usd,
            c.confidence,
        )
    ):
        reasons.append("MISSING_CANDIDATE_ECONOMICS")
    elif c.net_edge_usd <= 0 or c.liquidity_usd <= 0:
        reasons.append("NONPOSITIVE_EDGE_OR_LIQUIDITY")
    return tuple(reasons)


def ranked(candidates, at):
    eligible = [c for c in candidates if not rejection(c, at)]
    # Lexicographic priority, no hidden weights. The table's economics are never recalculated.
    eligible.sort(
        key=lambda c: (
            -TIERS[c.confidence],
            c.net_edge_usd.copy_negate(),
            -c.analogue_count,
            -c.baseline_samples,
            c.liquidity_usd.copy_negate(),
            c.effective_cost,
            c.ticker,
            c.issuer,
            c.chain_id,
            c.contract,
            c.candidate_id,
        )
    )
    return eligible


class OpportunityAgent:
    name = "OPPORTUNITY"

    async def run(self, context, tools, previous):
        table = tools.read("candidate_table")
        eligible = ranked(table, context.at)
        rejected = tuple(sorted(c.candidate_id for c in table if rejection(c, context.at)))
        chosen = eligible[0] if eligible else None
        uncertain = (
            any(c.eligibility == "UNAVAILABLE" or c.trust == "INSUFFICIENT_EVIDENCE" for c in table)
            or not table
        )
        return (
            "OK" if chosen or not uncertain else "INSUFFICIENT_EVIDENCE",
            OpportunityOutput(
                action="BUY" if chosen else "DEFER" if uncertain else "NO_QUALIFYING_OPPORTUNITY",
                candidate_id=chosen.candidate_id if chosen else None,
                eligible_ids=tuple(c.candidate_id for c in eligible),
                rejected_ids=rejected,
                strengths=("DETERMINISTICALLY_ELIGIBLE", "RANKED_BACKEND_ECONOMICS")
                if chosen
                else (),
                weaknesses=() if chosen else ("NO_QUALIFYING_BACKEND_CANDIDATE",),
            ),
            (),
            ("INTERPRETATION_NOT_RISK_OR_EXECUTION_AUTHORITY",),
        )
