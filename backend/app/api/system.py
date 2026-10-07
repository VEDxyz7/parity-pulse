from fastapi import APIRouter, Request, Response

from app import __version__
from app.api.schemas import DemoSystemStatus, FixtureStatus, GateStatus, HealthStatus, SystemStatus

router = APIRouter(prefix="/api", tags=["foundation"])


def database_status(request: Request) -> str:
    db = request.app.state.database
    return "connected" if request.app.state.ready and db and db.healthy() else "unavailable"


@router.get("/health", response_model=HealthStatus)
def health(request: Request, response: Response):
    status = database_status(request)
    response.status_code = 200 if status == "connected" else 503
    return HealthStatus(
        status="ok" if status == "connected" else "degraded",
        database_status=status,
        service_version=__version__,
        run_id=request.app.state.run_id,
    )


@router.get("/system-status", response_model=DemoSystemStatus | SystemStatus)
def system_status(request: Request, response: Response):
    settings, state = request.app.state.settings, request.app.state
    status = database_status(request)
    response.status_code = 200 if status == "connected" else 503
    fixture = state.demo_fixture
    model = DemoSystemStatus if settings.runtime_mode == "DEMO" else SystemStatus
    return model(
        environment=settings.app_env,
        data_mode=settings.data_mode,
        execution_mode=settings.execution_mode,
        approval_mode=settings.approval_mode,
        live_trading_enabled=settings.live_trading_enabled,
        require_simulation=settings.require_simulation,
        database_status=status,
        service_version=__version__,
        run_id=state.run_id,
        gates=GateStatus(),
        demo_fixture=FixtureStatus(
            fixture_id=fixture.fixture_id,
            data_mode=fixture.data_mode,
            execution_allowed=fixture.execution_allowed,
        )
        if fixture
        else None,
    )
