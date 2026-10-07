"""Traceable evidence confidence; preserves the existing LOW uncalibrated cap."""

from app.agents.schemas import AgentConfidence, ConfidenceFactors


def confidence(bundle, *, disagreement=False):
    reps = bundle.assessment.representations
    at = bundle.decision_at
    stale = any(
        r.features is not None and not 0 <= (at - r.features.asof).total_seconds() <= 120
        for r in reps
    )
    missing = not reps or any(
        r.features is None
        or r.classification == "INSUFFICIENT_EVIDENCE"
        or r.reference.status != "AVAILABLE"
        or r.liquidity.status != "AVAILABLE"
        for r in reps
    )
    factors = ConfidenceFactors(
        data_quality="CONFLICTING"
        if disagreement
        else "STALE"
        if stale
        else "INSUFFICIENT"
        if missing
        else "AVAILABLE",
        baseline_samples=min((r.baseline.sample_count for r in reps), default=0),
        analogue_count=min((r.analogues.retrieved_sample_count for r in reps), default=0),
        model_samples=min((c.prediction_samples for c in bundle.candidates), default=0),
        feature_agreement=bool(reps) and not missing and not stale,
        news_corroboration=bool(reps) and all(r.news.state == "CORROBORATING" for r in reps),
        persistence_supported=bool(reps)
        and all(r.features and r.features.persistence_seconds > 0 for r in reps),
        regime_certain=bundle.assessment.regime is not None,
        agent_disagreement=disagreement,
    )
    sufficient = (
        factors.data_quality == "AVAILABLE"
        and factors.baseline_samples >= 30
        and factors.analogue_count >= 3
        and factors.regime_certain
    )
    # An opening model is additionally required for pre-open interpretations, not regular routing.
    if bundle.assessment.regime and bundle.assessment.regime.state != "REGULAR":
        sufficient &= factors.model_samples >= 30
    return AgentConfidence(
        evidence_status="CONFLICTING"
        if disagreement
        else "SUPPORTED"
        if sufficient
        else "INSUFFICIENT",
        factors=factors,
        reasons=(
            "UNCALIBRATED_EXISTING_LOW_CAP",
            "AGENT_DISAGREEMENT"
            if disagreement
            else "EVIDENCE_SUPPORTED"
            if sufficient
            else "MISSING_STALE_OR_INSUFFICIENT_EVIDENCE",
        ),
    )
