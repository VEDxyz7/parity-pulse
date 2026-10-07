"""Proposal records are separate from orders/positions, isolated by data mode."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from app.models.data_tables import ExposureProposalRow
from app.models.exposure import ExposureProposal


class ExposureRepository:
    def __init__(self, database):
        self.database = database

    def save(self, proposal: ExposureProposal):
        with self.database.sessions.begin() as session:
            session.add(
                ExposureProposalRow(
                    id=str(proposal.proposal_id),
                    data_mode=proposal.data_mode,
                    ticker=proposal.ticker or "UNRESOLVED",
                    provider="EXPOSURE_ESTIMATE",
                    source_timestamp=None,
                    ingestion_timestamp=proposal.created_at.isoformat(),
                    payload=proposal.model_dump_json(),
                )
            )

    def get(self, proposal_id: UUID, mode: str, now: datetime):
        if mode not in {"DEMO", "LIVE"}:
            raise ValueError("Explicit data mode required")
        with self.database.sessions() as session:
            row = session.scalar(
                select(ExposureProposalRow).where(
                    ExposureProposalRow.id == str(proposal_id),
                    ExposureProposalRow.data_mode == mode,
                )
            )
            if row is None:
                return None
            proposal = ExposureProposal.model_validate_json(row.payload)
        if now >= proposal.valid_until and proposal.status == "DRY_RUN":
            return proposal.model_copy(
                update={
                    "status": "EXPIRED",
                    "route_type": "NONE",
                    "quote_status": "UNAVAILABLE",
                    "selected": None,
                    "route_selection_reason": "ESTIMATE_EXPIRED_REQUEST_NEW_DATA",
                    "execution_blockers": [*proposal.execution_blockers, "ESTIMATE_EXPIRED"],
                }
            )
        return proposal
