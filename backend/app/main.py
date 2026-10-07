import asyncio
import logging
from contextlib import asynccontextmanager
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
from app.api.assets import router as assets_router
from app.api.demo_opportunity import router as demo_opportunity_router
from app.api.demo_paper import router as demo_paper_router
from app.api.demo_preparation import router as demo_preparation_router
from app.api.demo_sandbox import router as demo_sandbox_router
from app.api.exposure import router as exposure_router
from app.api.middleware import RequestContextMiddleware
from app.api.opportunity_scan import router as opportunity_scan_router
from app.api.system import router
from app.api.trust import router as trust_router
from app.clients.common import ProviderError
from app.config import Settings
from app.database import Database
from app.demo import load_demo_fixture
from app.repositories.opportunity_scan import OpportunityScanStore
from app.services.data_layer import DataLayer
from app.services.demo_opportunity import DemoOpportunityFlow
from app.services.demo_paper import DemoPaperLedger
from app.services.demo_preparation import DemoPreparationFlow
from app.services.demo_sandbox import DemoTrustSandbox
from app.services.exposure import ExposureService
from app.services.opportunity_scan import OpportunityScanService
from app.services.opportunity_sources import DataLayerScanSource, DemoScanSource
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


def create_app(settings: Settings | None = None) -> FastAPI:
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
            app.state.opportunity_scan = OpportunityScanService(
                store=app.state.opportunity_scan_store,
                orchestrator=AgentOrchestrator(store=agent_store),
            )
            app.state.opportunity_source = (
                DemoScanSource()
                if configured.runtime_mode == "DEMO"
                else DataLayerScanSource(app.state.data_layer, app.state.trust)
            )
            app.state.opportunity_scan_lock = asyncio.Lock()
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
            app.state.ready = False
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
    if configured.runtime_mode == "DEMO":
        app.include_router(demo_sandbox_router)
        app.include_router(demo_opportunity_router)
        app.include_router(demo_preparation_router)
        app.include_router(demo_paper_router)
    return app
