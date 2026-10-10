import hashlib
import json

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from app.clients.common import ProviderError
from app.models import data as models
from app.models import data_tables as tables

MAPPING = {
    model: getattr(tables, model.__name__ + "Row")
    for model in (
        models.TrackedAsset,
        models.Issuer,
        models.TokenMetadata,
        models.TokenObservation,
        models.EquityObservation,
        models.NewsEvent,
        models.MarketStatus,
    )
}


class DataRepository:
    def __init__(self, database):
        self.database = database

    def save(self, records):
        inserted = 0
        with self.database.sessions.begin() as session:
            for record in records:
                table = MAPPING[type(record)]
                payload = record.model_dump(mode="json")
                ticker = getattr(record, "ticker", "")
                identity = [
                    record.data_mode,
                    record.source,
                    ticker,
                    record.provider_identifier,
                    record.raw_source_timestamp,
                    getattr(record, "kind", None),
                    getattr(record, "interval", None),
                ]
                if isinstance(record, (models.TokenMetadata, models.Issuer)):
                    # Version metadata/ratios; the receive time alone is not a new version.
                    fingerprint = {
                        k: v
                        for k, v in payload.items()
                        if k
                        not in {
                            "ingestion_timestamp",
                            "source_timestamp",
                            "raw_source_timestamp",
                            "data_quality",
                        }
                    }
                    identity.append(fingerprint)
                key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
                existing = session.get(table, key)
                if existing:
                    if isinstance(
                        record,
                        (models.TokenObservation, models.EquityObservation, models.NewsEvent),
                    ):
                        # Normalize additive defaults in older JSON records before comparison.
                        old = (
                            type(record)
                            .model_validate_json(existing.payload)
                            .model_dump(mode="json")
                        )
                        excluded = {"ingestion_timestamp", "data_quality"}
                        if {k: v for k, v in old.items() if k not in excluded} != {
                            k: v for k, v in payload.items() if k not in excluded
                        }:
                            raise ProviderError(record.source, "CONFLICTING_OBSERVATION")
                    continue
                session.add(
                    table(
                        id=key,
                        data_mode=record.data_mode,
                        ticker=ticker,
                        provider=record.source,
                        source_timestamp=record.source_timestamp.isoformat()
                        if record.source_timestamp
                        else None,
                        ingestion_timestamp=record.ingestion_timestamp.isoformat(),
                        payload=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    )
                )
                inserted += 1
        return inserted

    def list(self, model, *, mode, ticker=None, limit=1000):
        if mode not in {"DEMO", "LIVE"} or not 1 <= limit <= 1000:
            raise ValueError("Explicit valid data mode and bounded limit required")
        table = MAPPING[model]
        query = (
            select(table)
            .where(table.data_mode == mode)
            .order_by(table.ingestion_timestamp.desc(), table.id)
            .limit(limit)
        )
        if ticker is not None:
            query = query.where(table.ticker == ticker)
        with self.database.sessions() as session:
            return [model.model_validate_json(row.payload) for row in session.scalars(query)]

    def checkpoint(self, *, mode, resource, cursor, received):
        key = hashlib.sha256((mode + resource).encode()).hexdigest()
        table = tables.IngestionCheckpointRow
        values = dict(
            id=key,
            data_mode=mode,
            ticker=resource,
            provider="INGESTION",
            source_timestamp=None,
            ingestion_timestamp=received.isoformat(),
            payload=json.dumps({"cursor": cursor}),
        )
        with self.database.engine.begin() as connection:
            connection.execute(
                insert(table)
                .values(**values)
                .on_conflict_do_update(index_elements=["id"], set_=values)
            )

    def resume(self, *, mode, resource):
        key = hashlib.sha256((mode + resource).encode()).hexdigest()
        with self.database.sessions() as session:
            row = session.get(tables.IngestionCheckpointRow, key)
            return json.loads(row.payload)["cursor"] if row else None
