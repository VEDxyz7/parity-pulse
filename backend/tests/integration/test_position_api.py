"""Real application lifespan restart against temporary durable stores; no network providers."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import ROOT_DIR, Settings
from app.main import create_app
from app.repositories.position import PositionStore
from app.services.position import change
from backend.tests.fixtures.execution_fixtures import NOW, allowance, evidence, funding, mutate
from backend.tests.integration.test_settlement_remediation import existing, filled, observe
from backend.tests.unit.test_position import (
    ReverseProvider,
    exit_inputs,
    instrument,
    reopen,
    runtime,
)


def settings(tmp_path, **changes):
    return Settings(
        _env_file=None,
        app_env="development",
        runtime_mode="LIVE",
        data_mode="DEMO",
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        log_level="WARNING",
        **changes,
    )


def test_durable_app_restart_and_readonly_api_keep_all_execution_gates(tmp_path, monkeypatch):
    time = [NOW]

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return time[0].astimezone(tz) if tz else time[0].replace(tzinfo=None)

    monkeypatch.setattr("app.main.datetime", FixedClock)
    config = settings(tmp_path)
    with TestClient(create_app(config)) as client:
        manager = client.app.state.positions
        manager.clock = lambda: NOW
        provider, temporary, a = existing()
        client.app.state.execution_store.save(a)
        a = observe(provider, client.app.state.execution_store, a, filled(a))
        p = manager.create(a.execution_id, instrument())
        temporary.close()
        response = client.get("/api/positions")
        assert response.status_code == 200 and response.json()[0]["state"] == "OPEN"
        before = client.get("/api/system-status").json()["gates"]
        assert client.post(f"/api/positions/{p.position_id}/exit").status_code in {404, 405}
    time[0] = p.exit_due_at
    with TestClient(create_app(config)) as client:
        # Startup recovers the verified settlement and marks the deterministic exit due.
        response = client.get(f"/api/positions/{p.position_id}")
        assert response.status_code == 200 and response.json()["state"] == "EXIT_PENDING"
        assert response.json()["entry_execution"]["execution_id"] == str(a.execution_id)
        assert response.json()["remaining_quantity_base_units"] == "400000"
        assert response.json()["job"]["job_id"] == str(p.job.job_id)
        assert client.get("/api/system-status").json()["gates"] == before
        assert client.get("/api/positions?limit=1001").status_code == 422
        assert client.get("/api/positions/00000000-0000-4000-8000-000000000001").status_code == 404
    assert (tmp_path / "positions/phase10/DEMO/positions.sqlite").is_file()


def test_demo_runtime_never_uses_or_writes_canonical_position_store(tmp_path):
    config = Settings(
        _env_file=None,
        app_env="test",
        runtime_mode="DEMO",
        data_mode="DEMO",
        database_url=f"sqlite:///{tmp_path / 'must_not_exist.db'}",
        log_level="WARNING",
    )
    with TestClient(create_app(config)) as client:
        assert client.get("/api/positions").json() == []
        assert client.app.state.demo_paper is not None
    assert list(tmp_path.iterdir()) == []


def test_live_readonly_mode_cannot_see_synthetic_canonical_positions(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.get("/api/positions").json() == []
    config = Settings(
        _env_file=None,
        app_env="development",
        runtime_mode="LIVE",
        data_mode="LIVE_READ_ONLY",
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        log_level="WARNING",
    )
    with TestClient(create_app(config)) as client:
        assert client.get("/api/positions").json() == []
        assert client.app.state.positions.mode == "LIVE_READ_ONLY"
    assert (tmp_path / "positions/phase10/LIVE_READ_ONLY/positions.sqlite").is_file()


def test_production_refuses_memory_storage_and_live_enablement():
    for kwargs in (
        dict(app_env="production", database_url="sqlite:///:memory:"),
        dict(execution_mode="LIVE"),
        dict(live_trading_enabled=True),
        dict(require_simulation=False),
        dict(approval_mode="AUTONOMOUS"),
    ):
        with pytest.raises(ValueError):
            Settings(_env_file=None, **kwargs)


def test_restart_between_exit_preparation_and_position_link_finds_same_decision(
    tmp_path, monkeypatch
):
    manager, p, time = runtime(tmp_path)
    time[0] = p.exit_due_at
    provider = ReverseProvider(clock=lambda: time[0])
    manager.execution.provider = provider
    manager.execution.quotes.provider = provider
    manager.execution.simulator.provider = provider
    original = manager._save

    def crash(old, **updates):
        if updates.get("exit_intent") is not None and updates["exit_intent"].execution is not None:
            raise SystemExit("simulated crash after execution decision claimed")
        return original(old, **updates)

    monkeypatch.setattr(manager, "_save", crash)
    with pytest.raises(SystemExit):
        manager.prepare_exit(p.position_id, **exit_inputs(manager, p, time))
    decision = manager.exit_decision_id(p.position_id)
    attempt = manager.execution.store.for_decision(decision, mode="DEMO")
    assert attempt is not None
    manager = reopen(manager, tmp_path, time, provider)
    calls = len(provider.calls)
    manager.recover()
    restored = manager.store.get(p.position_id, mode="DEMO")
    assert restored.exit_intent.execution.execution_id == attempt.execution_id
    assert len(provider.calls) == calls
    assert manager.prepare_exit(p.position_id, **exit_inputs(manager, restored, time)) == restored
    assert len(provider.calls) == calls


def test_restart_keeps_unknown_until_confirmed_and_blocks_dependent_execution(tmp_path):
    manager, p, time = runtime(tmp_path, confirmed=False)
    manager = reopen(manager, tmp_path, time)
    manager.recover()
    p = manager.store.get(p.position_id, mode="DEMO")
    assert p.state == "UNKNOWN" and manager.has_unresolved()
    a = manager.execution.prepare(
        evidence(decision_id="new_entry"),
        funding(),
        target_contract=instrument().contract,
        allowance=None,
        correlation_id="restart",
    )
    assert a.state == "BLOCKED" and "POSITION_STATE_UNRESOLVED" in a.reason_codes
    provider, temporary, _ = existing()
    temporary.close()
    provider.order_status = lambda _: (filled(p.entry_execution), time[0])
    manager.execution.provider = provider
    assert manager.reconcile(p.position_id).state == "OPEN"


def test_calendar_change_after_restart_does_not_shift_exit_policy(tmp_path):
    manager, p, time = runtime(tmp_path)
    manager = reopen(manager, tmp_path, time)
    manager.calendar.data["version"] = "different_calendar"
    manager.recover()
    restored = manager.store.get(p.position_id, mode="DEMO")
    assert restored.state == "RECONCILIATION_REQUIRED"
    assert restored.exit_due_at == p.exit_due_at and manager.has_unresolved()


def test_exhausted_status_job_does_not_resume_automatic_retry_on_restart(tmp_path):
    manager, p, time = runtime(tmp_path, confirmed=False)
    manager.execution.provider = None
    for i in range(3):
        time[0] = NOW + timedelta(seconds=60 * i)
        manager.tick()
    manager = reopen(manager, tmp_path, time)
    assert manager.recover() == []
    assert manager.store.get(p.position_id, mode="DEMO").job.attempts == 3


def test_exit_requires_current_safe_funding_identity_and_notional():
    manager, p, time = runtime()
    time[0] = p.exit_due_at
    for field, value in (("wallet", "0x" + "9" * 40), ("unit_price_usd", "99")):
        inputs = exit_inputs(manager, p, time)
        inputs["funding_state"] = mutate(inputs["funding_state"], **{field: value})
        with pytest.raises(ValueError):
            manager.prepare_exit(p.position_id, **inputs)


def test_two_durable_workers_cannot_claim_the_same_position_job(tmp_path):
    manager, p, _ = runtime(tmp_path)
    second = PositionStore(manager.execution.store, tmp_path / "positions")

    def claim(store):
        candidate = change(
            p,
            version=1,
            job=change(
                p.job, status="RUNNING", lease_id=uuid4(), lease_until=NOW + timedelta(seconds=30)
            ),
        )
        try:
            store.save(candidate, expected_version=0)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, [manager.store, second]))
    assert sorted(results) == [False, True]
    restored = manager.store.get(p.position_id, mode="DEMO")
    assert restored.version == 1 and restored.job.status == "RUNNING"
    second.close()


def test_lease_loser_cannot_read_status_or_prepare_execution(tmp_path):
    manager, p, time = runtime(tmp_path, confirmed=False)
    manager._save(
        p,
        job=change(
            p.job, status="RUNNING", lease_id=uuid4(), lease_until=NOW + timedelta(seconds=30)
        ),
    )
    manager.execution.provider.order_status = lambda _: pytest.fail(
        "Owned monitor lease cannot poll twice"
    )
    assert manager.tick() == []
    assert manager.has_unresolved()


def test_confirmed_exit_hash_conflict_preserves_holding_and_blocks_close():
    from backend.tests.unit.test_position import prepare_exit

    manager, p, time = runtime()
    p, provider = prepare_exit(manager, p, time, execution_mode="RFQ")
    a = p.exit_intent.execution
    imported = mutate(
        a,
        external_tracking_only=True,
        state="EXECUTION_PENDING",
        order_id="exit_conflict",
        tx_hash="0x" + "6" * 64,
        version=a.version + 1,
    )
    manager.execution.store.save(imported, expected_version=a.version)
    provider.order_status = lambda _: (
        filled(
            imported,
            createdAt=int(time[0].timestamp() * 1000),
            filledAt=int(time[0].timestamp() * 1000),
        ),
        time[0],
    )
    result = manager.reconcile(p.position_id)
    assert result.state == "RECONCILIATION_REQUIRED" and result.closed_at is None
    assert result.remaining_quantity_base_units == "400000" and not result.applied_exit_executions
    assert result.exit_intent.execution.tx_hash == "0x" + "6" * 64
    assert manager.has_unresolved()


def test_recovery_batch_limit_keeps_dependent_execution_blocked():
    manager, p, _ = runtime()
    manager.recovery_complete = False
    assert manager.has_unresolved()
    assert manager.recover(limit=1)
    assert manager.recovery_complete
    for value in (0, 1001, True):
        with pytest.raises(ValueError):
            manager.tick(limit=value)


def test_exit_after_the_scheduled_regular_session_is_blocked():
    manager, p, time = runtime()
    time[0] = p.exit_due_at + timedelta(hours=7)
    with pytest.raises(ValueError, match="NOT_SAFE_OR_NOT_DUE"):
        manager.prepare_exit(p.position_id, **exit_inputs(manager, p, time))
    assert manager.store.get(p.position_id, mode="DEMO").remaining_quantity_base_units == "400000"


def test_proposal_requote_cannot_rebind_an_existing_position():
    from app.services.position import PositionService
    from backend.tests.unit.test_agentic_wallet import prepared

    execution, a = prepared()
    manager = PositionService(PositionStore(execution.store), execution, clock=lambda: NOW)
    manager.recover()
    p = manager.create(a.execution_id, instrument())
    execution.requote(a, funding_state=funding(), allowance=allowance())
    manager.tick()
    assert manager.store.get(p.position_id, mode="DEMO").state == "RECONCILIATION_REQUIRED"
    assert manager.has_unresolved()


def test_durable_position_is_restored_by_a_separate_python_process(tmp_path):
    manager, p, _ = runtime(tmp_path)
    manager.store.close()
    manager.execution.store.close()
    code = """
