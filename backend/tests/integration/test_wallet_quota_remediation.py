"""Developer date enforcement through adapter/CLI/gateway, with an injected clock."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.clients.baw_cli import WalletReadError
from app.clients.execution_gateway import AgenticWalletCliGateway
from app.models.execution import ExecutionControls
from app.services.agentic_wallet import AgenticWalletAdapter
from backend.tests.fixtures.execution_fixtures import NOW, funding
from backend.tests.fixtures.wallet_fixtures import WalletWire
from backend.tests.unit.test_agentic_wallet import prepared


def gateway(wire, *, now=NOW):
    _, attempt = prepared()
    wire.clock = lambda: now
    adapter = AgenticWalletAdapter(wire, data_mode="DEMO", clock=lambda: now)
    return AgenticWalletCliGateway(ExecutionControls(data_mode="DEMO"), adapter).dry_run(
        attempt, now=now, funding_state=funding()
    )


def quota_passed(result):
    return next(c.passed for c in result.wallet.checks if c.code == "WALLET_QUOTA_DATE_CURRENT")


def test_valid_developer_quota_date_reaches_actual_gateway_without_execution():
    w = WalletWire()
    result = gateway(w)
    assert result.wallet.status == "PASS" and quota_passed(result)
    assert any(c[:2] == ("wallet", "settings") for c in w.calls)
    assert not result.execution_ready and not result.signed and not result.broadcast


@pytest.mark.parametrize("offset", [-1, 1])
def test_stale_or_future_developer_date_alone_blocks_actual_gateway(offset):
    w = WalletWire()
    w.values["settings"]["developerModeQuotaDate"] = (
        (NOW + timedelta(days=offset)).date().isoformat()
    )
    # Market quota date remains valid: this assertion specifically kills the old mutation.
    assert w.values["settings"]["quotaDate"] == NOW.date().isoformat()
    result = gateway(w)
    assert result.wallet.status == "BLOCKED" and not quota_passed(result)
    assert "WALLET_QUOTA_DATE_CURRENT" in result.reasons
    assert not result.execution_ready


@pytest.mark.parametrize("value", [None, "not-a-date", "2026-13-01", "2026-10-08T00:00:00Z", 0])
def test_missing_or_malformed_developer_metadata_is_unavailable_at_gateway(value):
    w = WalletWire()
    if value is None:
        del w.values["settings"]["developerModeQuotaDate"]
    else:
        w.values["settings"]["developerModeQuotaDate"] = value
    result = gateway(w)
    assert result.wallet.status == "BLOCKED" and "WALLET_AVAILABLE" in result.reasons
    assert not result.execution_ready


@pytest.mark.parametrize(
    "asof,current",
    [
        (datetime(2030, 1, 1, 23, 59, 59, tzinfo=UTC), True),
        (datetime(2030, 1, 2, 0, 0, 0, tzinfo=UTC), False),
    ],
)
def test_utc_midnight_developer_date_boundary_is_consumed_by_gateway(asof, current):
    w = WalletWire()
    w.values["settings"]["quotaDate"] = asof.date().isoformat()
    w.values["settings"]["developerModeQuotaDate"] = "2030-01-01"
    result = gateway(w, now=asof)
    assert quota_passed(result) is current
    if not current:
        assert "WALLET_QUOTA_DATE_CURRENT" in result.reasons
    assert not result.execution_ready


def test_local_date_must_not_substitute_for_utc_date_at_gateway():
    w = WalletWire()
    local = NOW.astimezone(timezone(timedelta(hours=10)))
    assert local.date() != NOW.date()
    assert quota_passed(gateway(w, now=local))
    w.values["settings"]["developerModeQuotaDate"] = local.date().isoformat()
    assert not quota_passed(gateway(w, now=local))


def test_unavailable_settings_blocks_actual_gateway_and_does_not_mutate_wallet():
    w = WalletWire()
    w.failure = WalletReadError("WALLET_READ_TIMEOUT")
    result = gateway(w)
    assert result.wallet.status == "BLOCKED" and "WALLET_AVAILABLE" in result.reasons
    assert not result.signed and not result.broadcast and not result.funds_moved
    assert all(c[0] in {"cli-check", "wallet", "market-order"} for c in w.calls)
