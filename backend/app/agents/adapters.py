"""Mode-specific evidence projection; the six interpreters and algorithms are shared."""

from app.agents.schemas import (
    Candidate,
    DownstreamEvidence,
    EvidenceBundle,
    EvidenceRef,
    ResearchInput,
)
from app.models.trust import TrustAssessment
from app.services.demo_opportunity import DemoOpportunityFlow
from app.services.demo_sandbox import DemoTrustSandbox
from app.services.research_episodes import fingerprint


def reference(record, *, mode, source, at):
    digest = fingerprint(record)
    return EvidenceRef(
        evidence_id=f"evidence:{digest}",
        digest=digest,
        data_mode=mode,
        source=source,
        observed_at=at,
        available_at=at,
        synthetic=mode == "DEMO",
    )


def candidate(rep, *, mode, at, ref, opportunity=None, route=None):
    economic = opportunity.economics if opportunity else None
    f = rep.features
    eligible = (
        opportunity is not None
        and opportunity.status == "ACTIONABLE"
        and route is not None
        and route.status == "ROUTE_SELECTED"
    )
    identity = (rep.ticker, rep.issuer, rep.chain_id, rep.contract)
    return Candidate(
        candidate_id=fingerprint(identity),
        ticker=rep.ticker,
        issuer=rep.issuer,
        chain_id=rep.chain_id,
        contract=rep.contract,
        data_mode=mode,
        observed_at=rep.token_timestamp or at,
        available_at=at,
        trust=rep.classification,
        confidence=rep.confidence,
        deviation=f.deviation if f else None,
        volume_percentile=rep.baseline.volume_percentile,
        effective_cost=f.effective_price_per_share_usd if f else None,
        liquidity_usd=rep.liquidity.liquidity_usd,
        slippage_bps=opportunity.inputs.slippage_bps if opportunity else None,
        net_edge_usd=economic.net_hypothetical_edge_usd if economic else None,
        baseline_samples=rep.baseline.sample_count,
        analogue_count=rep.analogues.retrieved_sample_count,
        eligibility="ELIGIBLE"
        if eligible
        else "UNAVAILABLE"
        if rep.classification == "INSUFFICIENT_EVIDENCE"
        else "REJECTED",
        tradable=route.selected_candidate.inputs.tradable if eligible else None,
        evidence_refs=(ref.evidence_id,),
    )


class DemoEvidenceAdapter:
    """Existing fixtures/services, disposable databases; no new synthetic financial values."""

    def load(self, scenario):
        sandbox = DemoTrustSandbox()
        flow = DemoOpportunityFlow(sandbox, clock=lambda: 0)
        trust = flow.remember(
            sandbox.assess(
                scenario,
                run_id="phase6-demo",
                request_id="phase6-demo",
                correlation_id="phase6-demo",
            )
        )
        opportunity = flow.opportunity(trust.assessment.assessment_id)
        risk = flow.risk(opportunity.opportunity.opportunity_id)
        at = trust.assessment.evaluated_at
        ref = reference(trust.assessment, mode="DEMO", source="EXISTING_DEMO_TRUST", at=at)
        downstream_ref = reference(
            opportunity, mode="DEMO", source="EXISTING_DEMO_OPPORTUNITY", at=at
        )
        risk_ref = reference(risk, mode="DEMO", source="EXISTING_DEMO_RISK", at=at)
        dataset = sandbox.datasets[scenario]
        c = candidate(
            trust.assessment.representations[0],
            mode="DEMO",
            at=at,
            ref=ref,
            opportunity=opportunity.opportunity,
            route=opportunity.route_decision,
        )
        c = Candidate.model_validate(
            {
                **c.model_dump(),
                "evidence_refs": (
                    ref.evidence_id,
                    downstream_ref.evidence_id,
                    risk_ref.evidence_id,
                ),
            }
        )
        return EvidenceBundle(
            data_mode="DEMO",
            decision_at=at,
            assessment=trust.assessment,
            assets=(dataset.asset.record,),
            articles=tuple(r.record for r in trust.news_inputs),
            candidates=(c,),
            references=(ref, downstream_ref, risk_ref),
            downstream=(
                DownstreamEvidence(
                    candidate_id=c.candidate_id,
                    opportunity=opportunity.opportunity,
                    route=opportunity.route_decision,
                    risk=risk.risk,
                ),
            ),
        )


class LiveReadOnlyEvidenceAdapter:
    """Already captured backend evidence only; no network, fake fallback or DEMO risk conversion."""

    def from_assessment(self, assessment, *, assets=(), articles=(), research=()):
        assessment = TrustAssessment.model_validate_json(assessment.model_dump_json())
        if assessment.data_mode != "LIVE":
            raise ValueError("LIVE_READ_ONLY requires real evidence")
        at = assessment.evaluated_at
        ref = reference(assessment, mode="LIVE_READ_ONLY", source="CAPTURED_REAL_TRUST", at=at)
        # No production candidate is silently made eligible before Phase 7/Gate verification.
        return EvidenceBundle(
            data_mode="LIVE_READ_ONLY",
            decision_at=at,
            assessment=assessment,
            assets=tuple(assets),
            articles=tuple(articles),
            research=tuple(research),
            candidates=tuple(
                candidate(r, mode="LIVE_READ_ONLY", at=at, ref=ref)
                for r in assessment.representations
            ),
            references=(ref,),
        )

    def from_replay(self, replay, *, row_index=0):
        if replay.data_mode != "LIVE":
            raise ValueError("Synthetic replay cannot become real agent evidence")
        episode = replay.episodes[row_index]
        d = episode.decision
        # Project decision fields only, never the current episode's future outcome/scorecard.
        assessment = TrustAssessment(
            assessment_id=d.decision_id[:32],
            run_id=replay.run_id,
            request_id="phase6-replay",
            correlation_id="phase6-replay",
            data_mode="LIVE",
            evaluated_at=d.decision_at,
            ticker=d.ticker,
            status="ASSESSED" if d.trust else "UNAVAILABLE",
            regime=None,
            representations=[d.trust] if d.trust else [],
            limitations=["CAPTURED_HISTORICAL_NOT_CURRENT_LIVE"],
        )
        return self.from_assessment(
            assessment, research=(ResearchInput(current=d, episodes=replay.episodes),)
        )
