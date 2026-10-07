"""Mode-isolated immutable analytical records, separate from orders and positions."""

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from app.models.data_tables import TrustAssessmentRow, TrustEpisodeRow, TrustSampleRow
from app.models.trust import TrustAssessment, TrustEpisode, TrustSample


class TrustRepository:
    def __init__(self, database):
        self.database = database

    def save(self, record):
        record = type(record).model_validate(record.model_dump())
        if isinstance(record, TrustAssessment):
            table, identifier, mode, ticker, at = (
                TrustAssessmentRow,
                str(record.assessment_id),
                record.data_mode,
                record.ticker or "UNRESOLVED",
                record.evaluated_at,
            )
        elif isinstance(record, TrustSample):
            table, identifier, mode, ticker, at = (
                TrustSampleRow,
                record.sample_id,
                record.data_mode,
                record.ticker,
                record.features.available_at,
            )
        elif isinstance(record, TrustEpisode):
            table, identifier, mode, ticker, at = (
                TrustEpisodeRow,
                record.episode_id,
                record.sample.data_mode,
                record.sample.ticker,
                record.outcome_available_at,
            )
        else:
            raise ValueError("Unknown trust record")
        with self.database.engine.begin() as connection:
            # First availability is immutable: repeated observation cannot backdate evidence.
            statement = insert(table).values(
                id=identifier,
                data_mode=mode,
                ticker=ticker,
                provider="TRUST_ENGINEERING_V1",
                source_timestamp=None,
                ingestion_timestamp=at.isoformat(),
                payload=record.model_dump_json(),
            )
            connection.execute(statement.on_conflict_do_nothing(index_elements=["id"]))

    def history(self, model, *, mode, ticker, at, start):
        if mode not in {"LIVE", "DEMO"}:
            raise ValueError("Explicit data mode required")
        table = {TrustSample: TrustSampleRow, TrustEpisode: TrustEpisodeRow}[model]
        with self.database.sessions() as session:
            rows = session.scalars(
                select(table)
                .where(
                    table.data_mode == mode,
                    table.ticker == ticker,
                    table.ingestion_timestamp <= at.isoformat(),
                    table.ingestion_timestamp >= start.isoformat(),
                )
                .order_by(table.ingestion_timestamp.desc(), table.id)
                .limit(5001)
            ).all()
        return [model.model_validate_json(row.payload) for row in rows[:5000]], len(rows) > 5000

    def get(self, assessment_id, mode):
        if mode not in {"LIVE", "DEMO"}:
            raise ValueError("Explicit data mode required")
        with self.database.sessions() as session:
            row = session.scalar(
                select(TrustAssessmentRow).where(
                    TrustAssessmentRow.id == str(assessment_id),
                    TrustAssessmentRow.data_mode == mode,
                )
            )
            return TrustAssessment.model_validate_json(row.payload) if row else None
