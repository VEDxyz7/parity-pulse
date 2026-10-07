import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException

from app import __version__
from app.api.assets import router as assets_router
from app.api.exposure import router as exposure_router
from app.api.middleware import RequestContextMiddleware
from app.api.system import router
from app.api.trust import router as trust_router
from app.clients.common import ProviderError
from app.config import Settings
from app.database import Database
from app.demo import load_demo_fixture
from app.services.data_layer import DataLayer
from app.services.exposure import ExposureService
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
            database = Database(configured.database_url)
            database.initialize()
            app.state.database = database
            app.state.data_layer = DataLayer(configured, database)
            app.state.exposure = ExposureService(app.state.data_layer, database)
            app.state.trust = TrustService(app.state.data_layer, database)
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
    return app
