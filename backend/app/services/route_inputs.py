"""Boundary adapters only. The shared router owns all eligibility and ranking rules."""

from app.models.routing import RouteIdentity, RouteInput, RoutePolicy


def from_estimate(item, token, *, assessment=None):
    candidate = RouteInput(
        identity=RouteIdentity(
            underlying=item.ticker,
            issuer=item.issuer,
            chain_id=item.chain_id,
            contract=item.contract,
            token=item.token_symbol,
        ),
        data_mode=item.data_mode,
        token_price_usd=item.token_price_usd,
        token_to_share_ratio=item.token_to_share_ratio,
        price_source=item.price_source,
        price_timestamp=item.price_timestamp,
        price_quality=item.price_quality,
        ratio_source=item.ratio_source,
        ratio_observed_at=item.ratio_observed_at,
        ratio_source_timestamp=item.ratio_source_timestamp,
        normalization_eligible=item.estimate_eligible,
        normalization_reasons=item.exclusion_reasons,
        supported=token.asset_type == 1
        and token.reason_code
        not in {
            "ASSET_PAUSED",
            "ASSET_LIMITED",
            "UNSUPPORTED",
            "MARKET_MAINTENANCE",
        },
        market_state=token.market_state,
        tradable=token.open_state,
    )

    if (
        assessment is None
        or assessment.ticker != item.ticker
        or assessment.data_mode != item.data_mode
    ):
        return candidate
    row = next(
        (
            r
            for r in assessment.representations
            if (r.ticker, r.issuer, r.chain_id, r.contract, r.symbol)
            == (item.ticker, item.issuer, item.chain_id, item.contract, item.token_symbol)
        ),
        None,
    )
    # A recent classification cannot be reused for a changed price/ratio or unrelated observation.
    if (
        row is None
        or row.token_price_usd != item.token_price_usd
        or row.token_to_share_ratio != item.token_to_share_ratio
        or row.token_timestamp is None
        or item.price_timestamp is None
        or abs((row.token_timestamp - item.price_timestamp).total_seconds()) > 30
    ):
        return candidate
    return RouteInput.model_validate(
        {
            **candidate.model_dump(),
            "trust_state": row.classification,
            "trust_source": "CACHED_DETERMINISTIC_TRUST_SERVICE",
            "trust_timestamp": assessment.evaluated_at,
            "trust_assessment_id": assessment.assessment_id,
            "liquidity_usd": row.liquidity.liquidity_usd,
            "liquidity_status": "AVAILABLE"
            if row.liquidity.status == "AVAILABLE"
            else "UNAVAILABLE",
            "liquidity_source": row.liquidity.source,
            "liquidity_timestamp": row.liquidity.observed_at,
            "volume_usd": row.liquidity.volume_24h_usd,
        }
    )


def opportunity_input(token, price, assessment, decision, risk, economics):
    row = next(
        (
            r
            for r in assessment.representations
            if (r.ticker, r.issuer, r.chain_id, r.contract, r.symbol)
            == (token.ticker, token.platform_id, token.chain_id, token.contract, token.token_symbol)
        ),
        None,
    )
    if row is None or assessment.data_mode != token.data_mode:
        raise ValueError("Routing requires a matching Trust representation")
    if (
        (
            price.ticker,
            price.issuer,
            price.chain_id,
            price.contract,
            price.token_symbol,
            price.token_to_share_ratio,
            price.data_mode,
        )
        != (
            token.ticker,
            token.platform_id,
            token.chain_id,
            token.contract,
            token.token_symbol,
            token.token_to_share_ratio,
            token.data_mode,
        )
        or (decision.ticker, decision.issuer, decision.chain_id, decision.contract, decision.symbol)
        != (
            token.ticker,
            token.platform_id,
            token.chain_id,
            token.contract,
            token.token_symbol,
        )
        or risk.opportunity_id != decision.opportunity_id
    ):
        raise ValueError("Routing cannot mix market, Opportunity and Risk identities")
    # Existing downstream engine currently supports synthetic analytical inputs only.
    # This adapter does not claim a provider execution route or production Opportunity permission.
    return RouteInput(
        identity=RouteIdentity(
            underlying=token.ticker,
            issuer=token.platform_id,
            chain_id=token.chain_id,
            contract=token.contract,
            token=token.token_symbol,
        ),
        data_mode=token.data_mode,
        token_price_usd=price.token_price,
        token_to_share_ratio=token.token_to_share_ratio,
        price_source=price.source,
        price_timestamp=price.source_timestamp,
        price_quality=price.data_quality,
        ratio_source=token.source,
        ratio_observed_at=token.ingestion_timestamp,
        ratio_source_timestamp=token.source_timestamp,
        supported=token.asset_type == 1
        and token.reason_code
        not in {"ASSET_PAUSED", "ASSET_LIMITED", "UNSUPPORTED", "MARKET_MAINTENANCE"},
        normalization_eligible=decision.status == "ACTIONABLE",
        normalization_reasons=[] if decision.status == "ACTIONABLE" else decision.reason_codes,
        market_state=token.market_state,
        tradable=token.open_state,
        liquidity_usd=row.liquidity.liquidity_usd,
        liquidity_status="AVAILABLE" if row.liquidity.status == "AVAILABLE" else "UNAVAILABLE",
        liquidity_source=row.liquidity.source,
        liquidity_timestamp=row.liquidity.observed_at,
        volume_usd=row.liquidity.volume_24h_usd,
        fees_usd=economics.fees_usd,
        gas_usd=economics.gas_usd,
        slippage_bps=economics.slippage_bps,
        cost_status="AVAILABLE",
        cost_source="SYNTHETIC_DEMO_ECONOMICS",
        cost_timestamp=economics.observed_at,
        trust_state=row.classification,
        trust_source="DETERMINISTIC_TRUST_SERVICE",
        trust_timestamp=assessment.evaluated_at,
        trust_assessment_id=assessment.assessment_id,
        risk_state=risk.status,
        risk_source="DETERMINISTIC_RISK_ENGINE",
        risk_timestamp=risk.evaluated_at,
        risk_id=risk.risk_id,
        risk_max_notional_usd=risk.maximum_allowed_notional_usd,
        risk_reason_codes=risk.reason_codes,
        route_available=True,
        route_support="SYNTHETIC_DEMO_PREPARATION",
    )


def opportunity_policy(policy):
    return RoutePolicy(
        purpose="OPPORTUNITY",
        require_costs=True,
        require_liquidity=True,
        require_trust=True,
        require_risk=True,
        min_liquidity_usd=policy.min_liquidity_usd,
        max_slippage_bps=policy.max_slippage_bps,
    )
