import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.engine import make_url
from starlette.exceptions import HTTPException

from app import __version__
from app.agents.memory import AgentStore
from app.agents.orchestrator import AgentOrchestrator
from app.api.agent_api import router as agent_api_router
from app.api.assets import router as assets_router
from app.api.demo_opportunity import router as demo_opportunity_router
from app.api.demo_paper import router as demo_paper_router
from app.api.demo_preparation import router as demo_preparation_router
from app.api.demo_sandbox import router as demo_sandbox_router
from app.api.exposure import router as exposure_router
from app.api.middleware import RequestContextMiddleware
from app.api.opportunity_scan import router as opportunity_scan_router
from app.api.portfolio import autopilot_router
from app.api.portfolio import router as portfolio_router
from app.api.live import router as live_router
from app.api.positions import router as positions_router
from app.api.scorecard import router as scorecard_router
from app.api.system import router
from app.api.terminal import router as terminal_router
from app.api.trust import router as trust_router
from app.api.workspace import router as workspace_router
from app.clients.binance_trading import BinanceSafetyClient
from app.clients.common import ProviderError
from app.clients.llm import configured_provider
from app.config import Settings
from app.database import Database
from app.demo import load_demo_fixture
from app.models.execution import ExecutionControls
from app.repositories.agent_api import ToolReceipts
from app.repositories.execution import ExecutionStore
from app.repositories.opportunity_scan import OpportunityScanStore
from app.repositories.portfolio import PortfolioStore
from app.repositories.position import PositionStore
from app.repositories.research import ResearchStore
from app.repositories.scorecard import ScorecardStore
from app.services.agent_api import AgentAPI
from app.services.agentic_wallet import AgenticWalletAdapter
from app.services.data_layer import DataLayer
from app.services.demo_opportunity import DemoOpportunityFlow
from app.services.demo_paper import DemoPaperLedger
from app.services.demo_preparation import DemoPreparationFlow
from app.services.demo_sandbox import DemoTrustSandbox
from app.services.execution import SafetyExecutionService
from app.services.exposure import ExposureService
from app.services.opportunity_scan import OpportunityScanService
from app.services.opportunity_sources import DataLayerScanSource, DemoScanSource
from app.services.portfolio import PortfolioService
from app.services.portfolio_sources import CachedPortfolioSource
from app.services.position import PositionService
from app.services.scorecard import ScorecardService
from app.services.terminal import TerminalService
from app.services.trust import TrustService
from app.utils.logging import configure_logging

logger = logging.getLogger("parity.app")


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    state = request.state
    ids = {
        "request_id": getattr(state, "request_id", str(uuid4())),
        "correlation_id": getattr(state, "correlation_id", str(uuid4())),
        "run_id": request.app.state.run_id,
    }
    return JSONResponse(
        {"error": {"code": code, "message": message}, **ids},
        status_code=status,
        headers={
            "X-Request-ID": ids["request_id"],
            "X-Correlation-ID": ids["correlation_id"],
            "X-Run-ID": ids["run_id"],
        },
    )


