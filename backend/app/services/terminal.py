"""Observational composition over existing authorities; no provider or execution calls."""

from decimal import Decimal, localcontext

from app.models.data import EquityObservation, Issuer, TokenMetadata, TokenObservation
from app.models.portfolio import portfolio_fingerprint
from app.models.terminal import (
    AgentEvidenceRow,
    AgentView,
    EpisodeRow,
    ExecutionAnalyticsRow,
    IssuerRow,
    ObservationRef,
    PortfolioMonitor,
    TerminalOverview,
    TerminalPage,
    TrustMonitorRow,
)
from app.services.normalization import comparable_economics, effective_price_per_share
from app.services.trust_evidence import seconds


def ref(record):
    return ObservationRef(
        digest=portfolio_fingerprint(record),
        source=record.source,
        provider_identifier=record.provider_identifier,
        observed_at=record.source_timestamp,
        available_at=record.ingestion_timestamp,
        data_quality=record.data_quality,
    )


def page(items, query, reasons=()):
    return TerminalPage(
        items=tuple(items[query.offset : query.offset + query.limit]),
        limit=query.limit,
        offset=query.offset,
        has_more=len(items) > query.offset + query.limit,
        reasons=tuple(reasons),
    )


class TerminalService:
    def __init__(self, layer, trust, agents, execution, positions, portfolio, research, *, clock):
        self.layer, self.trust, self.agents = layer, trust, agents
        self.execution, self.positions, self.portfolio = execution, positions, portfolio
        self.research, self.clock = research, clock
        self.mode = portfolio.mode

    def _cached(self, model, ticker, at):
        rows = self.layer.repository.list(model, mode=self.layer.mode, ticker=ticker)
        if any(r.data_mode != self.layer.mode for r in rows):
            raise ValueError("Cached record mode binding conflict")
        if len(rows) >= 1000:
            raise ValueError("Cache inspection bound exceeded")
        return [
            r
            for r in rows
            if r.ingestion_timestamp <= at
            and (r.source_timestamp is None or r.source_timestamp <= at)
        ]

    def _monitor(self, ticker, at, issuer=None, contract=None):
        assessment = self.trust.repository.latest(ticker, self.layer.mode, at)
        if assessment is None:
            return TrustMonitorRow(
                ticker=ticker,
                issuer=issuer,
                contract=contract,
                freshness="UNAVAILABLE",
                reasons=("NO_PERSISTED_TRUST_ASSESSMENT",),
            )
        candidates = [
            r
            for r in assessment.representations
            if (issuer is None or r.issuer == issuer)
            and (contract is None or r.contract == contract)
        ]
        stored = candidates[0] if len(candidates) == 1 else None
        if stored and (len(stored.analogues.matches) > 20 or len(stored.news.article_ids) > 50):
            raise ValueError("Persisted Trust evidence bound exceeded")
        age = seconds(at - assessment.evaluated_at)
        fresh = 0 <= age <= 120
        return TrustMonitorRow(
            ticker=ticker,
            issuer=issuer,
            contract=contract,
            assessment_id=str(assessment.assessment_id),
            assessed_at=assessment.evaluated_at,
            age_seconds=max(age, Decimal(0)),
            freshness="FRESH" if fresh else "STALE",
            classification=stored.classification if fresh and stored else "INSUFFICIENT_EVIDENCE",
            confidence=stored.confidence if fresh and stored else None,
            regime=assessment.regime.state if assessment.regime else None,
            stored_evidence=stored,
            reasons=tuple(
                dict.fromkeys(
                    (
                        *assessment.limitations,
                        *(
                            stored.reason_codes
                            if stored
                            else ["REPRESENTATION_ASSESSMENT_UNAVAILABLE"]
                        ),
                        *([] if fresh else ["PERSISTED_TRUST_STALE"]),
                    )
                )
            ),
        )

    def issuers(self, query, at):
        metadata = self._cached(TokenMetadata, query.ticker, at)
        observations = self._cached(TokenObservation, query.ticker, at)
        equities = self._cached(EquityObservation, query.ticker, at)
        issuers = self._cached(Issuer, None, at)
        regime = self.trust.regimes.evaluate(at)
        groups = {}
        for token in metadata:
            groups.setdefault((token.ticker, token.chain_id, token.contract), []).append(token)
        rows = []
        for key, versions in sorted(groups.items()):
            versions.sort(
                key=lambda r: (r.ingestion_timestamp, portfolio_fingerprint(r)), reverse=True
            )
            token = versions[0]
            reasons = []
            if any(
                v.ingestion_timestamp == token.ingestion_timestamp
                and (v.platform_id, v.token_to_share_ratio)
                != (token.platform_id, token.token_to_share_ratio)
                for v in versions
            ):
                reasons.append("CONFLICTING_METADATA")
            if not any(
                i.platform_id == token.platform_id and token.chain_id in i.chains for i in issuers
            ):
                reasons.append("ISSUER_MAPPING_UNRESOLVED")
            prices = [
                p
                for p in observations
                if (p.ticker, p.chain_id, p.contract) == key
                and p.kind in {"PRICE", "PRICE_INFO"}
                and p.source_timestamp is not None
            ]
            prices.sort(key=lambda p: (p.source_timestamp, portfolio_fingerprint(p)), reverse=True)
            price = prices[0] if prices else None
            if price and any(
                p.source_timestamp == price.source_timestamp
                and (p.token_price, p.issuer, p.token_to_share_ratio)
                != (price.token_price, price.issuer, price.token_to_share_ratio)
                for p in prices
            ):
                reasons.append("CONFLICTING_PRICE_OBSERVATIONS")
            refs = [
                e
                for e in equities
                if e.ticker == token.ticker
                and e.source_timestamp is not None
                and e.kind
                in ({"QUOTE", "SNAPSHOT"} if regime.state == "REGULAR" else {"REGULAR_CLOSE"})
            ]
            refs.sort(key=lambda e: (e.source_timestamp, portfolio_fingerprint(e)), reverse=True)
            independent = refs[0] if refs else None
            if independent and any(
                e.source_timestamp == independent.source_timestamp and e.price != independent.price
                for e in refs
            ):
                reasons.append("CONFLICTING_EQUITY_OBSERVATIONS")
            reference = self.trust.references.evaluate(
                token, price, independent, regime, at, self.layer.mode
            )
            # Token normalization may be available without an independent reference. The same
            # reference validator verifies metadata/price identities, units and freshness first.
            token_reasons = [
                r
                for r in reference.reason_codes
                if r.startswith(
                    ("TOKEN_", "RATIO_", "NOT_STOCK", "DEMO_IDENTITY", "INVALID_FINANCIAL")
                )
            ]
            reasons.extend(reference.reason_codes)
            economics = None
            effective = None
            conflicts = any("CONFLICT" in r for r in reasons)
            if (
                not conflicts
                and not token_reasons
                and price
                and price.token_price is not None
                and "ISSUER_MAPPING_UNRESOLVED" not in reasons
            ):
                effective = effective_price_per_share(price.token_price, token.token_to_share_ratio)
                if reference.status == "AVAILABLE":
                    economics = comparable_economics(
                        price.token_price, token.token_to_share_ratio, independent.price
                    )
            info = next((p for p in prices if p.kind == "PRICE_INFO"), None)
            liquidity = self.trust.liquidity.evaluate(token, info, at, self.layer.mode)
            reasons.extend(liquidity.reason_codes)
            if token.open_state is not True or token.reason_code in {
                "ASSET_PAUSED",
                "ASSET_LIMITED",
                "UNSUPPORTED",
                "MARKET_MAINTENANCE",
            }:
                reasons.append("REPRESENTATION_NOT_VERIFIED_TRADABLE")
            monitor = self._monitor(token.ticker, at, token.platform_id, token.contract)
            if monitor.classification == "INSUFFICIENT_EVIDENCE":
                reasons.append("TRUST_INSUFFICIENT_EVIDENCE")
            with localcontext() as ctx:
                ctx.prec = 256
                percent = economics["deviation"] * 100 if economics else None
                spread = effective - independent.price if economics else None
            stale = any("STALE" in r or "SKEW" in r for r in reasons)
            rows.append(
                IssuerRow(
                    ticker=token.ticker,
                    company=token.company_name,
                    issuer=token.platform_id,
                    token=token.token_symbol,
                    contract=token.contract,
                    chain_id=token.chain_id,
                    token_price_usd=price.token_price if price else None,
                    token_to_share_ratio=token.token_to_share_ratio,
                    ratio_observed_at=token.ingestion_timestamp,
                    ratio_source_timestamp=token.source_timestamp,
                    effective_price_per_share_usd=effective,
                    independent_equity_price_usd=independent.price if economics else None,
                    comparable_token_value_usd=economics["comparable_token_value_usd"]
                    if economics
                    else None,
                    deviation=economics["deviation"] if economics else None,
                    absolute_deviation=economics["absolute_deviation"] if economics else None,
                    deviation_percent=percent,
                    spread_usd_per_share=spread,
                    reference=reference,
                    liquidity=liquidity,
                    trust=monitor,
                    eligibility="INSUFFICIENT_EVIDENCE" if reasons else "ANALYTICAL_ONLY",
                    freshness="CONFLICTING"
                    if conflicts
                    else "STALE"
                    if stale
                    else "FRESH"
                    if effective is not None
                    else "UNAVAILABLE",
                    tradable=token.open_state,
                    market_state=token.market_state,
                    regime=regime.state,
                    reasons=tuple(dict.fromkeys(reasons)),
                    observations=tuple(
                        ref(r) for r in (token, price, independent, info) if r is not None
                    ),
                )
            )
        return page(rows, query, ("BOUNDED_PERSISTED_CACHE_NO_PROVIDER_REFRESH",))

    def trust_monitor(self, query, at):
        tokens = self._cached(TokenMetadata, query.ticker, at)
        identities = sorted({(t.ticker, t.platform_id, t.contract) for t in tokens})
        rows = [self._monitor(t, at, i, c) for t, i, c in identities]
        if query.ticker and not rows:
            rows = [self._monitor(query.ticker, at)]
        return page(rows, query)

    def agent_evidence(self, query, at):
        # Agent run filtering precedes pagination, bounded by an explicit catalog cap.
        runs = self.agents.list_runs(self.mode, at, limit=101)
        if len(runs) > 100:
            raise ValueError("Agent catalog inspection bound exceeded")
        rows = []
        for run in runs:
            if query.ticker and not any(c.ticker == query.ticker for c in run.candidate_table):
                continue
            memory = {}
            for c in run.candidate_table:
                if c.regime:
                    for m in self.agents.recent(c.ticker, self.mode, c.regime, run.timestamp):
                        memory[m.memory_id] = m
            rows.append(
                AgentEvidenceRow(
                    run_id=run.run_id,
                    decision_id=run.decision_id,
                    correlation_id=run.correlation_id,
                    timestamp=run.timestamp,
                    status=run.status,
                    agents=tuple(
                        AgentView(
                            agent=r.agent,
                            status=r.status,
                            confidence=r.confidence.tier,
                            provider=r.provider,
                            model=r.model,
                            timestamp=r.timestamp,
                            evidence_refs=r.evidence_refs,
                            reasons=r.limitations,
                            conflicts=r.conflicts,
                            output=r.output,
                        )
                        for r in run.responses
                    ),
                    evidence=run.evidence,
                    decision=run.decision,
                    memory=tuple(memory.values()),
                )
            )
        return page(rows, query)

    def executions(self, query, at):
        attempts = self.execution.list(mode=self.mode, limit=101)
        if len(attempts) > 100 or self.positions.store.count(mode=self.mode) > 1000:
            raise ValueError("Execution/position catalog inspection bound exceeded")
        positions = self.positions.store.list(mode=self.mode, limit=1000)
        rows = []
        for a in attempts:
            p = next(
                (
                    p
                    for p in positions
                    if a.execution_id
                    in {
                        p.entry_execution.execution_id,
                        *(e.execution_id for e in p.applied_exit_executions),
                        *(
                            [p.exit_intent.execution.execution_id]
                            if p.exit_intent and p.exit_intent.execution
                            else []
                        ),
                    }
                ),
                None,
            )
            if query.ticker and (p is None or p.instrument.ticker != query.ticker):
                continue
            if a.updated_at > at:
                raise ValueError("Execution record in future")
            linked = (
                [
                    p.entry_execution,
                    *p.applied_exit_executions,
                    *(
                        [p.exit_intent.execution]
                        if p.exit_intent and p.exit_intent.execution
                        else []
                    ),
                ]
                if p
                else []
            )
            snapshot_current = any(e == a for e in linked)
            reconcile = a.settlement_conflict or (
                p and (p.state == "RECONCILIATION_REQUIRED" or not snapshot_current)
            )
            category = (
                "RECONCILIATION_REQUIRED"
                if reconcile
                else "UNKNOWN"
                if a.state == "EXECUTION_UNKNOWN" or (p and p.state == "UNKNOWN")
                else "CONFIRMED"
                if a.state == "EXECUTION_CONFIRMED"
                else "SUBMITTED"
                if a.state in {"EXECUTION_PENDING", "EXECUTION_SUBMITTED"}
                else "FAILED"
                if a.state
                in {
                    "EXECUTION_FAILED",
                    "EXECUTION_EXPIRED",
                    "EXECUTION_CANCELLED",
                    "SIMULATION_FAILED",
                }
                else "BLOCKED"
                if a.state == "BLOCKED"
                else "SIMULATED"
                if a.simulation and a.simulation.status == "PASS"
                else "DRY_RUN"
                if a.quote
                else "PROPOSED"
            )
            confirmed = category == "CONFIRMED"
            q = a.quote
            rows.append(
                ExecutionAnalyticsRow(
                    execution_id=str(a.execution_id),
                    decision_id=a.decision_id,
                    correlation_id=a.correlation_id,
                    source=a.source,
                    synthetic=a.source == "TEST_FIXTURE",
                    lifecycle_state=a.state,
                    category=category,
                    actual_completed_trade=confirmed and a.source == "BINANCE_WEB3",
                    created_at=a.created_at,
                    updated_at=a.updated_at,
                    settled_at=a.settled_at if confirmed else None,
                    provider=q.route.vendorName if q else None,
                    execution_mode=q.route.executionMode if q else None,
                    quote_id=q.route.quoteId if q else None,
                    quoted_at=q.received_at if q else None,
                    quote_expires_at=q.expires_at if q else None,
                    fingerprint=a.route.fingerprint if a.route else None,
                    simulation_status=a.simulation.status if a.simulation else None,
                    simulation_at=a.simulation.evaluated_at if a.simulation else None,
                    risk_status=a.risk.status if a.risk else None,
                    funding_status=a.funding.status if a.funding else None,
                    requested_base_units=q.request.amount if q else None,
                    quoted_output_base_units=q.route.toTokenAmount if q else None,
                    filled_base_units=a.filled_quantity_base_units if confirmed else None,
                    average_execution_price=a.average_execution_price if confirmed else None,
                    network_fee_estimate_usd=q.route.tradeFee if q else None,
                    estimated_gas_provider_units=q.route.estimateGasFee if q else None,
                    actual_fees_native_base_units=a.fees_native_base_units if confirmed else None,
                    quote_latency_seconds=seconds(q.received_at - q.requested_at) if q else None,
                    position_id=str(p.position_id) if p else None,
                    position_state=p.state if p else None,
                    remaining_base_units=p.remaining_quantity_base_units
                    if p
                    and snapshot_current
                    and p.state in {"OPEN", "EXIT_PENDING", "EXITING", "CLOSED"}
                    else None,
                    realized_gross_pnl_usd=p.gross_pnl_usd
                    if confirmed and p and snapshot_current
                    else None,
                    realized_net_pnl_usd=p.net_pnl_usd
                    if confirmed and p and snapshot_current
                    else None,
                    reasons=tuple(
                        dict.fromkeys(
                            (
                                *a.reason_codes,
                                *(
                                    ["POSITION_EXECUTION_SNAPSHOT_BEHIND_JOURNAL"]
                                    if p and not snapshot_current
                                    else []
                                ),
                            )
                        )
                    ),
                )
            )
        return page(
            rows,
            query,
            ("QUOTED_UNITS_ARE_NOT_FILLED_UNITS", "ESTIMATED_GAS_UNITS_NOT_ASSUMED_USD"),
        )

    def episodes(self, query, at):
        as_of = getattr(query, "as_of", None) or at
        if as_of > at:
            raise ValueError("Future historical cutoff denied")
        rows = []
        for run in self.research.list(self.layer.mode):
            if len(run.episodes) > 5000:
                raise ValueError("Replay episode inspection bound exceeded")
            replay = {r.episode_id: r for r in run.rows}
            for e in run.episodes:
                d, target = e.decision, e.target
                if d.decision_at > as_of or (query.ticker and d.ticker != query.ticker):
                    continue
                r = replay[e.episode_id]
                if (
                    r.decision_at != d.decision_at
                    or r.decision_id != d.decision_id
                    or any(
                        m.outcome_available_at > d.decision_at
                        or m.feature_available_at > d.decision_at
                        for m in r.retrieval.matches
                    )
                ):
                    raise ValueError("Replay point-in-time binding conflict")
                if any(
                    i
                    not in {
                        old.episode_id
                        for old in run.episodes
                        if old.target.status == "AVAILABLE"
                        and old.target.available_at <= d.decision_at
                        and old.decision.decision_at < d.decision_at
                    }
                    for i in r.prediction.training_ids
                ):
                    raise ValueError("Replay future training evidence")
                available = target.status == "AVAILABLE" and target.available_at <= as_of
                f = d.sample.features if d.sample else None
                rows.append(
                    EpisodeRow(
                        run_id=run.run_id,
                        dataset_digest=run.dataset_digest,
                        implementation_digest=run.implementation_digest,
                        episode_id=e.episode_id,
                        ticker=d.ticker,
                        issuer=d.issuer,
                        contract=d.contract,
                        decision_at=d.decision_at,
                        query_as_of=as_of,
                        regime=d.regime,
                        evidence_kind=e.evidence_kind,
                        eligibility=d.data_quality,
                        trust_state=r.trust_state,
                        deviation=f.deviation if f else None,
                        volume_usd=f.volume_24h_usd if f else None,
                        liquidity_usd=f.liquidity_usd if f else None,
                        feature_available_at=f.available_at if f else None,
                        prediction=r.prediction,
                        retrieval=r.retrieval,
                        opening_outcome=target if available else None,
                        outcome_state="AVAILABLE"
                        if available
                        else "NOT_YET_AVAILABLE"
                        if target.status == "AVAILABLE"
                        else target.status,
                        reasons=tuple(dict.fromkeys((*d.reasons, *r.reasons, *target.reasons))),
                        provenance=tuple(
                            ObservationRef(
                                digest=p.record_digest,
                                source=p.source,
                                provider_identifier=p.record_digest,
                                observed_at=p.effective_at,
                                available_at=p.available_at,
                                data_quality="POINT_IN_TIME_VERIFIED",
                            )
                            for p in d.provenance
                        ),
                    )
                )
        rows.sort(key=lambda e: (e.decision_at, e.run_id, e.episode_id), reverse=True)
        return page(rows, query)

    def overview(self, query, context):
        config = self.portfolio.store.config(mode=self.mode)
        pending = self.portfolio.store.pending(mode=self.mode)
        at = context["generated_at"]
        return TerminalOverview(
            **context,
            issuers=self.issuers(query, at),
            trust=self.trust_monitor(query, at),
            agents=self.agent_evidence(query, at),
            executions=self.executions(query, at),
            episodes=self.episodes(query, at),
            portfolio=PortfolioMonitor(
                config_version=config.version if config else None,
                pending_plan_id=pending.plan_id if pending else None,
                status=pending.status
                if pending
                else "NO_PENDING_PLAN"
                if config
                else "NOT_CONFIGURED",
                reasons=pending.reasons if pending else (),
            ),
        )
