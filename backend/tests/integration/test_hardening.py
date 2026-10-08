"""Phase 16 adversarial checks: isolated state, no credentials or real provider calls."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import select

from app.database import Database
from app.models.base import SchemaMetadata
from app.repositories.opportunity_scan import OpportunityScanStore
from backend.tests.integration.test_agent_api import agent as agent
from backend.tests.integration.test_scorecard import scoring as scoring
from backend.tests.unit.test_opportunity_scan import changed, scan


@pytest.mark.parametrize("commit", [True, False])
def test_health_cannot_rollback_or_read_another_session_transaction(commit):
    db = Database("sqlite:///:memory:")
    db.initialize()
    entered = Event()

    def health():
        entered.set()
        return db.healthy()

    with ThreadPoolExecutor(max_workers=1) as workers:
        with db.sessions() as session:
            session.add(SchemaMetadata(key="owned-transaction", value="must-survive"))
            session.flush()
            future = workers.submit(health)
            assert entered.wait(2)
            # A second checkout must wait; sharing the same active DBAPI connection
            # would let health close/rollback the writer's transaction.
            with pytest.raises(TimeoutError):
                future.result(timeout=0.05)
            if commit:
                session.commit()
            else:
                session.rollback()
        assert future.result(timeout=3) is True
    with db.sessions() as session:
        row = session.scalar(
            select(SchemaMetadata).where(SchemaMetadata.key == "owned-transaction")
        )
        assert (row is not None) is commit
        if commit:
            assert row.value == "must-survive"
    db.close()


@pytest.mark.parametrize("disk", [False, True])
def test_simultaneous_immutable_scan_writes_are_idempotent(tmp_path, disk):
    result = scan()
    stores = [OpportunityScanStore(tmp_path / "scans" if disk else None) for _ in range(4)]
    targets = stores if disk else [stores[0]] * 4
    with ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(lambda store: store.save(result), targets * 3))
    assert targets[0].list(mode="DEMO") == (result,)
    with pytest.raises(ValueError, match="Conflicting"):
        targets[0].save(changed(result, blockers=("CONFLICT",)))
    assert targets[0].get(result.run_id, mode="DEMO") == result
    for store in stores:
        store.close()


@pytest.mark.parametrize("memory", [False, True])
def test_concurrent_status_polling_does_not_corrupt_or_report_false_health(tmp_path, memory):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite:///:memory:" if memory else f"sqlite:///{tmp_path}/poll.db",
        )
    )
    with TestClient(app) as client:
        paths = ["/api/health", "/api/system-status", "/api/workspace", "/api/agent/tools"] * 12
        with ThreadPoolExecutor(max_workers=12) as workers:
            responses = list(workers.map(client.get, paths))
        assert all(r.status_code == 200 for r in responses)
        assert all(
            r.json()["database_status"] == "connected"
            for r in responses
            if "database_status" in r.json()
        )
        workspace = client.get("/api/workspace").json()
        assert workspace["production_gates"]["TRUST_GATE"] == "BLOCKED"
        assert workspace["production_gates"]["OPPORTUNITY_GATE"] == "BLOCKED_BY_TRUST"
        assert workspace["broadcast"] is False
        assert app.state.database.healthy()


def test_repeated_confirmations_only_one_version_can_be_accepted():
    from datetime import timedelta

    from app.models.execution import UserConfirmation
    from backend.tests.fixtures.execution_fixtures import NOW
    from backend.tests.unit.test_execution_safety import prepared

    s, a = prepared()
    confirmation = UserConfirmation(
        route_fingerprint=a.route.fingerprint,
        decision_id=a.decision_id,
        confirmed_at=NOW,
        expires_at=NOW + timedelta(seconds=20),
        source="HOST_EXPLICIT_USER_CONFIRMATION",
    )

    def confirm(_):
        try:
            return s.confirm(a, confirmation)
        except ValueError as error:
            assert str(error) == "INVALID_OR_STALE_EXPLICIT_CONFIRMATION"
            return None

    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(confirm, range(8)))
    accepted = [r for r in results if r is not None]
    assert len(accepted) == 1
    assert s.store.get(a.execution_id, mode="DEMO").version == a.version + 1
    assert "SWAP_LIVE_GATE_BLOCKED" in s.gateway.submit(
        accepted[0],
        now=NOW,
        funding_state=__import__(
            "backend.tests.fixtures.execution_fixtures", fromlist=["funding"]
        ).funding(),
    )
    assert not any(c[0] in {"sign", "broadcast", "submit"} for c in s.provider.calls)
    s.store.close()


def test_quote_refresh_and_duplicate_preparation_share_one_execution_intent():
    from backend.tests.fixtures.execution_fixtures import BUY, allowance, evidence, funding
    from backend.tests.unit.test_execution_safety import prepared

    s, a = prepared()
    s.clock.advance(31)
    with ThreadPoolExecutor(max_workers=2) as workers:
        refresh = workers.submit(s.requote, a, funding_state=funding(), allowance=allowance())
        retry = workers.submit(
            s.prepare,
            evidence(),
            funding(),
            target_contract=BUY,
            allowance=allowance(),
            correlation_id="duplicate",
        )
        refreshed, retried = refresh.result(), retry.result()
    current = s.store.get(a.execution_id, mode="DEMO")
    assert refreshed.execution_id == retried.execution_id == current.execution_id == a.execution_id
    assert current.generation == 1 and current.user_confirmation is None
    assert current.simulation.fingerprint == current.route.fingerprint
    assert current.route.fingerprint != a.route.fingerprint
    assert sum(c[0] == "quote" for c in s.provider.calls) == 2
    assert not any(c[0] in {"sign", "broadcast", "submit"} for c in s.provider.calls)
    s.store.close()


@pytest.mark.parametrize(
    "stage,state",
    [
        ("quote", "RISK_APPROVED"),
        ("build", "QUOTE_CREATED"),
        ("simulate", "ROUTE_BUILT"),
        ("approval", "APPROVAL_REQUIRED"),
    ],
)
def test_restart_during_preparation_retains_identity_without_resubmission(tmp_path, stage, state):
    from app.repositories.execution import ExecutionStore
    from backend.tests.fixtures.execution_fixtures import (
        BUY,
        FixtureProvider,
        allowance,
        evidence,
        funding,
    )
    from backend.tests.unit.test_execution_safety import service

    provider = FixtureProvider()

    def interrupt(*args, **kwargs):
        raise SystemExit("INJECTED_PROCESS_INTERRUPTION")

    setattr(provider, stage, interrupt)
    store = ExecutionStore(tmp_path / "execution")
    s = service(store=store, provider=provider)
    with pytest.raises(SystemExit, match="INJECTED"):
        s.prepare(
            evidence(),
            funding(),
            target_contract=BUY,
            allowance=allowance("0") if stage == "approval" else allowance(),
            correlation_id="restart",
        )
    old = store.for_decision(evidence().decision_id, mode="DEMO")
    assert old.state == state
    store.close()
    reopened = ExecutionStore(tmp_path / "execution")
    fresh = FixtureProvider()
    s = service(store=reopened, provider=fresh)
    recovered = s.prepare(
        evidence(), funding(), target_contract=BUY, allowance=allowance(), correlation_id="retry"
    )
    assert recovered == old
    assert fresh.calls == []
    assert recovered.state not in {"EXECUTION_SUBMITTED", "EXECUTION_CONFIRMED"}
    assert recovered.user_confirmation is None
    reopened.close()


def test_scheduler_and_manual_exit_prepare_only_one_intent(tmp_path):
    from backend.tests.unit.test_position import ReverseProvider, exit_inputs, runtime

    manager, p, time = runtime(tmp_path)
    time[0] = p.exit_due_at
    provider = ReverseProvider(clock=lambda: time[0])
    manager.execution.provider = manager.execution.quotes.provider = (
        manager.execution.simulator.provider
    ) = provider
    with ThreadPoolExecutor(max_workers=3) as workers:
        monitoring = workers.submit(manager.tick)

        def guarded_exit():
            try:
                return manager.prepare_exit(p.position_id, **exit_inputs(manager, p, time))
            except ValueError as error:
                # Active persisted monitor leases intentionally block manual preparation.
                assert str(error) == "POSITION_EXIT_NOT_SAFE_OR_NOT_DUE"
                return None

        exits = [workers.submit(guarded_exit) for _ in range(2)]
        monitoring.result()
        prepared_exits = [r for f in exits if (r := f.result()) is not None]
    prepared_exits.append(manager.prepare_exit(p.position_id, **exit_inputs(manager, p, time)))
    current = manager.store.get(p.position_id, mode="DEMO")
    assert len({r.exit_intent.execution.execution_id for r in prepared_exits}) == 1
    assert current.remaining_quantity_base_units == p.remaining_quantity_base_units
    assert current.state == "EXIT_PENDING"
    assert sum(c[0] == "quote" for c in provider.calls) == 1
    assert not any(c[0] in {"sign", "broadcast", "submit"} for c in provider.calls)
    manager.store.close()
    manager.execution.store.close()


@pytest.mark.parametrize("tool", ["buy_stock_exposure", "find_opportunity"])
def test_concurrent_tool_deliveries_have_one_decision_and_no_execution(agent, tool):
    from threading import Barrier

    from backend.tests.integration.test_agent_api import NOW, arguments, invoke

    body = arguments(tool)
    barrier = Barrier(8)

    def delivery(_):
        barrier.wait(timeout=5)
        return invoke(agent, tool, body)

    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(delivery, range(8)))
    completed = [r for r in results if r.error is None]
    assert completed and len({r.decision_id for r in completed}) == 1
    assert all(r.error is None or r.error.code == "RECONCILIATION_REQUIRED" for r in results)
    retry = invoke(agent, tool, body)
    assert retry.replayed is True and retry.decision_id == completed[0].decision_id
    if tool == "buy_stock_exposure":
        assert len(agent[1].exposure.repository.list_original("DEMO", NOW)) == 1
    else:
        assert len(agent[1].opportunity_scan_store.list(mode="DEMO")) == 1
    assert all(r.transaction_broadcast is False and r.execution_ready is False for r in results)
    assert all(
        getattr(agent[1].safety_execution, method).call_count == 0
        for method in ("prepare", "confirm", "prepare_rfq_submission", "requote")
    )


def test_multiple_mcp_requests_preserve_contract_and_authority(agent):
    import asyncio

    import httpx
    from mcp import Client

    from app.mcp_server import create_server
    from app.models.agent_api import ToolResult

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=agent[0].app, client=("127.0.0.1", 123)),
            base_url="http://127.0.0.1:8000",
        ) as http:
            async with Client(create_server(http)) as client:
                results = await asyncio.gather(
                    *[client.call_tool("get_portfolio", {}) for _ in range(8)]
                )
                bodies = [ToolResult.model_validate(r.structured_content) for r in results]
                assert all(not r.is_error for r in results)
                assert len({r.request_id for r in bodies}) == 8
                assert all(not r.transaction_broadcast and not r.execution_ready for r in bodies)
                assert all(r.gates.OPPORTUNITY_GATE == "BLOCKED_BY_TRUST" for r in bodies)

    asyncio.run(exercise())


def test_interrupted_data_refresh_rolls_back_without_advancing_checkpoint(tmp_path):
    from sqlalchemy import event

    from app.models.data import TrackedAsset
    from app.providers.demo import load_data_fixture
    from app.repositories.data import DataRepository

    path = f"sqlite:///{tmp_path}/refresh.db"
    db = Database(path)
    db.initialize()
    repository = DataRepository(db)
    records = load_data_fixture()["assets"]
    assert len(records) >= 2
    inserts = []

    def crash(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO tracked_assets"):
            inserts.append(statement)
            if len(inserts) == 2:
                raise SystemExit("REFRESH_INTERRUPTED")

    event.listen(db.engine, "before_cursor_execute", crash)
    with pytest.raises(SystemExit, match="REFRESH_INTERRUPTED"):
        repository.save(records)
    db.close()
    reopened = Database(path)
    reopened.initialize()
    repository = DataRepository(reopened)
    assert repository.list(TrackedAsset, mode="DEMO") == []
    assert repository.resume(mode="DEMO", resource="refresh") is None
    assert repository.save(records) == len(records)
    assert repository.save(records) == 0
    assert len(repository.list(TrackedAsset, mode="DEMO")) == len(records)
    reopened.close()


@pytest.mark.parametrize("stage", ["scan", "agents"])
def test_interrupted_scan_or_agents_leave_durable_receipt_without_retry(
    agent, tmp_path, monkeypatch, stage
):
    import asyncio
    from uuid import uuid4

    from app.repositories.agent_api import ToolReceipts
    from backend.tests.integration.test_agent_api import arguments, invoke
    from backend.tests.unit.test_opportunity_scan import snapshot

    receipts = ToolReceipts(tmp_path / "interrupted")
    api = agent[1].agent_api
    api.receipts = receipts
    monkeypatch.setattr(agent[1].opportunity_source, "capture", lambda *args: snapshot())

    async def interrupt(*args, **kwargs):
        raise asyncio.CancelledError("HOST_PROCESS_INTERRUPTED")

    target = agent[1].opportunity_scan if stage == "scan" else agent[1].opportunity_scan.agents
    monkeypatch.setattr(target, "scan" if stage == "scan" else "analyze", interrupt)
    body = {**arguments("find_opportunity"), "budget_usd": "60", "risk_budget_usd": "2"}
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            api.call(
                "find_opportunity",
                body,
                request_id=str(uuid4()),
                correlation_id=str(uuid4()),
                run_id="INTERRUPTED",
            )
        )
    assert agent[1].opportunity_scan_store.list(mode="DEMO") == ()
    receipts.close()
    api.receipts = ToolReceipts(tmp_path / "interrupted")
    try:
        result = invoke(agent, "find_opportunity", body)
        assert result.error.code == "RECONCILIATION_REQUIRED"
        assert agent[1].opportunity_scan_store.list(mode="DEMO") == ()
        assert not result.transaction_broadcast and not result.execution_ready
    finally:
        api.receipts.close()


def test_interrupted_scorecard_append_is_atomic_after_restart(scoring, tmp_path):
    from sqlalchemy import event

    from app.models.scorecard import AuditEvent, Scorecard
    from app.repositories.scorecard import ScorecardStore
    from backend.tests.integration.test_scorecard import ask

    client, service = scoring
    ask(client)
    cards = service.capture()
    events = service.events(cards)
    assert cards and events
    store = ScorecardStore(tmp_path / "interrupted-evaluation")

    def interrupt(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT OR IGNORE INTO scorecards"):
            raise SystemExit("SCORECARD_INTERRUPTED_AFTER_EVENTS")

    event.listen(store.engine, "before_cursor_execute", interrupt)
    with pytest.raises(SystemExit, match="SCORECARD_INTERRUPTED"):
        store.append(cards, events)
    store.close()
    reopened = ScorecardStore(tmp_path / "interrupted-evaluation")
    try:
        assert reopened.list(Scorecard, mode="DEMO") == ()
        assert reopened.list(AuditEvent, mode="DEMO") == ()
        reopened.append(cards, events)
        reopened.append(cards, events)
        assert reopened.list(Scorecard, mode="DEMO") == cards
        assert len(reopened.list(AuditEvent, mode="DEMO")) == len(events)
    finally:
        reopened.close()


def test_repeated_verified_allowance_observations_rebuild_and_simulate_once():
    from threading import Barrier

    from backend.tests.fixtures.execution_fixtures import allowance, funding
    from backend.tests.unit.test_execution_safety import prepared

    service, original = prepared(balance="0")
    assert original.state == "APPROVAL_REQUIRED"
    assert original.approval_simulation.status == "PASS"
    barrier = Barrier(8)

    def observe(_):
        barrier.wait(timeout=5)
        try:
            return service.observe_approval(
                original, allowance(original.approval.amount), funding_state=funding()
            )
        except ValueError as error:
            assert str(error) in {"APPROVAL_STATE_MISMATCH", "STALE_OR_EXHAUSTED_REQUOTE_ATTEMPT"}
            return None

    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(observe, range(8)))
    accepted = [r for r in results if r is not None]
    assert len(accepted) == 1
    current = service.store.get(original.execution_id, mode="DEMO")
    assert current.state == "APPROVAL_CONFIRMED" and current.generation == 1
    assert (
        current.request_id == original.request_id and current.execution_id == original.execution_id
    )
    assert current.simulation.fingerprint == current.route.fingerprint != original.route.fingerprint
    assert sum(c[0] == "quote" for c in service.provider.calls) == 2
    assert not current.broadcast and not current.signed and not current.execution_ready
    assert not any(c[0] in {"sign", "broadcast", "submit"} for c in service.provider.calls)
    service.store.close()
