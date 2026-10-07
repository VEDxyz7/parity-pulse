"""Build a canonical unsigned DEMO request manifest, never calldata or a signed transaction."""

from fractions import Fraction
from uuid import UUID

from app.models.demo_execution import (
    DemoBuyParameters,
    PreparedDemoRequest,
    artifact_digest,
    artifact_id,
)
from app.services.demo_sandbox import MARKER


class TransactionBuilder:
    def prepare(self, quote, risk, *, now):
        if not quote.quoted_at <= now < quote.valid_until:
            raise ValueError("Expired or future quote")
        if risk.status != "PASS" or risk.opportunity_id != quote.opportunity_id:
            raise ValueError("Matching revalidated analytical Risk PASS is required")
        if artifact_digest(quote, "quote_id") != quote.fingerprint:
            raise ValueError("Quote fingerprint mismatch")
        if (
            quote.base_notional_usd > risk.maximum_allowed_notional_usd
            or quote.output_token_quantity > risk.proposed_token_quantity
        ):
            raise ValueError("Quote size exceeds revalidated Risk allowance")
        parameters = DemoBuyParameters(
            **MARKER,
            ticker=quote.ticker,
            issuer=quote.issuer,
            chain_id=quote.chain_id,
            target_token=quote.contract,
            token_symbol=quote.symbol,
            token_decimals=quote.decimals,
            token_base_units=str(int(Fraction(quote.output_token_quantity) * 10**quote.decimals)),
            quote_id=quote.quote_id,
            quantity=quote.output_token_quantity,
            base_notional_usd=quote.base_notional_usd,
            maximum_input_usd=quote.input_amount_usd,
            minimum_output_tokens=quote.output_token_quantity,
            maximum_slippage_bps=quote.slippage_bps,
            fees_usd=quote.fees_usd,
            gas_usd=quote.gas_usd,
            execution_buffer_usd=quote.execution_buffer_usd,
            total_cash_required_usd=quote.total_cash_required_usd,
        )
        request = PreparedDemoRequest(
            **MARKER,
            transaction_id=UUID(int=0),
            fingerprint="0" * 64,
            quote_fingerprint=quote.fingerprint,
            context_sha256=quote.context_sha256,
            quote_id=quote.quote_id,
            opportunity_id=quote.opportunity_id,
            prepared_at=now,
            valid_until=quote.valid_until,
            parameters=parameters,
        )
        fingerprint = artifact_digest(request, "transaction_id")
        return PreparedDemoRequest.model_validate(
            {
                **request.model_dump(),
                "fingerprint": fingerprint,
                "transaction_id": artifact_id("request", fingerprint),
            }
        )
