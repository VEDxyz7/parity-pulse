"""Read existing, mode-scoped Trust evidence; never fetch providers or seed history."""

from datetime import timedelta

from sqlalchemy import select

from app.models.data_tables import TrustAssessmentRow
from app.models.trust import TrustAssessment


class RoutingEvidenceReader:
    def __init__(self, database):
        self.database = database

    def latest(self, underlying, *, mode, now):
        if mode not in {"DEMO", "LIVE"}:
            raise ValueError("Explicit data mode required")
        if underlying is None:
            return None
        with self.database.sessions() as session:
            row = session.scalar(
                select(TrustAssessmentRow)
                .where(
                    TrustAssessmentRow.ticker == underlying,
                    TrustAssessmentRow.data_mode == mode,
                    TrustAssessmentRow.ingestion_timestamp <= now.isoformat(),
                    TrustAssessmentRow.ingestion_timestamp
                    > (now - timedelta(seconds=120)).isoformat(),
                )
                .order_by(TrustAssessmentRow.ingestion_timestamp.desc(), TrustAssessmentRow.id)
                .limit(1)
            )
            result = TrustAssessment.model_validate_json(row.payload) if row is not None else None
        return result if result is not None and result.status == "ASSESSED" else None
