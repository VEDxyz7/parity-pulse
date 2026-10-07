"""Validated vendor quotes for an already selected discovered representation.

Issuer routing remains the shared RoutingService. Here only executable provider routes
for that exact pair/amount are compared, deterministically and without an LLM.
"""

from decimal import Decimal, localcontext

from app.models.execution import ProviderQuote
from app.services.execution_builders import current_quote


class AggregatorQuoteService:
    def __init__(self, provider):
        self.provider = provider

    def select(self, request, *, mode, funding, evidence, now):
        quotes = self.provider.quote(request, mode=mode)
        if not quotes or len(quotes) > 100:
            raise ValueError("EMPTY_OR_OVERSIZED_QUOTE_ROUTES")
        accepted = []
        for item in quotes:
            q = ProviderQuote.model_validate_json(item.model_dump_json())
            current_quote(q, now)
            if q.request != request or q.data_mode != mode:
                raise ValueError("QUOTE_REQUEST_OR_MODE_MISMATCH")
            if (q.source == "TEST_FIXTURE") != (
                getattr(self.provider, "fixture_only", False) is True
            ):
                raise ValueError("QUOTE_SOURCE_ISOLATION")
            r = q.route
            if (
                r.tradeFee is not None
                and r.tradeFee <= evidence.costs_usd
                and r.approveTarget is not None
                and r.priceImpactPercent is not None
                and abs(r.priceImpactPercent) <= evidence.slippage_bps / Decimal(100)
                and r.fromToken.tokenUnitPrice == funding.state.unit_price_usd
                and int(r.fromToken.decimal) == funding.state.asset.decimals
            ):
                accepted.append(q)
        if not accepted:
            raise ValueError("VERIFIED_COST_COMPATIBLE_QUOTE_UNAVAILABLE")
        # Different marks/decimals make a comparison ambiguous. Never choose favorable metadata.
        if len({(q.route.toToken.decimal, q.route.toToken.tokenUnitPrice) for q in accepted}) != 1:
            raise ValueError("CONFLICTING_OUTPUT_TOKEN_METADATA")

        def key(q):
            with localcontext() as ctx:
                ctx.prec = 256
                r = q.route
                # Quoted output mark value less the documented USD network fee.
                # This is route economics, never an independent traditional-equity reference.
                net = (
                    Decimal(r.toTokenAmount)
                    / 10 ** int(r.toToken.decimal)
                    * r.toToken.tokenUnitPrice
                    - r.tradeFee
                )
            return -net, q.route.vendorName, q.route.quoteId

        return sorted(accepted, key=key)[0]
