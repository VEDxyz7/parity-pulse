"""Deterministic indicative routing only; this service has no execution gateway."""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from uuid import uuid4

from pydantic import ValidationError

from app.clients.common import ProviderError
from app.models.data import EquityObservation, TokenMetadata, TokenObservation, quality_at
from app.models.exposure import (
    ExposureProposal,
    IndependentReference,
    RepresentationEstimate,
)
from app.repositories.exposure import ExposureRepository
from app.services.intent import parse_intent
from app.services.normalization import bounded_decimal, effective_price_per_share
from app.services.route_inputs import from_estimate
from app.services.routing import RoutingService
from app.services.routing_evidence import RoutingEvidenceReader

logger = logging.getLogger("parity.exposure")
BLOCKERS = [
    "TRUST_NOT_IMPLEMENTED",
    "FEES_SLIPPAGE_GAS_UNKNOWN",
    "LIQUIDITY_NOT_VERIFIED",
    "FUNDING_AND_WALLET_NOT_VERIFIED",
    "PROVIDER_ROUTE_NOT_VERIFIED",
    "SIMULATION_UNAVAILABLE",
    "SWAP_LIVE_GATE_BLOCKED",
    "RFQ_LIVE_GATE_BLOCKED",
    "AGENTIC_WALLET_LIVE_GATE_BLOCKED",
]


def estimate(token, price, budget, now, mode):
    reasons = []
    if token.data_mode != mode or price.data_mode != mode:
        reasons.append("DATA_MODE_MISMATCH")
    if (
        token.ticker,
        token.platform_id,
        token.chain_id,
        token.contract,
        token.token_symbol,
        token.token_to_share_ratio,
    ) != (
        price.ticker,
        price.issuer,
        price.chain_id,
        price.contract,
        price.token_symbol,
        price.token_to_share_ratio,
    ):
        reasons.append("CONFLICTING_OBSERVATION")
    quality = price.data_quality
    if mode == "LIVE":
        freshness = quality_at(mode, price.source_timestamp, now)
        quality = freshness if price.data_quality == "LIVE" else price.data_quality
        if price.data_quality != "LIVE" or freshness != "LIVE":
            reasons.append("TOKEN_PRICE_NOT_FRESH_VERIFIED")
        if not 0 <= (now - token.ingestion_timestamp).total_seconds() <= 120:
            reasons.append("RATIO_METADATA_STALE_OR_FUTURE")
        if token.chain_id == "DEMO" or token.contract.startswith("demo:"):
            reasons.append("DEMO_IDENTITY_IN_LIVE")
    if token.asset_type != 1:
        reasons.append("NOT_STOCK")
    if (
        token.market_state not in {"premarket", "regular", "postmarket"}
        or token.open_state is not True
    ):
        reasons.append("ISSUER_MARKET_NOT_ELIGIBLE")
    if token.decimals is None or token.decimals > 36:
        reasons.append("TOKEN_DECIMALS_NOT_SUPPORTED")
    if price.kind != "PRICE" or price.token_price is None:
        reasons.append("TOKEN_PRICE_MISSING_OR_WRONG_KIND")
    for value in (price.token_price, token.token_to_share_ratio):
        bounded_decimal(value)
    kwargs = {}
    if not reasons:
        with localcontext() as ctx:
            ctx.prec = 256
            effective = effective_price_per_share(
                price.token_price, token.token_to_share_ratio, presentation=True
            )
            exact_units = Fraction(budget) / Fraction(price.token_price) * 10**token.decimals
            units = exact_units.numerator // exact_units.denominator
            if units == 0:
                reasons.append("BUDGET_BELOW_ONE_TOKEN_BASE_UNIT")
            else:
                quantity = Decimal(units).scaleb(-token.decimals)
                spent = quantity * price.token_price
                kwargs = dict(
                    effective_cost_per_share_usd=effective,
                    estimated_token_quantity=quantity,
                    token_base_units=str(units),
                    estimated_real_share_exposure=quantity * token.token_to_share_ratio,
                    estimated_token_cost_usd=spent,
                    unallocated_budget_usd=budget - spent,
                )
    return RepresentationEstimate(
        issuer=token.platform_id,
        chain_id=token.chain_id,
        contract=token.contract,
        token_symbol=token.token_symbol,
        ticker=token.ticker,
        company_name=token.company_name,
        token_to_share_ratio=token.token_to_share_ratio,
        token_price_usd=price.token_price,
        decimals=token.decimals,
        market_state=token.market_state,
        price_source=price.source,
        price_timestamp=price.source_timestamp,
        price_quality=quality,
        ratio_source=token.source,
        ratio_observed_at=token.ingestion_timestamp,
        ratio_source_timestamp=token.source_timestamp,
        data_mode=mode,
        estimate_eligible=not reasons,
        exclusion_reasons=reasons,
        **kwargs,
    )