import json, sys
from pathlib import Path
from app.repositories.execution import ExecutionStore
from app.repositories.position import PositionStore
root = Path(sys.argv[1])
execution = ExecutionStore(root / "execution")
positions = PositionStore(execution, root / "positions")
p = positions.get(sys.argv[2], mode="DEMO")
print(json.dumps({"state": p.state, "quantity": p.remaining_quantity_base_units,
    "execution": str(p.entry_execution.execution_id), "job": str(p.job.job_id)}))
positions.close()
execution.close()
"""
    child = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path), str(p.position_id)],
        cwd=ROOT_DIR,
        env={"PYTHONPATH": str(ROOT_DIR / "backend"), "PATH": os.environ.get("PATH", "")},
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert json.loads(child.stdout) == dict(
        state="OPEN",
        quantity="400000",
        execution=str(p.entry_execution.execution_id),
        job=str(p.job.job_id),
    )


def test_exit_preparation_retains_phase9_wallet_controls_and_hard_live_stop():
    from app.clients.execution_gateway import AgenticWalletCliGateway
    from app.services.agentic_wallet import AgenticWalletAdapter
    from backend.tests.unit.test_position import prepare_exit

    manager, p, time = runtime()
    manager.execution.gateway = AgenticWalletCliGateway(
        manager.execution.controls, AgenticWalletAdapter(data_mode="DEMO", clock=manager.clock)
    )
    result, _ = prepare_exit(manager, p, time)
    reasons = result.exit_intent.execution.reason_codes
    assert "WALLET_EXECUTION_DISABLED" in reasons
    assert "AGENTIC_WALLET_LIVE_GATE_BLOCKED" in reasons
    assert "DRY_RUN_STOP_NO_EXECUTION" in reasons
    assert result.state == "EXIT_PENDING" and result.remaining_quantity_base_units == "400000"
