"""Structured source-journal projections. No raw instructions, secrets or hidden reasoning."""

import re

from app.models.portfolio import portfolio_fingerprint
from app.models.scorecard import AuditEvent, DecisionTrace, TraceStage
from app.repositories.scorecard import identity

STAGES = (
    "INPUT",
    "DATA_FETCH",
    "ASSET_DISCOVERY",
    "NORMALIZATION",
    "FEATURE_CALCULATION",
    "TRUST",
    "AGENT_RUN",
    "CANDIDATE_SCAN",
    "DECISION",
    "ROUTE",
    "RISK",
    "QUOTE",
    "BUILD",
    "SIMULATION",
    "APPROVAL",
    "EXECUTION",
    "POSITION",
    "EXIT",
    "OUTCOME",
    "SCORECARD",
)


def stage(event_type):
    if event_type.startswith("RISK_"):
        return "RISK"
    if event_type.startswith("SIMULATION"):
        return "SIMULATION"
    if event_type.startswith("EXECUTION"):
        return "EXECUTION"
    if event_type == "NO_ACTION":
        return "DECISION"
    return event_type


def safe_record(value, secrets=()):
    text = value.model_dump_json()
    if any(s in text for s in secrets if s):
        raise ValueError("Sensitive analytical source refused")
    forbidden = {
        "chainofthought",
        "hiddenreasoning",
        "reasoningsummary",
        "privatekey",
        "seedphrase",
        "apikey",
        "secretkey",
        "authorization",
        "usersignature",
        "typeddatatosign",
        "calldata",
    }

    def visit(v, depth=0):
        if depth > 30:
            raise ValueError("Audit projection depth exceeded")
        if isinstance(v, dict):
            if any(re.sub(r"[^a-z]", "", k.lower()) in forbidden for k in v):
                raise ValueError("Forbidden audit material")
            for item in v.values():
                visit(item, depth + 1)
        elif isinstance(v, (list, tuple)):
            if len(v) > 2000:
                raise ValueError("Audit projection bound exceeded")
            for item in v:
                visit(item, depth + 1)
        elif isinstance(v, str):
            if len(v) > 2000 or re.search(
                r"(?i)(bearer\s+|(?:api[_-]?key|secret|password|private[_-]?key|seed)\s*[:=])", v
            ):
                raise ValueError("Unsafe audit summary")

    visit(value.model_dump(mode="json"))


class AuditService:
    def __init__(self, store, *, clock, secrets=()):
        self.store, self.clock, self.secrets = store, clock, secrets

    def event(
        self,
        card,
        kind,
        at,
        status,
        source,
        payload,
        *,
        inputs=None,
        outputs=None,
        reasons=(),
        execution_id=None,
    ):
        event = AuditEvent(
            event_id="pending",
            data_mode=card.data_mode,
            decision_id=card.decision_id,
            run_id=card.run_id,
            episode_id=card.episode_id,
            correlation_id=card.correlation_id,
            ticker=card.ticker,
            timestamp=at,
            recorded_at=self.clock(),
            event_type=kind,
            actor="STRUCTURED_AGENT"
            if kind == "AGENT_RUN"
            else "EVALUATOR"
            if kind == "SCORECARD"
            else "DETERMINISTIC_BACKEND",
            source=source,
            source_digest=portfolio_fingerprint(payload),
            status=status,
            input_summary=inputs or {},
            output_summary=outputs or {},
            reasons=tuple(dict.fromkeys(reasons)),
            execution_id=execution_id,
        )
        event = event.model_copy(
            update={
                "event_id": portfolio_fingerprint(
                    event.model_dump(exclude={"event_id", "recorded_at"})
                )
            }
        )
        safe_record(event, self.secrets)
        return event

    def trace(self, decision_id, cards, events, context):
        selected = tuple(c for c in cards if c.decision_id == decision_id)
        if not selected:
            raise LookupError("Unknown mode-scoped decision")
        ids = {i for c in selected for i in c.event_ids}
        found = sorted((e for e in events if e.event_id in ids), key=self.order)
        if ids != {e.event_id for e in found}:
            raise ValueError("Incomplete decision audit references")
        groups = tuple(
            TraceStage(
                stage=s,
                status="RECORDED"
                if any(stage(e.event_type) == s for e in found)
                else "UNAVAILABLE_OR_NOT_APPLICABLE",
                event_ids=tuple(e.event_id for e in found if stage(e.event_type) == s),
            )
            for s in STAGES
        )
        return DecisionTrace(
            **context,
            decision_id=decision_id,
            stages=groups,
            events=tuple(found),
            scorecards=selected,
            complete_for_recorded_scope=all(
                any(stage(e.event_type) == s for e in found)
                for s in ("INPUT", "DECISION", "OUTCOME", "SCORECARD")
            ),
        )

    @staticmethod
    def order(event):
        key = stage(event.event_type)
        return event.timestamp, STAGES.index(key) if key in STAGES else len(STAGES), event.event_id

    def append(self, cards, events):
        for value in (*cards, *events):
            safe_record(value, self.secrets)
        self.store.append(cards, events)

    @staticmethod
    def evaluation_id(card):
        return portfolio_fingerprint(card.model_dump(exclude={"evaluation_id", "recorded_at"}))

    @staticmethod
    def semantic_identity(value):
        return identity(value)
