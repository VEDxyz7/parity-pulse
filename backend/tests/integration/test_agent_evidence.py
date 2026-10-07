"""Point-in-time Phase 5/6 integration. Generated histories remain SYNTHETIC_TEST."""

import asyncio
import hashlib
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest

from app.agents.adapters import LiveReadOnlyEvidenceAdapter, reference
from app.agents.memory import AgentStore
from app.agents.orchestrator import AgentOrchestrator
from app.agents.schemas import EvidenceBundle, ResearchInput
from app.models.research import ResearchPolicy
from app.models.trust import TrustAssessment
from app.repositories.research import ResearchStore
from app.services.research_model import HistoricalRetrieval, RollingOpeningModel
from backend.tests.unit.test_agents import REQUEST, changed
from backend.tests.unit.test_research import calendar, dataset, fixture, frame


@pytest.fixture(scope="module")
def synthetic_research():
    cal = calendar.__wrapped__()
    base = fixture.__wrapped__()
    episodes = dataset.__wrapped__(cal, base)
    from app.services.research_episodes import ResearchEpisodeBuilder

    current = ResearchEpisodeBuilder(cal).build(frame(cal, base)).decision
    current = changed(current, policy=ResearchPolicy(model_features=("deviation",)))
    assessment = TrustAssessment(
        assessment_id=UUID(current.decision_id[:32]),
        run_id="synthetic-phase5",
        request_id="synthetic-phase5",
        correlation_id="synthetic-phase5",
        data_mode="DEMO",
        evaluated_at=current.decision_at,
        ticker=current.ticker,
        status="ASSESSED",
        regime=None,
        representations=[],
        limitations=["SYNTHETIC_TEST_NOT_REAL_EVIDENCE"],
    )
    ref = reference(
        assessment, mode="DEMO", source="SYNTHETIC_PHASE_5_TEST", at=current.decision_at
    )
    return EvidenceBundle(
        data_mode="DEMO",
        decision_at=current.decision_at,
        assessment=assessment,
        references=(ref,),
        research=(ResearchInput(current=current, episodes=tuple(episodes)),),
    )


def test_phase5_retrieval_and_model_are_called_without_reimplementation(synthetic_research):
    b = synthetic_research
    current = b.research[0]
    retrieval = HistoricalRetrieval(current.current.policy).evaluate(
        current.episodes, current.current
    )
    prediction = RollingOpeningModel(current.current.policy).predict(
        current.episodes, current.current
    )
    store = AgentStore()
    try:
        run = asyncio.run(AgentOrchestrator(store=store).analyze(REQUEST, b))
    finally:
        store.close()
    research = run.responses[3].output
    assert research.retrieval_status == retrieval.status == "SUFFICIENT"
    assert research.model_status == prediction.status == "READY"
    assert research.model_samples == prediction.sample_count >= 30
    assert research.retrieved_analogues == retrieval.retrieved_count == 3
    assert run.decision.decision == "DEFER"  # No qualifying route/risk/Trust candidate supplied.


def test_future_phase5_outcomes_do_not_change_prior_agent_run(synthetic_research):
    b = synthetic_research
    i = b.research[0]
    future_at = b.decision_at + timedelta(days=1)
    future_decision = changed(
        i.episodes[-1].decision,
        decision_at=future_at,
        opening_at=future_at + timedelta(minutes=1),
        token=None,
        independent_equity=None,
        closure_token=None,
        trust=None,
        sample=None,
        data_quality="REJECTED",
        reasons=("SYNTHETIC_FUTURE",),
    )
    target = changed(
        i.episodes[-1].target,
        opening_at=future_decision.opening_at,
        completed_at=future_at + timedelta(minutes=6),
        available_at=future_at + timedelta(minutes=7),
        status="POSTHOC_ONLY",
        provenance=(),
    )
    extra = changed(
        i.episodes[-1], episode_id="future-synthetic", decision=future_decision, target=target
    )
    with_future = changed(b, research=(changed(i, episodes=(*i.episodes, extra)),))
    stores = (AgentStore(), AgentStore())
    try:
        one = asyncio.run(AgentOrchestrator(store=stores[0]).analyze(REQUEST, b))
        two = asyncio.run(AgentOrchestrator(store=stores[1]).analyze(REQUEST, with_future))
        assert one == two
    finally:
        for store in stores:
            store.close()


def test_captured_real_replay_has_no_synthetic_fallback_or_production_mutation():
    path = Path(
        "data/research/phase5/a3e7be2630acccb2b7496d87f2e584ce2cf8af34811461738336d42aba59e98e.json"
    )
    if not path.is_file():
        pytest.skip(
            "Local real replay artifact is not committed; synthetic controls still required"
        )
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    replay = ResearchStore(path.parent).load(path.stem)
    b = LiveReadOnlyEvidenceAdapter().from_replay(replay)
    store = AgentStore()
    try:
        run = asyncio.run(AgentOrchestrator(store=store).analyze(REQUEST, b))
        assert run.data_mode == "LIVE_READ_ONLY"
        assert run.decision.decision == "DEFER"
        assert run.responses[3].status == "INSUFFICIENT_EVIDENCE"
        assert run.responses[3].output.model_samples == 0
        assert run.responses[3].output.retrieved_analogues == 0
        assert run.decision.risk_preview_status == "UNAVAILABLE"
        assert not run.execution_authorized
        assert not store.recent("NVDA", "DEMO", "UNKNOWN", b.decision_at + timedelta(days=1))
    finally:
        store.close()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
