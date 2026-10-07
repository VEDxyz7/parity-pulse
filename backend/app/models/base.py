from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SchemaMetadata(Base):
    """A deterministic bootstrap revision, not a financial/business record."""

    __tablename__ = "schema_metadata"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(64), nullable=False)
