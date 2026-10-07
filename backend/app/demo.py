from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.config import ROOT_DIR


class FoundationFixture(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    fixture_id: Literal["parity-pulse-foundation-v1"]
    data_mode: Literal["DEMO"]
    execution_allowed: Literal[False]
    service_name: Literal["Parity Pulse"]
    phase: Literal[1]
    observed_at: datetime


def load_demo_fixture() -> FoundationFixture:
    raw = (ROOT_DIR / "data/demo/foundation.json").read_bytes()
    return FoundationFixture.model_validate_json(raw)
