"""Phase 5 retrieval/model consumer; opening direction is not token reversal evidence."""

import asyncio
from datetime import datetime

from app.agents.schemas import ResearchOutput, ResearchView
from app.services.research_model import HistoricalRetrieval, RollingOpeningModel


class ResearchAgent:
    name = "RESEARCH"

    async def run(self, context, tools, previous):
        inputs, assessment = tools.read("historical_retrieval")
        memory = tools.read("recent_memory")
        views, conflicts, insufficient = [], [], False
        opening_results = []
        if not context.candidates and inputs:
            current = inputs[0]
            retrieval = await asyncio.to_thread(
                HistoricalRetrieval(current.current.policy).evaluate,
                current.episodes,
                current.current,
            )
            prediction = await asyncio.to_thread(
                RollingOpeningModel(current.current.policy).predict,
                current.episodes,
                current.current,
            )
            return (
                "INSUFFICIENT_EVIDENCE",
                ResearchOutput(
                    retrieval_status=retrieval.status,
                    model_status=prediction.status,
                    model_samples=prediction.sample_count,
                    retrieved_analogues=retrieval.retrieved_count,
                ),
                (),
                ("REAL_PHASE_5_EVIDENCE_INSUFFICIENT",),
            )
        for c in context.candidates:
            rep = next(
                r
                for r in assessment.representations
                if (r.ticker, r.issuer, r.chain_id, r.contract)
                == (c.ticker, c.issuer, c.chain_id, c.contract)
            )
            current = next(
                (
                    r
                    for r in inputs
                    if (r.current.ticker, r.current.issuer, r.current.chain_id, r.current.contract)
                    == (c.ticker, c.issuer, c.chain_id, c.contract)
                ),
                None,
            )
            retrieval = prediction = None
            if current:
                retrieval = await asyncio.to_thread(
                    HistoricalRetrieval(current.current.policy).evaluate,
                    current.episodes,
                    current.current,
                )
                prediction = await asyncio.to_thread(
                    RollingOpeningModel(current.current.policy).predict,
                    current.episodes,
                    current.current,
                )
            opening_results.append((retrieval, prediction))
            # Existing Trust episodes measure actual 30-minute token continuation/reversal.
            # Phase 5 opening returns remain separately labeled equity opening direction.
            matches = []
            for m in rep.analogues.matches[:3]:
                try:
                    times = [
                        datetime.fromisoformat(m[k])
                        for k in (
                            "feature_at",
                            "feature_available_at",
                            "completed_at",
                            "outcome_available_at",
                        )
                    ]
                    if (
                        not times[0] <= times[1] < times[2] <= times[3] <= context.at
                        or any(t.tzinfo is None for t in times)
                        or m["evidence_kind"]
                        != ("SYNTHETIC_TEST" if context.mode == "DEMO" else "LOCAL_OBSERVATIONS")
                        or m["outcome"] not in {"REVERSED", "PERSISTED", "MIXED"}
                    ):
                        continue
                    matches.append(m)
                except (KeyError, TypeError, ValueError):
                    continue
            unique = {m["episode_id"]: m for m in matches}
            pattern = "INSUFFICIENT"
            if rep.analogues.status == "SUFFICIENT" and len(unique) >= 3:
                outcomes = [m["outcome"] for m in unique.values()]
                pattern = (
                    "CONTINUATION"
                    if outcomes.count("PERSISTED") >= 2
                    else "REVERSAL"
                    if outcomes.count("REVERSED") >= 2
                    else "MIXED"
                )
                if "PERSISTED" in outcomes and "REVERSED" in outcomes:
                    conflicts.append("CONFLICTING_HISTORICAL_OUTCOMES")
            phase5_sufficient = (
                retrieval is not None
                and retrieval.status == "SUFFICIENT"
                and prediction is not None
                and prediction.status == "READY"
            )
            # Regular DEMO can explain its supplied Trust analogues without inventing openings.
            regular_demo = (
                context.mode == "DEMO"
                and assessment.regime is not None
                and assessment.regime.state == "REGULAR"
                and pattern != "INSUFFICIENT"
            )
            insufficient |= not phase5_sufficient and not regular_demo
            views.append(
                ResearchView(
                    candidate_id=c.candidate_id,
                    similar_episodes=tuple(m.episode_id for m in retrieval.matches)
                    if retrieval
                    else tuple(sorted(unique)),
                    historical_pattern=pattern,
                    opening_direction=prediction.direction
                    if prediction and prediction.direction
                    else "UNKNOWN",
                    prediction_status=prediction.status if prediction else "NOT_READY",
                    prediction_samples=prediction.sample_count if prediction else 0,
                    priors=current.priors if current else (),
                    memory_ids=tuple(m.memory_id for m in memory if m.stock == c.ticker),
                )
            )
        return (
            "CONFLICT"
            if conflicts
            else "INSUFFICIENT_EVIDENCE"
            if insufficient or not views
            else "OK",
            ResearchOutput(
                views=tuple(views),
                retrieval_status="SUFFICIENT"
                if opening_results
                and all(r is not None and r.status == "SUFFICIENT" for r, _ in opening_results)
                else "INSUFFICIENT_DATA"
                if any(r and r.status == "INSUFFICIENT_DATA" for r, _ in opening_results)
                else "NOT_READY",
                model_status="READY"
                if opening_results
                and all(p is not None and p.status == "READY" for _, p in opening_results)
                else "INSUFFICIENT_DATA"
                if any(p and p.status == "INSUFFICIENT_DATA" for _, p in opening_results)
                else "NOT_READY",
                model_samples=min(
                    (p.sample_count if p else 0 for _, p in opening_results), default=0
                ),
                retrieved_analogues=min(
                    (r.retrieved_count if r else 0 for r, _ in opening_results), default=0
                ),
            ),
            tuple(sorted(set(conflicts))),
            (
                "OPENING_DIRECTION_IS_NOT_TOKEN_REVERSAL",
                "PRIORS_ARE_NOT_LOCAL_MEASUREMENTS",
                "SYNTHETIC_DEMO_IS_NOT_PRODUCTION_EVIDENCE",
            )
            if context.mode == "DEMO"
            else ("OPENING_DIRECTION_IS_NOT_TOKEN_REVERSAL", "PRIORS_ARE_NOT_LOCAL_MEASUREMENTS"),
        )
