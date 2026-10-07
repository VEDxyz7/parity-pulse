"""Full-universe deterministic filtering, economics, routing and bounded Phase 6 interpretation."""

import asyncio
import logging
from collections import Counter
from datetime import timedelta
from decimal import localcontext
from uuid import NAMESPACE_URL, uuid5

from app.agents.adapters import reference
from app.agents.opportunity_agent import ranked, rejection
from app.agents.orchestrator import AgentOrchestrator
from app.agents.schemas import Candidate, DownstreamEvidence, EvidenceBundle
from app.models.data import TokenObservation
from app.models.opportunity import OpportunityInputs
from app.models.opportunity_scan import (
    CandidateAudit,
    OpportunityRequest,
    OpportunityScan,
    ScanPolicy,
    ScanSnapshot,
)
from app.models.risk import RiskInputs
from app.models.routing import RoutePolicy
from app.models.trust import TrustAssessment
from app.services.normalization import comparable_economics
from app.services.opportunity import OpportunityEngine, analytical_edge
from app.services.research_episodes import fingerprint
from app.services.research_model import HistoricalRetrieval, RollingOpeningModel
from app.services.risk import RiskEngine
from app.services.route_inputs import opportunity_input, opportunity_policy
from app.services.routing import RoutingService

LOGGER = logging.getLogger("parity.opportunity_scan")
CRITICAL = frozenset(
    {
        "TRUST_EVIDENCE_INSUFFICIENT",
        "INDEPENDENT_EQUITY_UNAVAILABLE",
        "STALE_INDEPENDENT_EQUITY",
        "MISSING_CRITICAL_COSTS",
        "PREDICTION_INSUFFICIENT",
        "MAPPING_UNRESOLVED",
        "TOKEN_PRICE_UNAVAILABLE",
        "LIQUIDITY_UNAVAILABLE",
        "STALE_TOKEN_PRICE",
        "RISK_CONSTRAINTS_UNAVAILABLE",
        "TRUST_UNAVAILABLE",
        "SOURCE_EVIDENCE_CONFLICT",
    }
)


def identity(token):
    return token.ticker, token.platform_id, token.chain_id, token.contract


def candidate_id(token):
    return fingerprint(identity(token))


def fresh(stamp, at):
    return (
        stamp is not None and stamp.tzinfo is not None and 0 <= (at - stamp).total_seconds() <= 120
    )