def independent_reference(equity, ticker, mode, now):
    if equity is None:
        return IndependentReference(status="UNAVAILABLE", reason="NO_INDEPENDENT_CURRENT_QUOTE")
    equity = EquityObservation.model_validate(equity.model_dump())
    if equity.ticker != ticker or equity.data_mode != mode or equity.source.startswith("BINANCE"):
        return IndependentReference(status="UNVERIFIED", reason="INDEPENDENT_IDENTITY_NOT_VERIFIED")
    fresh = quality_at(mode, equity.source_timestamp, now)
    status = "DEMO" if mode == "DEMO" else "AVAILABLE"
    reason = "SYNTHETIC_DEMO_REFERENCE" if mode == "DEMO" else "INDEPENDENT_CURRENT_REFERENCE"
    value = equity.price
    if mode == "LIVE" and (equity.data_quality != "LIVE" or fresh != "LIVE"):
        status, reason, value = (
            "STALE" if fresh == "STALE" else "UNVERIFIED",
            "NOT_CURRENT_VERIFIED",
            None,
        )
    if equity.kind not in {"SNAPSHOT", "QUOTE"} or value is None:
        if status in {"DEMO", "AVAILABLE"}:
            status, reason, value = "UNAVAILABLE", "NO_INDEPENDENT_CURRENT_QUOTE", None
    return IndependentReference(
        status=status,
        price_usd_per_share=value,
        source=equity.source,
        source_timestamp=equity.source_timestamp,
        reason=reason,
    )


