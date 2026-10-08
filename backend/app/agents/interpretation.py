"""Permit grounded interpretation/salience, never modifications of authoritative facts."""

from app.agents.schemas import InterpretationClaim


def allowed_claims(response):
    conclusions = ["NO_EXECUTION_AUTHORITY"]
    if response.status == "OK":
        conclusions.append("SUPPORTS_ANALYSIS")
    if response.limitations:
        conclusions.append("LIMITS_ANALYSIS")
    if response.status != "OK":
        conclusions.append("REQUIRES_ABSTENTION")
    if response.conflicts:
        conclusions.append("CONFLICTING_EVIDENCE")
    return tuple(
        InterpretationClaim(evidence_ref=ref, conclusion=conclusion)
        for ref in response.evidence_refs
        for conclusion in conclusions
    )


def validated_interpretation(canonical, parsed):
    """All provenance, enums, economics, status, confidence and decisions stay fixed.

    An interpreter may select/order grounded claims and existing opportunity strengths/
    weaknesses. Claims have a controlled vocabulary, so they cannot smuggle invented
    financial prose/tickers into an otherwise strictly typed output.
    """
    allowed = {(c.evidence_ref, c.conclusion) for c in allowed_claims(canonical)}
    selected = [(c.evidence_ref, c.conclusion) for c in parsed.reasoning_summary]
    if len(set(selected)) != len(selected) or not set(selected).issubset(allowed):
        raise ValueError("Ungrounded or duplicate interpretation")
    left, right = (
        canonical.model_dump(exclude={"reasoning_summary"}),
        parsed.model_dump(exclude={"reasoning_summary"}),
    )
    if canonical.agent == "OPPORTUNITY":
        for name in ("strengths", "weaknesses"):
            proposed, original = right["output"][name], left["output"][name]
            if len(set(proposed)) != len(proposed) or not set(proposed).issubset(original):
                raise ValueError("Invented opportunity explanation")
            right["output"][name] = original
    if left != right:
        raise ValueError("Contradictory or invented authoritative fact")
    return parsed
