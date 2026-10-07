"""Canonical decimal JSON text; no financial SQLite REAL/Numeric columns."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RecordColumns:
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data_mode: Mapped[str] = mapped_column(String(4), index=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    source_timestamp: Mapped[str | None] = mapped_column(Text)
    ingestion_timestamp: Mapped[str] = mapped_column(Text)
    payload: Mapped[str] = mapped_column(Text)


class TrackedAssetRow(RecordColumns, Base):
    __tablename__ = "tracked_assets"


class IssuerRow(RecordColumns, Base):
    __tablename__ = "issuers"


class TokenMetadataRow(RecordColumns, Base):
    __tablename__ = "token_metadata"


class TokenObservationRow(RecordColumns, Base):
    __tablename__ = "token_observations"


class EquityObservationRow(RecordColumns, Base):
    __tablename__ = "equity_observations"


class NewsEventRow(RecordColumns, Base):
    __tablename__ = "news_events"


class MarketStatusRow(RecordColumns, Base):
    __tablename__ = "market_status"


class IngestionCheckpointRow(RecordColumns, Base):
    __tablename__ = "ingestion_checkpoints"


class ExposureProposalRow(RecordColumns, Base):
    __tablename__ = "exposure_proposals"


class TrustAssessmentRow(RecordColumns, Base):
    __tablename__ = "trust_assessments"


class TrustSampleRow(RecordColumns, Base):
    __tablename__ = "trust_samples"


class TrustEpisodeRow(RecordColumns, Base):
    __tablename__ = "trust_episodes"
