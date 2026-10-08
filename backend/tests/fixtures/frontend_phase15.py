"""Phase 15 browser fixture only: isolated, synthetic, never provider verification.

Explicitly loaded by scripts/verify-frontend-phase15.py; no production app hook.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from app.agents.adapters import DemoEvidenceAdapter
from app.agents.orchestrator import AgentOrchestrator
from app.config import Settings
from app.main import create_app
from app.models.research import ResearchPolicy
from app.providers.demo import load_data_fixture
from app.repositories.research import ResearchStore
from app.services.research_replay import HistoricalReplay
from backend.tests.fixtures.execution_fixtures import allowance
from backend.tests.integration.test_terminal import NOW, change
from backend.tests.unit.test_agents import REQUEST
from backend.tests.unit.test_portfolio import evaluate, setup
from backend.tests.unit.test_research import calendar, dataset, fixture


def factory(runtime, simulation_failure=False):
    store = ResearchStore(Path(os.environ["PARITY_PHASE15_DIR"]) / "browser-state" / str(uuid4()))
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            runtime_mode=runtime,
            data_mode="DEMO",
            database_url="sqlite:///:memory:",
            log_level="WARNING",
        ),
        terminal_research_store=store,
    )
    original = app.router.lifespan_context

    @asynccontextmanager
    async def life(app):
        async with original(app):
            s = app.state.terminal
            s.clock = lambda: NOW
            app.state.scorecard.clock = lambda: NOW
            app.state.scorecard.audit.clock = lambda: NOW
            app.state.exposure.clock = lambda: NOW
            app.state.agent_api.clock = lambda: NOW
            records = load_data_fixture()
            stamp = dict(
                source_timestamp=NOW, ingestion_timestamp=NOW, raw_source_timestamp=NOW.isoformat()
            )
            t = next(r for r in records["metadata"] if r.ticker == "NVDA")
            p = next(r for r in records["tokens"] if r.ticker == "NVDA")
            e = next(r for r in records["equities"] if r.ticker == "NVDA")
            s.layer.repository.save(
                [
                    change(t, **stamp, token_to_share_ratio="0.1"),
                    change(p, **stamp, token_to_share_ratio="0.1", token_price="10.2"),
                    change(e, **stamp, kind="SNAPSHOT", price="100"),
                ]
            )
            await AgentOrchestrator(store=s.agents).analyze(
                REQUEST, DemoEvidenceAdapter().load("supported-move")
            )
            cal = calendar.__wrapped__()
            rows = dataset.__wrapped__(cal, fixture.__wrapped__())
            store.save(
                HistoricalReplay(ResearchPolicy(model_features=("deviation",))).run(
                    rows, provenance=("SYNTHETIC_TEST",)
                )
            )
            portfolio, position, time = setup()
            s.portfolio = portfolio
            s.execution, s.positions = portfolio.positions.execution.store, portfolio.positions
            plan = evaluate(portfolio)
            portfolio.prepare(plan.plan_id, plan.actions[0].action_id, allowance=allowance())
            originals = (app.state.portfolio, app.state.positions)
            if runtime == "DEMO":
                app.state.portfolio, app.state.positions = portfolio, portfolio.positions
            try:
                yield
            finally:
                app.state.portfolio, app.state.positions = originals
                portfolio.store.close()
                portfolio.positions.store.close()
                portfolio.positions.execution.store.close()

    if simulation_failure:

        @app.middleware("http")
        async def changed_risk_fixture(request, call_next):
            # Alter existing synthetic risk inputs at the test boundary. Actual service rejects.
            if request.url.path == "/api/demo/simulate":
                core = app.state.demo_opportunity
                values = core.fixture.risk_inputs.model_dump()
                values["wallet_available_usd"] = "0"
                inputs = type(core.fixture.risk_inputs).model_validate(values)
                core.fixture = type(core.fixture).model_validate(
                    {**core.fixture.model_dump(), "risk_inputs": inputs}
                )
            return await call_next(request)

    app.router.lifespan_context = life
    return app


def demo():
    return factory("DEMO")


def ordinary():
    return factory("LIVE")


def failed_simulation():
    return factory("DEMO", simulation_failure=True)
