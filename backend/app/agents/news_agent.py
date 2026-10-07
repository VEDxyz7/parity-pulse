"""Publication-time corroboration, through the existing deterministic news service."""

from datetime import timedelta

from app.agents.schemas import NewsOutput, NewsView
from app.services.trust_evidence import NewsAlignmentService


class NewsAgent:
    name = "NEWS"

    async def run(self, context, tools, previous):
        articles, assessment = tools.read("news_evidence")
        views, conflicts, abstained = [], [], False
        for c in context.candidates:
            rep = next(
                r
                for r in assessment.representations
                if (r.ticker, r.issuer, r.chain_id, r.contract)
                == (c.ticker, c.issuer, c.chain_id, c.contract)
            )
            company = next((a.company_name for a in context.assets if a.ticker == c.ticker), "")
            evidence = NewsAlignmentService().evaluate(
                articles,
                ticker=c.ticker,
                company=company,
                deviation=rep.features.deviation if rep.features else 0,
                at=context.at,
                mode="DEMO" if context.mode == "DEMO" else "LIVE",
                complete=rep.news.coverage == "COMPLETE_REQUESTED_WINDOW",
                unavailable=rep.news.coverage == "UNAVAILABLE",
            )
            fresh = tuple(
                a
                for a in articles
                if a.provider_identifier in evidence.article_ids
                and context.at - timedelta(seconds=context.policy.news_window_seconds)
                <= a.published_timestamp
                <= context.at
                and a.ingestion_timestamp <= context.at
            )
            unavailable = not fresh or evidence.coverage != "COMPLETE_REQUESTED_WINDOW"
            abstained |= unavailable
            if (
                not unavailable
                and rep.news.state == "CORROBORATING"
                and evidence.directional_state != "CORROBORATING"
            ):
                conflicts.append("NEWS_TRUST_EVIDENCE_DISAGREEMENT")
            if not unavailable and evidence.directional_state == "CONFLICTING":
                conflicts.append("DIRECTIONAL_NEWS_CONFLICT")
            views.append(
                NewsView(
                    candidate_id=c.candidate_id,
                    relevance="UNAVAILABLE"
                    if unavailable
                    else evidence.directional_state
                    if evidence.directional_state != "UNKNOWN"
                    else "RELEVANT",
                    direction="UNKNOWN"
                    if unavailable
                    or evidence.directional_state == "UNKNOWN"
                    or rep.features is None
                    else ("UP" if rep.features.deviation > 0 else "DOWN")
                    if evidence.directional_state == "CORROBORATING"
                    else ("DOWN" if rep.features.deviation > 0 else "UP"),
                    event_type="UNAVAILABLE" if unavailable else "HEADLINE_EVIDENCE",
                    article_ids=tuple(a.provider_identifier for a in fresh)
                    if not unavailable
                    else (),
                    publication_times=tuple(a.published_timestamp for a in fresh)
                    if not unavailable
                    else (),
                )
            )
        return (
            "CONFLICT" if conflicts else "ABSTAIN" if abstained or not views else "OK",
            NewsOutput(views=tuple(views)),
            tuple(sorted(set(conflicts))),
            ("PUBLICATION_AND_FIRST_AVAILABILITY_REQUIRED", "CORROBORATION_NOT_CAUSALITY"),
        )
