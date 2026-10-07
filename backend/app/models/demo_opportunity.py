"""Marked DEMO orchestration envelopes, never production gate changes."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from app.models.data import DataModel
from app.models.demo_sandbox import DemoMarker, DemoProductionGates, ScenarioId
from app.models.opportunity import OpportunityDecision, OpportunityInputs
from app.models.risk import RiskDecision, RiskInputs, RiskPolicy
from app.models.routing import RouteDecision


class DemoOpportunityFixture(DemoMarker):
    economics: OpportunityInputs
    risk_inputs: RiskInputs
    risk_policy: RiskPolicy


class OpportunityRequest(DataModel):
    trust_assessment_id: UUID


class RiskRequest(DataModel):
    opportunity_id: UUID


class DemoOpportunityResult(DemoMarker):
    route_decision: RouteDecision | None = None
    runtime_mode: Literal["DEMO"] = "DEMO"
    scenario_id: ScenarioId
    trust_fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    inputs_fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    opportunity: OpportunityDecision
    production_gates: DemoProductionGates = DemoProductionGates()


class DemoRiskResult(DemoMarker):
    runtime_mode: Literal["DEMO"] = "DEMO"
    scenario_id: ScenarioId
    inputs_fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    risk: RiskDecision
    production_gates: DemoProductionGates = DemoProductionGates()
