"""Closed typed snapshots. No arbitrary tool registration, SQL, transport or execution."""

from collections import Counter
from contextvars import ContextVar

from app.agents.schemas import EvidenceBundle

ALLOWLIST = {
    "INTENT": frozenset({"stock_resolver", "mandate_validator"}),
    "MARKET": frozenset({"market_evidence"}),
    "NEWS": frozenset({"news_evidence"}),
    "RESEARCH": frozenset({"historical_retrieval", "recent_memory"}),
    "OPPORTUNITY": frozenset({"candidate_table"}),
    "DECISION": frozenset({"constraints"}),
}
DEPTH = ContextVar("parity_agent_tool_depth", default=0)


class ToolDenied(ValueError):
    """Sanitized allowlist/budget failure, with no untrusted tool name in the message."""


class AgentTools:
    __slots__ = ("_registry", "_agent")

    def __init__(self, registry, agent):
        self._registry, self._agent = registry, agent

    def read(self, name):
        return self._registry.read(self._agent, name)


class ToolRegistry:
    def __init__(self, bundle, policy, memories=()):
        self._bundle = EvidenceBundle.model_validate_json(bundle.model_dump_json())
        self._policy = policy
        self._memories = tuple(memories)
        self.calls = Counter()

    def for_agent(self, agent):
        if agent not in ALLOWLIST:
            raise ToolDenied("Unknown agent capability")
        return AgentTools(self, agent)

    def read(self, agent, name):
        if name not in ALLOWLIST.get(agent, ()) or DEPTH.get() >= self._policy.max_depth:
            raise ToolDenied("Tool capability/depth denied")
        if (
            sum(self.calls.values()) >= self._policy.max_tool_calls
            or self.calls[agent] >= self._policy.max_tools_per_agent
        ):
            raise ToolDenied("Tool budget exhausted")
        self.calls[agent] += 1
        token = DEPTH.set(DEPTH.get() + 1)
        try:
            b = self._bundle
            # Return copies so an interpreter cannot mutate the authoritative snapshot.
            if name == "stock_resolver":
                return tuple(type(a).model_validate_json(a.model_dump_json()) for a in b.assets)
            if name == "mandate_validator":
                return ("PROPOSE_ONLY", "DRY_RUN")
            if name == "market_evidence":
                return b.assessment.model_copy(deep=True)
            if name == "news_evidence":
                return b.articles, b.assessment.model_copy(deep=True)
            if name == "historical_retrieval":
                return tuple(r.model_copy(deep=True) for r in b.research), b.assessment.model_copy(
                    deep=True
                )
            if name == "recent_memory":
                return tuple(m.model_copy(deep=True) for m in self._memories)
            if name == "candidate_table":
                return tuple(c.model_copy(deep=True) for c in b.candidates)
            if name == "constraints":
                return tuple(d.model_copy(deep=True) for d in b.downstream)
            raise ToolDenied("Tool unavailable")
        finally:
            DEPTH.reset(token)
