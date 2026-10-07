"""One deterministic Opportunity engine; synthetic inputs confer no execution authority."""

from datetime import timedelta
from decimal import ROUND_FLOOR, Decimal, localcontext
from uuid import uuid4

from app.models.opportunity import OpportunityDecision, OpportunityEconomics
from app.services.demo_sandbox import MARKER
from app.services.normalization import bounded_decimal, comparable_economics, financial


def rounded(value):
    return value.quantize(Decimal("1e-18"), rounding=ROUND_FLOOR)


def analytical_edge(*, effective, target, notional, slippage_bps, fees, gas, buffer):
    """Shared exact arithmetic only; callers retain their own eligibility and safety checks."""
    for value in (notional, slippage_bps, fees, gas, buffer):
        bounded_decimal(value)
    # Effective/target prices can be internally derived 256-digit Decimal quotients.
    # Their source lexemes were validated by the caller; do not truncate exact arithmetic.
    for value in (effective, target):
        value = financial(value)
        if abs(value.adjusted()) > 36 or len(value.as_tuple().digits) > 256:
            raise ValueError("Unsupported analytical magnitude")
    if (
        effective <= 0
        or target <= 0
        or notional <= 0
        or any(v < 0 for v in (slippage_bps, fees, gas, buffer))
        or slippage_bps > 10000
    ):
        raise ValueError("Invalid analytical economics")
    with localcontext() as context:
        context.prec = 256
        adjustment = target - effective
        change = adjustment / effective
        gross = notional * change
        slippage = notional * slippage_bps / Decimal(10000)
        net = gross - slippage - fees - gas - buffer
        return adjustment, change, gross, slippage, net