class OpportunityScanService:
    def __init__(self, *, policy=None, orchestrator=None, store=None):
        self.policy = ScanPolicy.model_validate((policy or ScanPolicy()).model_dump())
        self.agents = orchestrator or AgentOrchestrator()
        self.router, self.risk, self.economics = RoutingService(), RiskEngine(), OpportunityEngine()
        self.store = store
        self._running = False

    async def scan(self, request, snapshot):
        if self._running:
            raise ValueError("Concurrent/recursive scan denied")
        self._running = True
        try:
            return await self._scan(request, snapshot)
        finally:
            self._running = False

    def prepare(self, request, snapshot):
        request = OpportunityRequest.model_validate_json(request.model_dump_json())
        s = ScanSnapshot.model_validate_json(snapshot.model_dump_json())
        at, policy = s.captured_at, self.policy
        if s.data_mode != "DEMO" and request.demo_scenario is not None:
            raise ValueError("No DEMO fallback for a real scan")
        tokens = sorted(s.tokens, key=lambda t: (*identity(t), fingerprint(t)))
        s = ScanSnapshot.model_validate(
            {
                **s.model_dump(),
                "tokens": tuple(tokens),
                "assets": tuple(sorted(s.assets, key=lambda a: (a.ticker, fingerprint(a)))),
                "assessments": tuple(
                    sorted(
                        (
                            type(a).model_validate(
                                {
                                    **a.model_dump(),
                                    "representations": sorted(
                                        a.representations,
                                        key=lambda r: (r.ticker, r.issuer, r.chain_id, r.contract),
                                    ),
                                }
                            )
                            for a in s.assessments
                        ),
                        key=lambda a: (a.ticker or "", str(a.assessment_id)),
                    )
                ),
                "articles": tuple(
                    sorted(
                        (
                            a
                            for a in s.articles
                            if a.published_timestamp <= at and a.ingestion_timestamp <= at
                        ),
                        key=fingerprint,
                    )
                ),
                "research": tuple(
                    type(r).model_validate(
                        {
                            **r.model_dump(),
                            "episodes": tuple(
                                e
                                for e in r.episodes
                                if e.decision.decision_at < at
                                and e.target.available_at is not None
                                and e.target.available_at <= at
                                and e.target.completed_at <= at
                            ),
                        }
                    )
                    for r in s.research
                ),
            }
        )
        counts = Counter((t.chain_id, t.contract) for t in tokens)
        duplicate_counts = Counter()
        entries, downstream, refs, assessments = [], {}, [], {}
        bound = (
            len(tokens) + len(s.catalog_rejections) > policy.max_representations
            or len({t.ticker for t in tokens}) > policy.max_stocks
        )
        discovery_ref = reference(
            {"digest": s.discovery_digest, "source": s.discovery_source},
            mode=s.data_mode,
            source=s.discovery_source,
            at=at,
        )
        for token in tokens:
            cid = candidate_id(token)
            if counts[(token.chain_id, token.contract)] > 1:
                duplicate_counts[cid] += 1
                cid = fingerprint((cid, duplicate_counts[cid]))
            assessment = next(
                (
                    a
                    for a in s.assessments
                    if any(
                        (r.ticker, r.issuer, r.chain_id, r.contract) == identity(token)
                        for r in a.representations
                    )
                ),
                None,
            )
            ref = reference(
                {
                    "token": token.model_dump(mode="json"),
                    "trust": assessment.model_dump(mode="json") if assessment else None,
                    "costs": s.costs[candidate_id(token)].model_dump(mode="json")
                    if candidate_id(token) in s.costs
                    else None,
                    "risk": s.risk_context.model_dump(mode="json") if s.risk_context else None,
                },
                mode=s.data_mode,
                source="DETERMINISTIC_SCAN_EVIDENCE",
                at=at,
            )
            refs.append(ref)
            c, reasons, d = self.generate(token, cid, assessment, request, s, ref)
            if bound:
                reasons.append("UNIVERSE_BOUND_EXCEEDED")
            if counts[(token.chain_id, token.contract)] > 1:
                reasons.append("DUPLICATE_REPRESENTATION")
            reasons = tuple(sorted(set(reasons)))
            c = Candidate.model_validate(
                {
                    **c.model_dump(),
                    "eligibility": "REJECTED" if reasons else "ELIGIBLE",
                    "rejection_reasons": reasons,
                    "risk_flags": reasons,
                }
            )
            if not reasons:
                reasons = rejection(c, at)
                if reasons:
                    c = Candidate.model_validate(
                        {
                            **c.model_dump(),
                            "eligibility": "REJECTED",
                            "rejection_reasons": reasons,
                            "risk_flags": reasons,
                        }
                    )
            entries.append(
                CandidateAudit(
                    candidate=c,
                    inclusion="EXCLUDED" if request.universe.reasons(token) else "INCLUDED",
                    rejection_reasons=reasons,
                )
            )
            if d:
                downstream[cid] = d
            if assessment:
                assessments[cid] = assessment
        # Every representation is retained. Only eligible same-stock representations reach
        # the shared issuer router; its selection is authoritative for representation economics.
        for ticker in sorted({e.candidate.ticker for e in entries}):
            group = [e for e in entries if e.candidate.ticker == ticker and not e.rejection_reasons]
            if not group:
                continue
            route_inputs = []
            for entry in group:
                cid = entry.candidate.candidate_id
                if cid in downstream:
                    route_inputs.append(downstream[cid][3])
                elif cid in s.routes:
                    route_inputs.append(s.routes[cid])
            notional = group[0].candidate.proposed_notional_usd
            if len(route_inputs) != len(group) or any(
                e.candidate.proposed_notional_usd != notional for e in group
            ):
                entries = self.reject(
                    entries,
                    {e.candidate.candidate_id for e in group},
                    "ROUTE_INPUT_OR_SIZE_UNAVAILABLE",
                )
                continue
            route = self.router.decide(
                ticker,
                notional,
                route_inputs,
                mode="DEMO" if s.data_mode == "DEMO" else "LIVE",
                now=at,
                policy=opportunity_policy(s.demo_risk_policy)
                if s.demo_risk_policy
                else RoutePolicy(
                    purpose="OPPORTUNITY",
                    require_costs=True,
                    require_liquidity=True,
                    require_trust=True,
                    require_risk=True,
                    min_liquidity_usd=policy.min_liquidity_usd,
                    max_slippage_bps=policy.max_slippage_bps,
                ),
            )
            selected = route.selected_representation
            updates = []
            for entry in entries:
                if entry not in group:
                    updates.append(entry)
                    continue
                c = entry.candidate
                matches = selected and (
                    selected.underlying,
                    selected.issuer,
                    selected.chain_id,
                    selected.contract,
                ) == (c.ticker, c.issuer, c.chain_id, c.contract)
                reasons = (
                    () if matches else ("ROUTE_SUPERSEDED" if selected else "NO_ELIGIBLE_ROUTE",)
                )
                candidate = Candidate.model_validate(
                    {
                        **c.model_dump(),
                        "eligibility": "ELIGIBLE" if matches else "REJECTED",
                        "risk_flags": reasons,
                        "rejection_reasons": reasons,
                    }
                )
                updates.append(
                    CandidateAudit(
                        candidate=candidate,
                        inclusion=entry.inclusion,
                        rejection_reasons=reasons,
                        route=route,
                    )
                )
                if c.candidate_id in downstream:
                    downstream[c.candidate_id] = (
                        *downstream[c.candidate_id][:2],
                        route,
                        downstream[c.candidate_id][3],
                    )
            entries = updates
        # One rank policy for deterministic full-universe reduction and the existing interpreter.
        ordered = ranked(tuple(e.candidate for e in entries), at)
        ranks = {c.candidate_id: index for index, c in enumerate(ordered, 1)}
        top = tuple(ordered[: min(policy.top_k, self.agents.policy.top_k)])
        entries = tuple(
            CandidateAudit.model_validate(
                {
                    **e.model_dump(),
                    "rank": ranks.get(e.candidate.candidate_id),
                    "agent_selected": e.candidate in top,
                }
            )
            for e in entries
        )
        run_id = fingerprint(
            {
                "request": request.model_dump(mode="json"),
                "snapshot": s.model_dump(mode="json"),
                "policy": policy.model_dump(mode="json"),
                "candidates": [e.model_dump(mode="json") for e in entries],
            }
        )
        correlation = request.correlation_id or run_id
        blockers = list(s.blockers)
        if s.data_mode != "DEMO":
            blockers.append("PRODUCTION_OPPORTUNITY_GATE_BLOCKED_BY_TRUST")
        if not top:
            blockers.extend(
                sorted({r for e in entries for r in e.rejection_reasons if r in CRITICAL})
            )
        action = (
            "DEFER"
            if blockers or any(CRITICAL.intersection(e.rejection_reasons) for e in entries)
            else "NO_QUALIFYING_OPPORTUNITY"
        )
        return (
            request,
            s,
            entries,
            top,
            downstream,
            refs,
            assessments,
            discovery_ref,
            run_id,
            correlation,
            blockers,
            action,
        )

    async def _scan(self, request, snapshot):
        (
            request,
            s,
            entries,
            top,
            downstream,
            refs,
            assessments,
            discovery_ref,
            run_id,
            correlation,
            blockers,
            action,
        ) = await asyncio.to_thread(self.prepare, request, snapshot)
        at, policy, mandate = s.captured_at, self.policy, request.mandate()
        agent_run, selected, risk_status = None, None, "UNAVAILABLE"
        # NO Opportunity/LLM call before ALL deterministic filtering/routing and top-K.
        if top and not blockers:
            bundle = self.bundle(top, assessments, downstream, s, refs, discovery_ref, run_id)
            text = (
                f"I have ${mandate.budget_usd} and risk budget ${mandate.risk_budget_usd}; "
                "find me an opportunity "
                + (
                    "before Monday."
                    if mandate.time_window == "BEFORE_MONDAY"
                    else "before US market opens."
                )
            )
            agent_run = await self.agents.analyze(text, bundle, correlation_id=correlation)
            action = agent_run.decision.decision
            selected = next(
                (c for c in top if c.candidate_id == agent_run.decision.candidate_id), None
            )
            if action == "BUY" and selected:
                # Final deterministic revalidation AFTER interpretation; agents cannot approve risk.
                decision, inputs, _, _ = downstream[selected.candidate_id]
                final_risk = self.risk.evaluate(decision, inputs, s.demo_risk_policy, now=at)
                risk_status = final_risk.status
                if risk_status != "PASS":
                    action = "DEFER"
                    blockers.append("FINAL_RISK_REJECTED")
            if action == "DEFER":
                blockers.extend(agent_run.decision.reasons)
        rejections = Counter(r for e in entries for r in e.rejection_reasons)
        rejections.update(r.reason for r in s.catalog_rejections)
        result = OpportunityScan(
            run_id=run_id,
            decision_id="decision:" + run_id,
            correlation_id=correlation,
            timestamp=at,
            data_mode=s.data_mode,
            mandate=mandate,
            policy=policy,
            universe_count=len(entries) + len(s.catalog_rejections),
            eligible_count=sum(e.candidate.eligibility == "ELIGIBLE" for e in entries),
            rejected_count=sum(e.candidate.eligibility != "ELIGIBLE" for e in entries)
            + len(s.catalog_rejections),
            candidates=entries,
            catalog_rejections=s.catalog_rejections,
            top_k=top,
            selected_candidate=selected,
            final_action=action,
            blockers=tuple(sorted(set(blockers))),
            rejection_counts=dict(sorted(rejections.items())),
            provenance=(discovery_ref, *refs),
            agent_run=agent_run,
            risk_validation=risk_status,
        )
        if self.store:
            self.store.save(result)
        LOGGER.info(
            "CANDIDATE_SCAN",
            extra={
                "event_fields": {
                    "run_id": run_id,
                    "decision_id": result.decision_id,
                    "correlation_id": correlation,
                    "universe_count": result.universe_count,
                    "eligible_count": result.eligible_count,
                    "action": result.final_action,
                    "data_mode": s.data_mode,
                }
            },
        )
        return result

    @staticmethod
    def reject(entries, ids, code):
        rows = []
        for entry in entries:
            if entry.candidate.candidate_id in ids:
                reasons = (*entry.rejection_reasons, code)
                c = Candidate.model_validate(
                    {
                        **entry.candidate.model_dump(),
                        "eligibility": "REJECTED",
                        "risk_flags": reasons,
                        "rejection_reasons": reasons,
                    }
                )
                entry = CandidateAudit(
                    candidate=c, inclusion=entry.inclusion, rejection_reasons=reasons
                )
            rows.append(entry)
        return rows

    def generate(self, token, cid, assessment, request, s, ref):
        at, policy = s.captured_at, self.policy
        reasons = list(request.universe.reasons(token))
        rep = (
            next(
                (
                    r
                    for r in assessment.representations
                    if (r.ticker, r.issuer, r.chain_id, r.contract) == identity(token)
                ),
                None,
            )
            if assessment
            else None
        )
        values = dict(
            candidate_id=cid,
            ticker=token.ticker,
            issuer=token.platform_id,
            chain_id=token.chain_id,
            contract=token.contract,
            company=token.company_name[:160],
            token=token.token_symbol,
            token_to_share_ratio=token.token_to_share_ratio,
            data_mode=s.data_mode,
            observed_at=rep.token_timestamp if rep and rep.token_timestamp else at,
            available_at=at,
            trust=rep.classification if rep else "INSUFFICIENT_EVIDENCE",
            eligibility="UNAVAILABLE",
            evidence_refs=(ref.evidence_id,),
            tradable=token.open_state,
        )
        if token.asset_type != 1:
            reasons.append("UNSUPPORTED_ASSET_TYPE")
        if not any(a.ticker == token.ticker and a.supported for a in s.assets):
            reasons.append("MAPPING_UNRESOLVED")
        if (
            token.reason_code
            in {"ASSET_PAUSED", "ASSET_LIMITED", "UNSUPPORTED", "MARKET_MAINTENANCE"}
            or token.open_state is not True
            or token.market_state not in {"regular", "premarket", "postmarket"}
        ):
            reasons.append("REPRESENTATION_RESTRICTED")
        if token.ingestion_timestamp > at:
            reasons.append("FUTURE_METADATA")
        if s.data_mode != "DEMO" and (
            token.source.startswith("DEMO")
            or token.contract.startswith("demo:")
            or token.chain_id == "DEMO"
        ):
            reasons.append("SYNTHETIC_INPUT_IN_LIVE")
        if rep is None or assessment is None:
            reasons.append("TRUST_UNAVAILABLE")
            return Candidate(**values), reasons, None
        f, eq = rep.features, rep.reference.observation
        regime = assessment.regime.baseline_bucket if assessment.regime else None
        values.update(
            token_price_usd=rep.token_price_usd,
            confidence=rep.confidence,
            regime=regime,
            deviation=f.deviation if f else None,
            volume_percentile=rep.baseline.volume_percentile,
            volume_usd=rep.liquidity.volume_24h_usd,
            liquidity_usd=rep.liquidity.liquidity_usd,
            liquidity_state=rep.liquidity.status,
            persistence_seconds=f.persistence_seconds if f else None,
            news_state=rep.news.state,
            baseline_samples=rep.baseline.sample_count,
            analogue_count=rep.analogues.retrieved_sample_count,
            source_timestamps={
                "TOKEN": rep.token_timestamp,
                "RATIO": rep.ratio_source_timestamp,
                "RATIO_RECEIPT": rep.ratio_observed_at,
                "EQUITY": eq.source_timestamp if eq else None,
                "LIQUIDITY": rep.liquidity.observed_at,
                "TRUST": assessment.evaluated_at,
            },
        )
        if rep.token_to_share_ratio != token.token_to_share_ratio:
            reasons.append("TOKEN_SHARE_RATIO_CONFLICT")
        if not fresh(rep.ratio_observed_at, at):
            reasons.append("STALE_RATIO_METADATA")
        if rep.token_price_usd is None:
            reasons.append("TOKEN_PRICE_UNAVAILABLE")
        if not fresh(rep.token_timestamp, at):
            reasons.append("STALE_TOKEN_PRICE")
        if (
            assessment.evaluated_at > at
            or not fresh(assessment.evaluated_at, at)
            or (f and (not fresh(f.asof, at) or f.available_at > at))
        ):
            reasons.append("STALE_OR_FUTURE_TRUST")
        if rep.reference.status != "AVAILABLE" or eq is None or eq.price is None:
            reasons.append("INDEPENDENT_EQUITY_UNAVAILABLE")
        elif (
            eq.source.startswith("BINANCE")
            or eq.data_mode != ("DEMO" if s.data_mode == "DEMO" else "LIVE")
            or eq.ingestion_timestamp > at
        ):
            reasons.append("INDEPENDENT_EQUITY_CONFLICT")
        else:
            values.update(
                independent_equity_price_usd=eq.price, independent_equity_source=eq.source
            )
            if regime == "REGULAR":
                if (
                    eq.kind not in {"QUOTE", "SNAPSHOT"}
                    or eq.data_quality not in {"LIVE", "DEMO"}
                    or not fresh(eq.source_timestamp, at)
                ):
                    reasons.append("STALE_INDEPENDENT_EQUITY")
                if (
                    rep.token_timestamp is None
                    or eq.source_timestamp is None
                    or abs((rep.token_timestamp - eq.source_timestamp).total_seconds()) > 30
                ):
                    reasons.append("TOKEN_EQUITY_TIMESTAMP_SKEW")
            elif (
                eq.kind != "REGULAR_CLOSE"
                or eq.interval != "1minute"
                or eq.data_quality not in {"HISTORICAL", "DEMO"}
                or eq.source_timestamp is None
                or not assessment.regime
                or eq.source_timestamp + timedelta(minutes=1)
                != assessment.regime.previous_regular_close
                or rep.reference.reference_asof != assessment.regime.previous_regular_close
            ):
                reasons.append("PREVIOUS_REGULAR_CLOSE_UNVERIFIED")
        allowed_premarket = (
            regime == "PREMARKET"
            and assessment.regime
            and (assessment.regime.reopening or assessment.regime.multi_day_closure)
        )
        if (
            regime not in {"REGULAR", "WEEKEND_PREOPEN", "MULTI_DAY_REOPEN"}
            and not allowed_premarket
        ):
            reasons.append("RESTRICTED_MARKET_REGIME")
        if regime == "REGULAR" and s.data_mode != "DEMO":
            reasons.append("PREOPEN_WINDOW_NOT_ACTIVE")
        if rep.classification != "LIKELY_INFORMATION":
            reasons.append("TRUST_NOT_LIKELY_INFORMATION")
        if (
            f is None
            or rep.missing_evidence
            or rep.baseline.status != "SUFFICIENT"
            or rep.baseline.sample_count < 30
            or rep.analogues.status != "SUFFICIENT"
            or rep.analogues.retrieved_sample_count < 3
        ):
            reasons.append("TRUST_EVIDENCE_INSUFFICIENT")
        if (
            rep.liquidity.status != "AVAILABLE"
            or rep.liquidity.liquidity_usd is None
            or not fresh(rep.liquidity.observed_at, at)
            or not rep.liquidity.source
        ):
            reasons.append("LIQUIDITY_UNAVAILABLE")
        elif rep.liquidity.liquidity_usd < policy.min_liquidity_usd:
            reasons.append("INSUFFICIENT_LIQUIDITY")
        if s.risk_context:
            floor = rep.baseline.liquidity
            minimum = floor.quantiles.get("50") if floor else None
            if minimum is None or rep.liquidity.liquidity_usd is None:
                reasons.append("LIQUIDITY_PERCENTILE_UNAVAILABLE")
            elif rep.liquidity.liquidity_usd < max(minimum, s.risk_context.min_liquidity_usd):
                reasons.append("INSUFFICIENT_LIQUIDITY")
            tiers = {None: -1, "LOW": 0, "MEDIUM": 1, "HIGH": 2}
            if tiers[rep.confidence] < tiers[s.risk_context.min_confidence]:
                reasons.append("CONFIDENCE_MINIMUM")
        if (
            rep.news.coverage != "COMPLETE_REQUESTED_WINDOW"
            or rep.news.state != "CORROBORATING"
            or any(
                t > at for t in (*rep.news.published_timestamps, *rep.news.first_seen_timestamps)
            )
        ):
            reasons.append("NEWS_UNAVAILABLE_OR_UNALIGNED")
        if f and eq and eq.price and rep.token_price_usd:
            comparison = comparable_economics(
                rep.token_price_usd, token.token_to_share_ratio, eq.price
            )
            values["effective_cost"] = comparison["effective_price_per_share_usd"]
            if (
                comparison["deviation"] != f.deviation
                or comparison["effective_price_per_share_usd"] != f.effective_price_per_share_usd
            ):
                reasons.append("SOURCE_EVIDENCE_CONFLICT")
        costs = s.costs.get(candidate_id(token))
        if costs is None or not fresh(costs.observed_at, at) or costs.available_at > at:
            reasons.append("MISSING_CRITICAL_COSTS")
        else:
            values.update(
                slippage_bps=costs.slippage_bps,
                fees_usd=costs.fees_usd,
                gas_usd=costs.gas_usd,
                execution_buffer_usd=costs.execution_buffer_usd,
            )
            values["source_timestamps"]["COSTS"] = costs.observed_at
            if costs.slippage_bps > min(
                policy.max_slippage_bps,
                s.risk_context.max_slippage_bps if s.risk_context else policy.max_slippage_bps,
            ):
                reasons.append("EXCESSIVE_SLIPPAGE")
            if not costs.route_available:
                reasons.append("ROUTE_UNAVAILABLE")
        size, stress, risk_reasons = self.risk.size_opportunity(
            request.mandate(),
            s.risk_context,
            costs,
            rep.liquidity.liquidity_usd,
            now=at,
            mode=s.data_mode,
        )
        reasons.extend(risk_reasons)
        values.update(
            proposed_notional_usd=size,
            stress_loss_usd=stress,
            stress_adverse_move_fraction=s.risk_context.stress_adverse_move_fraction
            if s.risk_context
            else None,
        )
        target = None
        research = next(
            (
                r
                for r in s.research
                if (r.current.ticker, r.current.issuer, r.current.chain_id, r.current.contract)
                == identity(token)
            ),
            None,
        )
        if regime in {"WEEKEND_PREOPEN", "MULTI_DAY_REOPEN", "PREMARKET"}:
            if research and research.current.decision_at == at and research.current.trust == rep:
                retrieval = HistoricalRetrieval(research.current.policy).evaluate(
                    research.episodes, research.current
                )
                prediction = RollingOpeningModel(research.current.policy).predict(
                    research.episodes, research.current
                )
                values.update(
                    prediction_status=prediction.status,
                    predicted_open_return=prediction.predicted_return,
                    prediction_samples=prediction.sample_count,
                    prediction_interval_low=prediction.interval_low,
                    prediction_interval_high=prediction.interval_high,
                    historical_pattern=retrieval.historical_pattern,
                )
                if (
                    prediction.status == "READY"
                    and prediction.sample_count >= 30
                    and retrieval.retrieved_count >= 3
                    and eq
                    and eq.price
                ):
                    with localcontext() as context:
                        context.prec = 256
                        target = eq.price * (1 + prediction.predicted_return)
                    values["economics_basis"] = "OPENING_MODEL"
                else:
                    reasons.append("PREDICTION_INSUFFICIENT")
            else:
                reasons.append("PREDICTION_INSUFFICIENT")
        elif s.data_mode == "DEMO" and s.demo_economics:
            target = s.demo_economics.target_share_price_usd
            values["economics_basis"] = "SYNTHETIC_SCENARIO"
        if target and target > 0 and values.get("effective_cost") and size and costs:
            _, _, gross, slip, net = analytical_edge(
                effective=values["effective_cost"],
                target=target,
                notional=size,
                slippage_bps=costs.slippage_bps,
                fees=costs.fees_usd,
                gas=costs.gas_usd,
                buffer=costs.execution_buffer_usd,
            )
            values.update(
                gross_expected_edge_usd=gross, estimated_slippage_usd=slip, net_edge_usd=net
            )
            if net < max(
                policy.min_net_edge_usd,
                s.risk_context.min_net_edge_usd if s.risk_context else policy.min_net_edge_usd,
            ):
                reasons.append("NET_EDGE_BELOW_MINIMUM")
        else:
            reasons.append("EXPECTED_ECONOMICS_UNAVAILABLE")
        downstream = None
        if (
            not reasons
            and s.data_mode == "DEMO"
            and regime == "REGULAR"
            and all(
                v is not None for v in (s.demo_economics, s.demo_risk_inputs, s.demo_risk_policy)
            )
        ):
            inputs = OpportunityInputs.model_validate(
                {
                    **s.demo_economics.model_dump(),
                    "ticker": token.ticker,
                    "issuer": token.platform_id,
                    "chain_id": token.chain_id,
                    "contract": token.contract,
                    "requested_notional_usd": size,
                    "target_share_price_usd": target,
                    "slippage_bps": costs.slippage_bps,
                    "fees_usd": costs.fees_usd,
                    "gas_usd": costs.gas_usd,
                    "execution_buffer_usd": costs.execution_buffer_usd,
                    "observed_at": costs.observed_at,
                }
            )
            opportunity = self.economics.evaluate(assessment, rep, token, inputs, now=at)
            stable = fingerprint(
                {
                    "candidate": cid,
                    "inputs": inputs.model_dump(mode="json"),
                    "mandate": request.mandate().model_dump(mode="json"),
                    "assessment_id": str(assessment.assessment_id),
                }
            )
            opportunity = type(opportunity).model_validate(
                {
                    **opportunity.model_dump(),
                    "opportunity_id": uuid5(NAMESPACE_URL, "phase7-opportunity:" + stable),
                }
            )
            risk_inputs = RiskInputs.model_validate(
                {
                    **s.demo_risk_inputs.model_dump(),
                    "budget_usd": request.budget_usd,
                    "risk_budget_usd": request.risk_budget_usd,
                }
            )
            risk = self.risk.evaluate(opportunity, risk_inputs, s.demo_risk_policy, now=at)
            risk = type(risk).model_validate(
                {**risk.model_dump(), "risk_id": uuid5(NAMESPACE_URL, "phase7-risk:" + stable)}
            )
            if risk.status != "PASS":
                reasons.append("DETERMINISTIC_RISK_REJECTED")
            # Preserve exact downstream amounts (existing engine rounds at 18dp explicitly).
            if opportunity.economics:
                values["effective_cost"] = opportunity.economics.effective_price_per_share_usd
                values["net_edge_usd"] = opportunity.economics.net_hypothetical_edge_usd
                values["gross_expected_edge_usd"] = (
                    opportunity.economics.gross_hypothetical_edge_usd
                )
            price = TokenObservation(
                source="CAPTURED_DEMO_TRUST",
                provider_identifier=cid,
                source_timestamp=rep.token_timestamp,
                ingestion_timestamp=at,
                data_mode="DEMO",
                data_quality="DEMO",
                ticker=token.ticker,
                issuer=token.platform_id,
                chain_id=token.chain_id,
                contract=token.contract,
                token_symbol=token.token_symbol,
                token_to_share_ratio=token.token_to_share_ratio,
                token_price=rep.token_price_usd,
            )
            route_input = opportunity_input(token, price, assessment, opportunity, risk, inputs)
            downstream = (opportunity, risk_inputs, None, route_input)
        if s.data_mode != "DEMO":
            reasons.append("PRODUCTION_OPPORTUNITY_GATE_BLOCKED_BY_TRUST")
        return Candidate(**values), reasons, downstream

    def bundle(self, top, assessments, downstream, s, refs, discovery_ref, run_id):
        relevant = [assessments[c.candidate_id] for c in top]
        first = relevant[0]
        if any(a.regime != first.regime for a in relevant):
            raise ValueError("Mixed market regimes in top-K evidence")
        assessment_id = uuid5(NAMESPACE_URL, "scan-trust:" + run_id)
        assessment = TrustAssessment(
            assessment_id=assessment_id,
            run_id=run_id,
            request_id=run_id,
            correlation_id=run_id,
            data_mode=first.data_mode,
            evaluated_at=s.captured_at,
            ticker=None,
            status="ASSESSED",
            regime=first.regime,
            representations=[
                next(
                    r
                    for r in assessments[c.candidate_id].representations
                    if (r.ticker, r.issuer, r.chain_id, r.contract)
                    == (c.ticker, c.issuer, c.chain_id, c.contract)
                )
                for c in top
            ],
            limitations=["BOUNDED_FULL_UNIVERSE_PROJECTION", "NO_EXECUTION_AUTHORITY"],
        )
        ds = []
        for c in top:
            if c.candidate_id in downstream:
                opportunity, risk_inputs, route, _ = downstream[c.candidate_id]
                opportunity = type(opportunity).model_validate(
                    {**opportunity.model_dump(), "trust_assessment_id": assessment_id}
                )
                risk = self.risk.evaluate(
                    opportunity, risk_inputs, s.demo_risk_policy, now=s.captured_at
                )
                risk = type(risk).model_validate(
                    {**risk.model_dump(), "risk_id": route.selected_candidate.inputs.risk_id}
                )
                ds.append(
                    DownstreamEvidence(
                        candidate_id=c.candidate_id, opportunity=opportunity, route=route, risk=risk
                    )
                )
        article_ids = {i for r in assessment.representations for i in r.news.article_ids}
        articles = tuple(
            a
            for a in s.articles
            if a.provider_identifier in article_ids
            and a.ticker in {c.ticker for c in top}
            and a.published_timestamp <= s.captured_at
            and a.ingestion_timestamp <= s.captured_at
        )
        if len(articles) > 50:
            raise ValueError("Bounded news projection required")
        ids = {r for c in top for r in c.evidence_refs}
        return EvidenceBundle(
            data_mode=s.data_mode,
            decision_at=s.captured_at,
            assessment=assessment,
            assets=tuple(a for a in s.assets if a.ticker in {c.ticker for c in top}),
            articles=articles,
            candidates=top,
            references=(discovery_ref, *(r for r in refs if r.evidence_id in ids)),
            research=tuple(
                r
                for r in s.research
                if (r.current.ticker, r.current.issuer, r.current.chain_id, r.current.contract)
                in {(c.ticker, c.issuer, c.chain_id, c.contract) for c in top}
            ),
            downstream=tuple(ds),
        )