def create_app(
    settings: Settings | None = None,
    *,
    llm_provider=None,
    position_recovery_limit=100,
    portfolio_source=None,
    terminal_research_store=None,
) -> FastAPI:
    if type(position_recovery_limit) is not int or not 1 <= position_recovery_limit <= 1000:
        raise ValueError("Bounded position recovery required")
    try:
        configured = (
            Settings.model_validate(
                {name: getattr(settings, name) for name in Settings.model_fields}
            )
            if settings is not None
            else Settings()
        )
    except (ValidationError, ValueError):
        # Never render validation input (which can include the complete settings dictionary).
        raise RuntimeError("Invalid application configuration; startup refused") from None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(configured.log_level, configured.redaction_values())
        database = None
        llm_transport = None
        try:
            database = Database(
                "sqlite:///:memory:"
                if configured.runtime_mode == "DEMO"
                else configured.database_url
            )
            database.initialize()
            app.state.database = database
            app.state.data_layer = DataLayer(configured, database)
            app.state.exposure = ExposureService(app.state.data_layer, database)
            app.state.trust = TrustService(app.state.data_layer, database)
            database_file = make_url(configured.database_url).database
            scan_directory = (
                None
                if (
                    configured.runtime_mode == "DEMO"
                    or configured.app_env == "test"
                    or database_file == ":memory:"
                )
                else (Path(database_file).resolve().parent / "opportunity/phase7")
            )
            app.state.opportunity_scan_store = OpportunityScanStore(scan_directory)
            agent_store = AgentStore(scan_directory / "agents" if scan_directory else None)
            provider = llm_provider
            if provider is None:
                provider, llm_transport = configured_provider(configured)
            app.state.opportunity_scan = OpportunityScanService(
                store=app.state.opportunity_scan_store,
                orchestrator=AgentOrchestrator(store=agent_store, provider=provider),
            )
            app.state.opportunity_source = (
                DemoScanSource()
                if configured.runtime_mode == "DEMO"
                else DataLayerScanSource(app.state.data_layer, app.state.trust)
            )
            app.state.opportunity_scan_lock = asyncio.Lock()
            execution_directory = (
                None
                if scan_directory is None
                else Path(database_file).resolve().parent / "execution/phase8"
            )
            app.state.execution_store = ExecutionStore(execution_directory)
            app.state.safety_client = (
                BinanceSafetyClient(
                    configured.binance_web3_api_key,
                    configured.binance_web3_secret_key,
                    cache_ttl=0,
                )
                if configured.data_mode == "LIVE_READ_ONLY"
                else None
            )
            app.state.safety_execution = SafetyExecutionService(
                app.state.safety_client,
                app.state.execution_store,
                ExecutionControls(data_mode=configured.data_mode),
                clock=lambda: datetime.now(UTC),
                wallet_adapter=AgenticWalletAdapter(data_mode=configured.data_mode),
            )
            position_directory = (
                None
                if execution_directory is None
                else Path(database_file).resolve().parent
                / "positions/phase10"
                / configured.data_mode
            )
            app.state.position_store = PositionStore(app.state.execution_store, position_directory)
            app.state.positions = PositionService(
                app.state.position_store,
                app.state.safety_execution,
                clock=lambda: datetime.now(UTC),
                postopen_exit_minutes=configured.postopen_exit_minutes,
            )
            app.state.safety_execution.position_guard = app.state.positions.has_unresolved
            # Bounded startup recovery performs status reads only. No execution/wallet writes.
            app.state.position_recovery_results = app.state.positions.recover(
                limit=position_recovery_limit
            )
            portfolio_directory = (
                None
                if execution_directory is None
                else Path(database_file).resolve().parent
                / "portfolio/phase11"
                / configured.data_mode
            )
            app.state.portfolio_store = PortfolioStore(portfolio_directory)
            app.state.live = None
            source = portfolio_source
            if configured.portfolio_inventory == "WALLET" and source is None:
                from app.services.live_wiring import LiveRuntime

                app.state.live = LiveRuntime(configured, app.state.data_layer, portfolio_directory)
                source = app.state.live.source
            app.state.portfolio = PortfolioService(
                app.state.portfolio_store,
                app.state.positions,
                source
                or CachedPortfolioSource(app.state.data_layer, clock=lambda: datetime.now(UTC)),
                clock=lambda: datetime.now(UTC),
                trust_required=configured.trust_required_for_rebalance,
                inventory=configured.portfolio_inventory,
                allow_closed_underlying=configured.portfolio_inventory == "WALLET"
                and configured.closed_market_swap,
            )
            app.state.portfolio.recover()
            if app.state.live is not None:
                app.state.live.attach(app.state.portfolio)
            app.state.positions.portfolio_exit_guard = app.state.portfolio.can_reduce
            app.state.terminal = TerminalService(
                app.state.data_layer,
                app.state.trust,
                agent_store,
                app.state.execution_store,
                app.state.positions,
                app.state.portfolio,
                terminal_research_store
                or ResearchStore(Path(__file__).resolve().parents[2] / "data/research/phase5"),
                clock=lambda: datetime.now(UTC),
            )
            app.state.demo_sandbox = (
                DemoTrustSandbox() if configured.runtime_mode == "DEMO" else None
            )
            app.state.demo_opportunity = (
                DemoOpportunityFlow(app.state.demo_sandbox)
                if configured.runtime_mode == "DEMO"
                else None
            )
            app.state.demo_preparation = (
                DemoPreparationFlow(app.state.demo_opportunity)
                if configured.runtime_mode == "DEMO"
                else None
            )
            app.state.demo_paper = (
                DemoPaperLedger(app.state.demo_preparation)
                if configured.runtime_mode == "DEMO"
                else None
            )
            app.state.scorecard_store = ScorecardStore(
                None
                if execution_directory is None
                else Path(database_file).resolve().parent
                / "scorecard/phase13"
                / configured.data_mode
            )
            app.state.scorecard = ScorecardService(
                app.state.scorecard_store,
                app.state.terminal,
                app.state.exposure.repository,
                app.state.opportunity_scan_store,
                clock=lambda: datetime.now(UTC),
                secrets=configured.redaction_values(),
                demo_flow=app.state.demo_opportunity,
                paper=app.state.demo_paper,
                demo_preparation=app.state.demo_preparation,
            )
            app.state.tool_receipts = ToolReceipts(
                None
                if execution_directory is None
                else Path(database_file).resolve().parent
                / "agent-api/phase14"
                / configured.data_mode
            )
            app.state.agent_api = AgentAPI(app.state, app.state.tool_receipts)
            for client in app.state.data_layer.clients:
                client.run_id = app.state.run_id
            app.state.demo_fixture = load_demo_fixture() if configured.data_mode == "DEMO" else None
            app.state.ready = True
            logger.info(
                "APP_STARTED",
                extra={
                    "event_fields": {
                        "run_id": app.state.run_id,
                        "service_version": __version__,
                        "database_status": "connected",
                    }
                },
            )
            yield
        except Exception as exc:
            logger.error(
                "APP_LIFESPAN_FAILED",
                extra={
                    "event_fields": {
                        "run_id": app.state.run_id,
                        "error_type": type(exc).__name__,
                    }
                },
            )
            raise RuntimeError("Application lifecycle failed; consult sanitized logs") from None
        finally:
            if llm_transport is not None:
                await llm_transport.close()
            app.state.ready = False
            if getattr(app.state, "tool_receipts", None) is not None:
                app.state.tool_receipts.close()
            app.state.agent_api = None
            if getattr(app.state, "scorecard_store", None) is not None:
                app.state.scorecard_store.close()
            app.state.scorecard = None
            app.state.demo_fixture = None
            if getattr(app.state, "data_layer", None) is not None:
                app.state.data_layer.close()
            app.state.data_layer = None
            app.state.exposure = None
            app.state.trust = None
            app.state.demo_sandbox = None
            app.state.demo_opportunity = None
            app.state.demo_preparation = None
            app.state.demo_paper = None
            if getattr(app.state, "opportunity_scan_store", None) is not None:
                app.state.opportunity_scan_store.close()
            if getattr(app.state, "opportunity_scan", None) is not None:
                app.state.opportunity_scan.agents.store.close()
            app.state.opportunity_scan = None
            app.state.opportunity_source = None
            if getattr(app.state, "safety_client", None) is not None:
                app.state.safety_client.close()
            if getattr(app.state, "execution_store", None) is not None:
                if getattr(app.state, "position_store", None) is not None:
                    app.state.position_store.close()
                app.state.positions = None
                app.state.execution_store.close()
            if getattr(app.state, "live", None) is not None:
                app.state.live.close()
            if getattr(app.state, "portfolio_store", None) is not None:
                app.state.portfolio_store.close()
            app.state.portfolio = None
            app.state.terminal = None
            app.state.safety_execution = None
            if database is not None:
                database.close()
            app.state.database = None
            logger.info("APP_STOPPED", extra={"event_fields": {"run_id": app.state.run_id}})

    app = FastAPI(title="Parity Pulse", version=__version__, lifespan=lifespan)
    app.state.settings = configured
    app.state.run_id = str(uuid4())
    app.state.ready, app.state.database, app.state.demo_fixture = False, None, None
    app.add_middleware(RequestContextMiddleware, run_id=app.state.run_id)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, _exc):
        return error_response(request, 422, "INVALID_REQUEST", "Request validation failed")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc):
        return error_response(
            request,
            exc.status_code,
            "HTTP_ERROR",
            "Request could not be handled",
        )

    @app.exception_handler(ProviderError)
    async def provider_error(request: Request, exc):
        return error_response(
            request, 503, exc.kind, "Read-only provider data unavailable; no substitution was made"
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc):
        logger.error(
            "REQUEST_FAILED",
            extra={
                "event_fields": {
                    "run_id": app.state.run_id,
                    "request_id": getattr(request.state, "request_id", None),
                    "correlation_id": getattr(request.state, "correlation_id", None),
                    "error_type": type(exc).__name__,
                }
            },
        )
        return error_response(request, 500, "INTERNAL_ERROR", "An internal error occurred")

    app.include_router(router)
    app.include_router(assets_router)
    app.include_router(exposure_router)
    app.include_router(trust_router)
    app.include_router(opportunity_scan_router)
    app.include_router(positions_router)
    app.include_router(portfolio_router)
    if configured.portfolio_inventory == "WALLET":
        # Live wallet routes exist only when wallet inventory is configured.
        app.include_router(live_router)
    app.include_router(autopilot_router)
    app.include_router(terminal_router)
    app.include_router(scorecard_router)
    app.include_router(agent_api_router)
    app.include_router(workspace_router)
    if configured.runtime_mode == "DEMO":
        app.include_router(demo_sandbox_router)
        app.include_router(demo_opportunity_router)
        app.include_router(demo_preparation_router)
        app.include_router(demo_paper_router)
    return app
