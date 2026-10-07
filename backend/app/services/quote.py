"""Deterministic synthetic quotes; no provider request or executable quote is issued."""

from datetime import timedelta
from decimal import ROUND_FLOOR, Decimal, localcontext
from uuid import UUID

from app.models.demo_execution import DemoQuote, artifact_digest, artifact_id
from app.models.opportunity import OpportunityDecision, OpportunityEconomics, OpportunityInputs
from app.services.demo_sandbox import MARKER
from app.services.opportunity import rounded


class QuoteService:
    ttl_seconds = 30

    def create(
        self, opportunity, risk, *, source_risk_id, context_sha256, market_observation_kind, now
    ):
        if risk.status != "PASS" or risk.opportunity_id != opportunity.opportunity_id:
            raise ValueError("A matching revalidated analytical Risk PASS is required")
        if (
            opportunity.status != "ACTIONABLE"
            or not opportunity.evaluated_at <= now < opportunity.valid_until
        ):
            raise ValueError("A valid actionable DEMO opportunity is required")
        e = opportunity.economics
        inputs = opportunity.inputs
        with localcontext() as context:
            context.prec = 256
            execution_price = e.token_price_usd * (1 + inputs.slippage_bps / Decimal(10000))
            quantum = Decimal(1).scaleb(-min(opportunity.decimals, 18))
            quantity = (risk.proposed_notional_usd / execution_price).quantize(
                quantum, rounding=ROUND_FLOOR
            )
            base = quantity * e.token_price_usd
            amount = quantity * execution_price
            slippage = amount - base
            fixed = inputs.fees_usd + inputs.gas_usd + inputs.execution_buffer_usd
            net = quantity * inputs.target_share_price_usd * e.token_to_share_ratio - amount - fixed
            fields = dict(
                **MARKER,
                context_sha256=context_sha256,
                opportunity_id=opportunity.opportunity_id,
                source_risk_id=source_risk_id,
                ticker=opportunity.ticker,
                issuer=opportunity.issuer,
                chain_id=opportunity.chain_id,
                contract=opportunity.contract,
                symbol=opportunity.symbol,
                decimals=opportunity.decimals,
                quoted_at=now,
                valid_until=min(now + timedelta(seconds=self.ttl_seconds), opportunity.valid_until),
                market_observed_at=opportunity.token_observed_at,
                market_observation_kind=market_observation_kind,
                mark_price_usd=e.token_price_usd,
                execution_price_usd=execution_price,
                token_to_share_ratio=e.token_to_share_ratio,
                requested_notional_usd=risk.proposed_notional_usd,
                base_notional_usd=base,
                input_amount_usd=amount,
                output_token_quantity=quantity,
                share_exposure=quantity * e.token_to_share_ratio,
                fees_usd=inputs.fees_usd,
                gas_usd=inputs.gas_usd,
                execution_buffer_usd=inputs.execution_buffer_usd,
                slippage_bps=inputs.slippage_bps,
                estimated_slippage_usd=slippage,
                total_cash_required_usd=amount + fixed,
                net_hypothetical_edge_usd=rounded(net),
                economics_inputs=inputs,
            )
            # Validate/default all fields before fingerprinting, so JSON is canonical.
            quote = DemoQuote(**fields, quote_id=UUID(int=0), fingerprint="0" * 64)
            fingerprint = artifact_digest(quote, "quote_id")
            return DemoQuote.model_validate(
                {
                    **quote.model_dump(),
                    "fingerprint": fingerprint,
                    "quote_id": artifact_id("quote", fingerprint),
                }
            )

    def quoted_opportunity(self, source, quote, *, current_inputs=None):
        """Risk works on mark notional; slippage is then added once by the existing engine."""
        with localcontext() as context:
            context.prec = 256
            inputs = OpportunityInputs.model_validate(
                {
                    **(current_inputs or quote.economics_inputs).model_dump(),
                    "requested_notional_usd": quote.base_notional_usd,
                }
            )
            gross = quote.output_token_quantity * (
                inputs.target_share_price_usd * quote.token_to_share_ratio - quote.mark_price_usd
            )
            slippage = quote.base_notional_usd * inputs.slippage_bps / Decimal(10000)
            net = rounded(
                gross - slippage - inputs.fees_usd - inputs.gas_usd - inputs.execution_buffer_usd
            )
            effective = quote.mark_price_usd / quote.token_to_share_ratio
            adjustment = inputs.target_share_price_usd - effective
            economics = OpportunityEconomics.model_validate(
                {
                    **source.economics.model_dump(),
                    "requested_notional_usd": quote.base_notional_usd,
                    "gross_hypothetical_edge_usd": rounded(gross),
                    "hypothetical_target_share_price_usd": inputs.target_share_price_usd,
                    "hypothetical_adjustment_per_share_usd": rounded(adjustment),
                    "hypothetical_return_fraction": rounded(adjustment / effective),
                    "estimated_slippage_usd": slippage,
                    "fees_usd": inputs.fees_usd,
                    "gas_usd": inputs.gas_usd,
                    "execution_buffer_usd": inputs.execution_buffer_usd,
                    "net_hypothetical_edge_usd": net,
                }
            )
            status = (
                "ACTIONABLE"
                if adjustment > 0 and net >= inputs.minimum_net_edge_usd
                else "REJECTED"
            )
            return OpportunityDecision.model_validate(
                {
                    **source.model_dump(),
                    "inputs": inputs,
                    "economics": economics,
                    "status": status,
                    "action": "BUY" if status == "ACTIONABLE" else "NONE",
                    "reason_codes": ["QUOTED_COST_ADJUSTED_SYNTHETIC_ECONOMICS"]
                    if status == "ACTIONABLE"
                    else ["QUOTED_NET_EDGE_BELOW_MINIMUM"],
                }
            )
