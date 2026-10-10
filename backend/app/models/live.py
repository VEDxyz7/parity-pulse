"""Allowlisted public execution views. Sensitive artifacts have no response field."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.execution import Digest, ExecutionModel, Hash, Identifier

UNRESOLVED = frozenset(
    {
        "PREPARING",
        "QUOTED",
        "APPROVING",
        "SIGNED",
        "SUBMITTING",
        "SUBMITTED",
        "SUBMISSION_UNKNOWN",
        "RECONCILIATION_REQUIRED",
    }
)
TERMINAL = frozenset({"CONFIRMED", "FAILED", "REJECTED", "NOT_FILLED"})


class PublicFill(ExecutionModel):
    action_id: Identifier
    plan_id: str
    status: str
    asset: str
    side: Literal["BUY", "SELL"]
    notional_usd: str
    approve_tx: Hash | None = None
    swap_tx: Hash | None = None
    reasons: tuple[Identifier, ...] = ()
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record):
        # Construct from a positive allowlist, including for legacy rows with signatures.
        return cls.model_validate({k: record[k] for k in cls.model_fields if k in record})


class ExecutionConsent(ExecutionModel):
    action_id: Identifier
    payload_digest: Digest
    confirmation_id: Identifier
    confirmed_at: datetime
    expires_at: datetime
    source: Literal["HOST_EXPLICIT_USER_CONFIRMATION"]


class ExecutePlanRequest(ExecutionModel):
    confirmations: tuple[ExecutionConsent, ...] = Field(max_length=100)
