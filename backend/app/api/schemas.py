from typing import Literal

from pydantic import BaseModel, ConfigDict


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GateStatus(PublicModel):
    DATA_GATE: Literal["PASS"] = "PASS"
    DRY_RUN_GATE: Literal["PASS"] = "PASS"
    SWAP_LIVE_GATE: Literal["BLOCKED"] = "BLOCKED"
    RFQ_LIVE_GATE: Literal["BLOCKED"] = "BLOCKED"
    AGENTIC_WALLET_LIVE_GATE: Literal["BLOCKED"] = "BLOCKED"


class FixtureStatus(PublicModel):
    fixture_id: str
    data_mode: Literal["DEMO"]
    execution_allowed: Literal[False]


class HealthStatus(PublicModel):
    status: Literal["ok", "degraded"]
    database_status: Literal["connected", "unavailable"]
    service_version: str
    run_id: str


class SystemStatus(PublicModel):
    environment: Literal["development", "test", "production"]
    data_mode: Literal["DEMO", "LIVE_READ_ONLY"]
    execution_mode: Literal["DRY_RUN"]
    approval_mode: Literal["PROPOSE_ONLY"]
    live_trading_enabled: Literal[False]
    require_simulation: Literal[True]
    database_status: Literal["connected", "unavailable"]
    service_version: str
    phase: Literal[2] = 2
    run_id: str
    gates: GateStatus
    demo_fixture: FixtureStatus | None


class DemoSystemStatus(SystemStatus):
    runtime_mode: Literal["DEMO"] = "DEMO"
