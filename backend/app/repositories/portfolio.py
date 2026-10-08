"""Atomic single-portfolio configuration, decisions, pending intent and structured audit."""

import hashlib
import json
import threading
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, String, Table, Text, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from app.models.portfolio import PortfolioConfig, RebalancePlan


def checksum(payload):
    return hashlib.sha256(payload.encode()).hexdigest()


class PortfolioStore:
    def __init__(self, directory=None):
        self.lock = threading.RLock()
        if directory is None:
            self.engine = create_engine(
                "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
            )
        else:
            directory = Path(directory)
            directory.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine(f"sqlite:///{directory / 'portfolio.sqlite'}")
        metadata = MetaData()
        self.configs = Table(
            "portfolio_config",
            metadata,
            Column("mode", String, primary_key=True),
            Column("version", Integer, nullable=False),
            Column("payload", Text, nullable=False),
            Column("digest", String, nullable=False),
        )
        self.plans = Table(
            "portfolio_plans",
            metadata,
            Column("plan_id", String, primary_key=True),
            Column("mode", String, nullable=False),
            Column("active_mode", String, unique=True),
            Column("version", Integer, nullable=False),
            Column("payload", Text, nullable=False),
            Column("digest", String, nullable=False),
        )
        self.events = Table(
            "portfolio_audit",
            metadata,
            Column("sequence", Integer, primary_key=True, autoincrement=True),
            Column("mode", String, nullable=False),
            Column("payload", Text, nullable=False),
            Column("digest", String, nullable=False),
        )
        self.requests = Table(
            "portfolio_requests",
            metadata,
            Column("mode", String, primary_key=True),
            Column("key", String, primary_key=True),
            Column("plan_id", String, nullable=False),
        )
        metadata.create_all(self.engine)

    def _audit(self, db, mode, body):
        payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
        db.execute(
            self.events.insert().values(mode=mode, payload=payload, digest=checksum(payload))
        )

    @staticmethod
    def _decode(row, model):
        if checksum(row["payload"]) != row["digest"]:
            raise ValueError("Corrupt portfolio payload")
        result = model.model_validate_json(row["payload"])
        if result.data_mode != row["mode"] or result.version != row["version"]:
            raise ValueError("Portfolio row binding mismatch")
        if model is RebalancePlan and (
            result.plan_id != row["plan_id"]
            or row["active_mode"]
            != (result.data_mode if result.status == "REBALANCE_REQUIRED" else None)
        ):
            raise ValueError("Pending plan binding mismatch")
        return result

    def config(self, *, mode):
        with self.lock, self.engine.connect() as db:
            row = (
                db.execute(select(self.configs).where(self.configs.c.mode == mode))
                .mappings()
                .first()
            )
        return self._decode(row, PortfolioConfig) if row else None

    def set_config(self, config, *, expected_version, request_id, correlation_id):
        config = PortfolioConfig.model_validate_json(config.model_dump_json())
        if config.version != expected_version + 1:
            raise ValueError("Config version must advance once")
        payload = config.model_dump_json()
        values = dict(
            mode=config.data_mode, version=config.version, payload=payload, digest=checksum(payload)
        )
        try:
            with self.lock, self.engine.begin() as db:
                # Acquire the SQLite write lock before checking pending work/config identity.
                if expected_version == 0:
                    db.execute(self.configs.insert().values(**values))
                else:
                    old = (
                        db.execute(
                            select(self.configs).where(self.configs.c.mode == config.data_mode)
                        )
                        .mappings()
                        .first()
                    )
                    if (
                        not old
                        or self._decode(old, PortfolioConfig).created_at != config.created_at
                    ):
                        raise ValueError("Immutable config identity")
                    result = db.execute(
                        self.configs.update()
                        .where(
                            self.configs.c.mode == config.data_mode,
                            self.configs.c.version == expected_version,
                        )
                        .values(**values)
                    )
                    if result.rowcount != 1:
                        raise ValueError("Stale configuration version")
                if db.execute(
                    select(self.plans.c.plan_id).where(self.plans.c.active_mode == config.data_mode)
                ).first():
                    raise ValueError(
                        "Reconcile or safely retire pending rebalance before reconfiguration"
                    )
                self._audit(
                    db,
                    config.data_mode,
                    dict(
                        event="CONFIGURATION",
                        config=config.model_dump(mode="json"),
                        request_id=str(request_id),
                        correlation_id=str(correlation_id),
                        timestamp=config.updated_at.isoformat(),
                    ),
                )
        except IntegrityError:
            raise ValueError("Configuration already exists; use its current version") from None
        return config

    def get(self, plan_id, *, mode):
        with self.lock, self.engine.connect() as db:
            row = (
                db.execute(
                    select(self.plans).where(
                        self.plans.c.plan_id == plan_id, self.plans.c.mode == mode
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise LookupError("Unknown portfolio plan")
        return self._decode(row, RebalancePlan)

    def pending(self, *, mode):
        with self.lock, self.engine.connect() as db:
            row = (
                db.execute(select(self.plans).where(self.plans.c.active_mode == mode))
                .mappings()
                .first()
            )
        return self._decode(row, RebalancePlan) if row else None

    def for_request(self, key, *, mode):
        with self.lock, self.engine.connect() as db:
            plan_id = db.execute(
                select(self.requests.c.plan_id).where(
                    self.requests.c.mode == mode, self.requests.c.key == str(key)
                )
            ).scalar_one_or_none()
        return self.get(plan_id, mode=mode) if plan_id else None

    def claim(self, plan):
        plan = RebalancePlan.model_validate_json(plan.payload())
        with self.lock, self.engine.begin() as db:
            locked = db.execute(
                self.configs.update()
                .where(
                    self.configs.c.mode == plan.data_mode,
                    self.configs.c.version == plan.config.version,
                )
                .values(version=plan.config.version)
            )
            if locked.rowcount != 1:
                raise ValueError("Configuration changed during portfolio capture")
            known = db.execute(
                select(self.requests.c.plan_id).where(
                    self.requests.c.mode == plan.data_mode,
                    self.requests.c.key == str(plan.idempotency_key),
                )
            ).scalar_one_or_none()
            active = db.execute(
                select(self.plans.c.plan_id).where(self.plans.c.active_mode == plan.data_mode)
            ).scalar_one_or_none()
            plan_id = known or active
            if plan_id is None:
                payload = plan.payload()
                row = db.execute(
                    select(self.plans.c.plan_id).where(self.plans.c.plan_id == plan.plan_id)
                ).first()
                if row is None:
                    db.execute(
                        self.plans.insert().values(
                            plan_id=plan.plan_id,
                            mode=plan.data_mode,
                            active_mode=plan.data_mode
                            if plan.status == "REBALANCE_REQUIRED"
                            else None,
                            version=0,
                            payload=payload,
                            digest=checksum(payload),
                        )
                    )
                plan_id = plan.plan_id
            if known is None:
                db.execute(
                    self.requests.insert().values(
                        mode=plan.data_mode, key=str(plan.idempotency_key), plan_id=plan_id
                    )
                )
            self._audit(
                db,
                plan.data_mode,
                dict(
                    event="DECISION"
                    if plan_id == plan.plan_id and not known
                    else "PENDING_PLAN_REUSED",
                    plan_id=plan_id,
                    input_snapshot=plan.snapshot.snapshot_id,
                    config_version=plan.config.version,
                    request_id=str(plan.request_id),
                    correlation_id=str(plan.correlation_id),
                    timestamp=plan.updated_at.isoformat(),
                    reasons=list(plan.reasons),
                    proposed_status=plan.status,
                    captured_inputs=plan.snapshot.model_dump(
                        mode="json", exclude_computed_fields=True
                    ),
                ),
            )
        return self.get(plan_id, mode=plan.data_mode)

    def save(self, plan, *, expected_version):
        plan = RebalancePlan.model_validate_json(plan.payload())
        with self.lock, self.engine.begin() as db:
            row = (
                db.execute(select(self.plans).where(self.plans.c.plan_id == plan.plan_id))
                .mappings()
                .one()
            )
            old = self._decode(row, RebalancePlan)
            if old.version != expected_version or plan.version != expected_version + 1:
                raise ValueError("Stale rebalance plan version")
            for field in (
                "data_mode",
                "config",
                "snapshot",
                "total_value_usd",
                "rows",
                "actions",
                "route_decisions",
                "reasons",
                "idempotency_key",
                "request_id",
                "correlation_id",
                "created_at",
            ):
                if getattr(old, field) != getattr(plan, field):
                    raise ValueError("Immutable rebalance decision inputs")
            if old.status != plan.status and not (
                old.status == "REBALANCE_REQUIRED" and plan.status in {"RETIRED", "COMPLETED"}
            ):
                raise ValueError("Illegal rebalance retirement")
            if old.status != "REBALANCE_REQUIRED" and plan.preparations != old.preparations:
                raise ValueError("Retired decisions cannot gain preparation receipts")
            if (
                old.completion_snapshot != plan.completion_snapshot
                or old.settled_execution_ids != plan.settled_execution_ids
            ) and not (
                old.status == "REBALANCE_REQUIRED"
                and plan.status == "COMPLETED"
                and old.completion_snapshot is None
                and not old.settled_execution_ids
            ):
                raise ValueError("Canonical completion evidence is immutable")
            if (
                plan.preparations[: len(old.preparations)] != old.preparations
                or plan.updated_at < old.updated_at
            ):
                raise ValueError("Preparation receipts are append-only")
            payload = plan.payload()
            result = db.execute(
                self.plans.update()
                .where(
                    self.plans.c.plan_id == plan.plan_id, self.plans.c.version == expected_version
                )
                .values(
                    version=plan.version,
                    active_mode=plan.data_mode if plan.status == "REBALANCE_REQUIRED" else None,
                    payload=payload,
                    digest=checksum(payload),
                )
            )
            if result.rowcount != 1:
                raise ValueError("Concurrent plan update")
            self._audit(
                db,
                plan.data_mode,
                dict(
                    event="PLAN_UPDATE",
                    plan_id=plan.plan_id,
                    version=plan.version,
                    status=plan.status,
                    preparations=[p.model_dump(mode="json") for p in plan.preparations],
                    timestamp=plan.updated_at.isoformat(),
                    completion_snapshot=plan.completion_snapshot.model_dump(
                        mode="json", exclude_computed_fields=True
                    )
                    if plan.completion_snapshot
                    else None,
                    settled_execution_ids=[str(i) for i in plan.settled_execution_ids],
                    request_id=str(plan.request_id),
                    correlation_id=str(plan.correlation_id),
                ),
            )
        return plan

    def audit(self, *, mode, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Bounded audit required")
        with self.lock, self.engine.connect() as db:
            rows = (
                db.execute(
                    select(self.events)
                    .where(self.events.c.mode == mode)
                    .order_by(self.events.c.sequence.desc())
                    .limit(limit)
                )
                .mappings()
                .all()
            )
        for row in rows:
            if checksum(row["payload"]) != row["digest"]:
                raise ValueError("Corrupt portfolio audit")
        return [json.loads(r["payload"]) for r in rows]

    def latest(self, *, mode):
        # Bounded audit reference includes rejected/no-action decisions, not just pending work.
        for event in self.audit(mode=mode):
            if "plan_id" in event:
                return self.get(event["plan_id"], mode=mode)
        return None

    def close(self):
        self.engine.dispose()