class OpportunityEngine:
    def evaluate(self, assessment, representation, token, inputs, *, now):
        if assessment.data_mode != "DEMO" or token.data_mode != "DEMO":
            raise ValueError("Only isolated synthetic analysis is supported")
        if representation not in assessment.representations:
            raise ValueError("Representation does not belong to supplied Trust evidence")
        identity = (
            representation.ticker,
            representation.issuer,
            representation.chain_id,
            representation.contract,
        )
        if identity != (inputs.ticker, inputs.issuer, inputs.chain_id, inputs.contract) or (
            identity != (token.ticker, token.platform_id, token.chain_id, token.contract)
            or token.token_to_share_ratio != representation.token_to_share_ratio
        ):
            raise ValueError("Opportunity input identity/ratio conflict")
        reasons = []
        economics = None
        classification = representation.classification
        reference = representation.reference.observation
        equity_price = reference.price if reference is not None else None
        price = representation.token_price_usd
        if classification == "NORMAL":
            reasons.append("NORMAL_TRUST_NO_INFORMATION_SIGNAL")
        elif classification != "LIKELY_INFORMATION":
            reasons.append("TRUST_NOT_LIKELY_INFORMATION")
        if (
            assessment.status != "ASSESSED"
            or representation.evidence_quality != "SYNTHETIC_DEMO"
            or representation.missing_evidence
            or representation.features is None
            or representation.baseline.status != "SUFFICIENT"
            or representation.baseline.sample_count < 30
            or representation.analogues.status != "SUFFICIENT"
            or representation.analogues.retrieved_sample_count < 3
        ):
            reasons.append("TRUST_EVIDENCE_INSUFFICIENT")
        if assessment.regime is None or assessment.regime.state != "REGULAR":
            reasons.append("REGIME_UNSUPPORTED_OPENING_MODEL_UNAVAILABLE")
        if token.open_state is not True or token.market_state != "regular":
            reasons.append("TOKEN_RESTRICTED_OR_MARKET_STATE_UNVERIFIED")
        if token.decimals is None:
            reasons.append("TOKEN_DECIMALS_UNAVAILABLE")
        if (
            representation.reference.status != "AVAILABLE"
            or reference is None
            or reference.data_mode != "DEMO"
            or reference.data_quality != "DEMO"
            or not reference.source.startswith("DEMO_EQUITY")
            or reference.kind not in {"QUOTE", "SNAPSHOT"}
            or equity_price is None
        ):
            reasons.append("INDEPENDENT_CURRENT_EQUITY_UNAVAILABLE")
        times = [
            representation.token_timestamp,
            representation.reference.reference_asof,
            representation.liquidity.observed_at,
            inputs.observed_at,
            assessment.evaluated_at,
        ]
        if any(t is None or not 0 <= (now - t).total_seconds() <= 120 for t in times):
            reasons.append("STALE_MISSING_OR_FUTURE_OBSERVATION")
        if times[0] is None or times[1] is None or abs((times[0] - times[1]).total_seconds()) > 30:
            reasons.append("TOKEN_EQUITY_TIMESTAMP_SKEW")
        if representation.liquidity.status != "AVAILABLE":
            reasons.append("LIQUIDITY_UNAVAILABLE")
        if price is None:
            reasons.append("TOKEN_PRICE_UNAVAILABLE")
        if price is not None and equity_price is not None:
            for value in (price, equity_price, representation.token_to_share_ratio):
                bounded_decimal(value)
            with localcontext() as context:
                context.prec = 256
                comparison = comparable_economics(
                    price, representation.token_to_share_ratio, equity_price
                )
                effective = comparison["effective_price_per_share_usd"]
                adjustment, change, gross, slippage, net = analytical_edge(
                    effective=effective,
                    target=inputs.target_share_price_usd,
                    notional=inputs.requested_notional_usd,
                    slippage_bps=inputs.slippage_bps,
                    fees=inputs.fees_usd,
                    gas=inputs.gas_usd,
                    buffer=inputs.execution_buffer_usd,
                )
                economics = OpportunityEconomics(
                    **MARKER,
                    token_price_usd=price,
                    token_to_share_ratio=representation.token_to_share_ratio,
                    independent_share_price_usd=equity_price,
                    effective_price_per_share_usd=rounded(effective),
                    reference_deviation=rounded(comparison["deviation"]),
                    hypothetical_target_share_price_usd=inputs.target_share_price_usd,
                    hypothetical_adjustment_per_share_usd=rounded(adjustment),
                    hypothetical_return_fraction=rounded(change),
                    requested_notional_usd=inputs.requested_notional_usd,
                    gross_hypothetical_edge_usd=rounded(gross),
                    estimated_slippage_usd=slippage,
                    fees_usd=inputs.fees_usd,
                    gas_usd=inputs.gas_usd,
                    execution_buffer_usd=inputs.execution_buffer_usd,
                    net_hypothetical_edge_usd=rounded(net),
                )
                if adjustment <= 0:
                    reasons.append("NO_POSITIVE_HYPOTHETICAL_ADJUSTMENT")
                if economics.net_hypothetical_edge_usd < inputs.minimum_net_edge_usd:
                    reasons.append("NET_EDGE_BELOW_MINIMUM")
        status = (
            "NO_OPPORTUNITY"
            if classification == "NORMAL"
            else "REJECTED_BY_TRUST"
            if classification != "LIKELY_INFORMATION"
            else "REJECTED"
            if reasons
            else "ACTIONABLE"
        )
        distribution = representation.baseline.liquidity
        return OpportunityDecision(
            **MARKER,
            opportunity_id=uuid4(),
            trust_assessment_id=assessment.assessment_id,
            evaluated_at=now,
            valid_until=min(
                now + timedelta(seconds=inputs.validity_seconds),
                assessment.evaluated_at + timedelta(seconds=120),
            ),
            ticker=representation.ticker,
            issuer=representation.issuer,
            chain_id=representation.chain_id,
            contract=representation.contract,
            symbol=representation.symbol,
            source_trust_classification=classification,
            confidence=representation.confidence,
            evidence_quality=representation.evidence_quality,
            status=status,
            action="BUY" if status == "ACTIONABLE" else "NONE",
            reason_codes=reasons or ["POSITIVE_COST_ADJUSTED_SYNTHETIC_ECONOMICS"],
            inputs=inputs,
            economics=economics,
            token_observed_at=representation.token_timestamp,
            equity_observed_at=representation.reference.reference_asof,
            liquidity_observed_at=representation.liquidity.observed_at,
            liquidity_usd=representation.liquidity.liquidity_usd,
            liquidity_p50_usd=distribution.quantiles.get("50") if distribution else None,
            decimals=token.decimals,
        )