class ExposureService:
    def __init__(self, layer, database, *, clock=lambda: datetime.now(UTC)):
        self.layer, self.repository, self.clock = layer, ExposureRepository(database), clock
        self.router = RoutingService()
        self.routing_evidence = RoutingEvidenceReader(database)

    def propose(self, text, *, run_id, request_id, correlation_id):
        intent = parse_intent(text)
        mode = self.layer.mode
        now = self.clock()
        comparisons, limitations, asset, independent = [], {}, None, None
        metadata = {}
        reason = intent.reason
        if intent.status == "VALID":
            try:
                found = self.layer.discovery.resolve(intent.stock_query)
                if found["status"] not in {"VERIFIED", "DEMO"}:
                    reason = found["reason"]
                else:
                    asset = found["asset"]
                    if asset.data_mode != mode or not asset.supported:
                        raise ProviderError("EXPOSURE", "DATA_MODE_OR_ASSET_MISMATCH")
                    seen = set()
                    for discovered in found["tokens"]:
                        key = discovered.chain_id, discovered.contract
                        if key in seen:
                            raise ProviderError("EXPOSURE", "DUPLICATE_REPRESENTATION")
                        seen.add(key)
                        token = self.layer.rwa.profile(discovered)
                        price = self.layer.rwa.observation(token)
                        # Revalidate immutable models; model_copy/mock inputs cannot bypass safety.
                        token = TokenMetadata.model_validate(
                            {name: getattr(token, name) for name in TokenMetadata.model_fields}
                        )
                        price = TokenObservation.model_validate(
                            {name: getattr(price, name) for name in TokenObservation.model_fields}
                        )
                        if token.data_mode != mode or price.data_mode != mode:
                            raise ProviderError("EXPOSURE", "DATA_MODE_MISMATCH")
                        if (
                            token.ticker,
                            token.platform_id,
                            token.chain_id,
                            token.contract,
                            token.token_symbol,
                            token.asset_type,
                        ) != (
                            asset.ticker,
                            discovered.platform_id,
                            discovered.chain_id,
                            discovered.contract,
                            discovered.token_symbol,
                            discovered.asset_type,
                        ):
                            raise ProviderError("EXPOSURE", "CONFLICTING_UNDERLYING")
                        metadata[(token.platform_id, token.chain_id, token.contract)] = token
                        comparisons.append(
                            estimate(token, price, intent.budget_usd, self.clock(), mode)
                        )
                        self.layer.repository.save([token, price])
                    self.layer.repository.save([asset, *found["issuers"]])
                    limitations.update(self.layer.catalog_limitations())
                    try:
                        independent = self.layer.equity.get_snapshot(asset.ticker)
                        self.layer.repository.save([independent])
                    except ProviderError as error:
                        limitations["independent_equity"] = error.kind
            except (ProviderError, ValidationError, ValueError, ArithmeticError) as error:
                reason = error.kind if isinstance(error, ProviderError) else "MALFORMED_DATA"
                comparisons = []  # No partial candidate wins after a critical integrity failure.
                independent = None
                limitations["data_failure"] = reason
        now = self.clock()  # Providers may be slow; recheck all candidates before routing.
        for item_index, item in enumerate(comparisons):
            if mode == "LIVE" and (
                quality_at(mode, item.price_timestamp, now) != "LIVE"
                or not 0 <= (now - item.ratio_observed_at).total_seconds() < 120
                or (now - item.price_timestamp).total_seconds() >= 120
            ):
                comparisons[item_index] = item.model_copy(
                    update={
                        "estimate_eligible": False,
                        "exclusion_reasons": [
                            *item.exclusion_reasons,
                            "PRICE_EXPIRED_DURING_REQUEST",
                        ],
                    }
                )
        cached_trust = self.routing_evidence.latest(
            asset.ticker if asset else None, mode=mode, now=now
        )
        route = self.router.decide(
            asset.ticker if asset else None,
            intent.budget_usd,
            [
                from_estimate(
                    item,
                    metadata[(item.issuer, item.chain_id, item.contract)],
                    assessment=cached_trust,
                )
                for item in comparisons
            ],
            mode=mode,
            now=now,
        )
        identity = route.selected_representation
        selected = next(
            (
                item
                for item in comparisons
                if identity is not None
                and (item.issuer, item.chain_id, item.contract)
                == (identity.issuer, identity.chain_id, identity.contract)
            ),
            None,
        )
        reference = independent_reference(independent, asset.ticker if asset else "", mode, now)
        blockers = [*BLOCKERS]
        if reference.status != "AVAILABLE":
            blockers.append("INDEPENDENT_CURRENT_EQUITY_UNAVAILABLE")
        if selected is not None and selected.ratio_source_timestamp is None:
            blockers.append("RATIO_AS_OF_TIME_NOT_VERIFIED")
        expiry = now + timedelta(seconds=30)
        if mode == "LIVE" and selected is not None:
            expiry = min(
                expiry,
                selected.price_timestamp + timedelta(seconds=120),
                selected.ratio_observed_at + timedelta(seconds=120),
            )
        proposal = ExposureProposal(
            route_decision=route,
            proposal_id=uuid4(),
            created_at=now,
            valid_until=expiry,
            run_id=run_id,
            request_id=request_id,
            correlation_id=correlation_id,
            data_mode=mode,
            status="DRY_RUN" if selected else "NO_PROPOSAL",
            intent=intent,
            ticker=asset.ticker if asset else None,
            company_name=asset.company_name if asset else None,
            requested_budget_usd=intent.budget_usd,
            representations=comparisons,
            selected=selected,
            independent_equity=reference,
            route_type="INDICATIVE_MARKET_ESTIMATE" if selected else "NONE",
            route_selection_reason=route.explanation
            if selected
            else (reason if reason != "EXPLICIT_USD_BUDGET" else "NO_ELIGIBLE_ESTIMATE"),
            quote_status="INDICATIVE_ONLY" if selected else "UNAVAILABLE",
            execution_blockers=blockers,
            limitations=limitations,
        )
        self.repository.save(proposal)  # Persistence failure means no successful proposal response.
        logger.info(
            "DRY_RUN_PROPOSAL_PERSISTED",
            extra={
                "event_fields": {
                    "run_id": run_id,
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "proposal_id": str(proposal.proposal_id),
                    "proposal_status": proposal.status,
                    "data_mode": mode,
                }
            },
        )
        return proposal
