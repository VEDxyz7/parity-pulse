"""Interpret existing Trust outputs; never calculate prices, features or classification."""

from app.agents.schemas import MarketOutput, MarketView


class MarketAgent:
    name = "MARKET"

    async def run(self, context, tools, previous):
        trust = tools.read("market_evidence")
        views, reasons, conflicts = [], [], []
        for c in context.candidates:
            rep = next(
                r
                for r in trust.representations
                if (r.ticker, r.issuer, r.chain_id, r.contract)
                == (c.ticker, c.issuer, c.chain_id, c.contract)
            )
            f = rep.features
            stale = f is not None and not 0 <= (context.at - f.asof).total_seconds() <= 120
            times = (rep.token_timestamp, rep.liquidity.observed_at)
            stale |= any(
                t is not None and not 0 <= (context.at - t).total_seconds() <= 120 for t in times
            )
            equity = rep.reference.observation
            if trust.regime and trust.regime.state == "REGULAR":
                stale |= (
                    equity is None
                    or equity.source_timestamp is None
                    or not 0 <= (context.at - equity.source_timestamp).total_seconds() <= 120
                    or equity.data_quality not in {"LIVE", "DEMO"}
                )
                stale |= (
                    rep.token_timestamp is None
                    or equity is None
                    or equity.source_timestamp is None
                    or abs((rep.token_timestamp - equity.source_timestamp).total_seconds()) > 30
                )
            contradictory = c.trust != rep.classification or (
                f is not None
                and any(
                    v is not None and v != actual
                    for v, actual in (
                        (c.deviation, f.deviation),
                        (c.effective_cost, f.effective_price_per_share_usd),
                        (c.liquidity_usd, f.liquidity_usd),
                        (c.volume_percentile, rep.baseline.volume_percentile),
                    )
                )
            )
            unavailable = (
                f is None
                or rep.reference.status != "AVAILABLE"
                or rep.liquidity.status != "AVAILABLE"
                or rep.baseline.status != "SUFFICIENT"
                or rep.baseline.sample_count < 30
                or rep.analogues.status != "SUFFICIENT"
                or rep.analogues.retrieved_sample_count < 3
                or rep.classification == "INSUFFICIENT_EVIDENCE"
                or trust.regime is None
            )
            if contradictory:
                conflicts.append("CONTRADICTORY_MARKET_EVIDENCE")
            flags = (
                ("STALE_MARKET_EVIDENCE",)
                if stale
                else ("MISSING_MARKET_EVIDENCE",)
                if unavailable
                else ()
            )
            reasons.extend(flags)
            views.append(
                MarketView(
                    candidate_id=c.candidate_id,
                    classification="INSUFFICIENT_EVIDENCE"
                    if flags or contradictory
                    else rep.classification,
                    direction="UNKNOWN"
                    if flags or contradictory
                    else "UP"
                    if f.deviation > 0
                    else "DOWN"
                    if f.deviation < 0
                    else "FLAT",
                    risk_flags=flags,
                )
            )
        return (
            "CONFLICT" if conflicts else "INSUFFICIENT_EVIDENCE" if reasons or not views else "OK",
            MarketOutput(views=tuple(views)),
            tuple(sorted(set(conflicts))),
            tuple(sorted(set(reasons))) or (() if views else ("NO_MARKET_CANDIDATES",)),
        )
