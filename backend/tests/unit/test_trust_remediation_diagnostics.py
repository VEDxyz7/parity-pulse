"""Read-only diagnostics cannot expand production permissions or retain secrets."""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from app.clients.binance_web3 import READ_OPERATIONS
from app.clients.common import ProviderError

spec = importlib.util.spec_from_file_location(
    "trust_remediation_diagnostics",
    Path(__file__).parents[3] / "scripts/verify-trust-remediation.py",
)
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


def test_diagnostic_endpoints_are_isolated_reads_production_allowlist_unchanged():
    assert "token/top-liquidity" not in READ_OPERATIONS["GET"]
    pool = diagnostics.PoolDiagnosticClient(SecretStr("synthetic"), SecretStr("synthetic-secret"))
    trade = diagnostics.TradeDiagnosticClient(SecretStr("synthetic-massive"))
    try:
        pool.authorize("GET", "/api/v1/dex/market/token/top-liquidity")
        trade.authorize("GET", "/v2/last/trade/NVDA")
        for client, method, path in [
            (pool, "POST", "/api/v1/dex/market/token/top-liquidity"),
            (pool, "POST", "/api/v1/dex/aggregator/order/submit"),
            (pool, "GET", "/api/v1/dex/aggregator/swap"),
            (pool, "GET", "/api/v1/dex/balance/supported/chain"),
            (trade, "POST", "/v2/last/trade/NVDA"),
            (trade, "GET", "/v2/last/trade/AAPL"),
        ]:
            with pytest.raises(ProviderError, match="READ_ONLY_OPERATION_REQUIRED"):
                client.authorize(method, path)
    finally:
        pool.close()
        trade.close()


@pytest.mark.parametrize(
    "message,cause",
    [
        ("You are not entitled to this data", "ENTITLEMENT_DENIED"),
        ("Access forbidden", "FORBIDDEN_CAUSE_UNCONFIRMED"),
        ("synthetic-secret", "PAYLOAD_DISCARDED"),
    ],
)
def test_403_diagnostics_retain_only_categorical_status_never_response_text(message, cause):
    ledger = []
    response = httpx.Response(
        403,
        json={
            "status": "NOT_AUTHORIZED",
            "message": message,
            "request_id": "unretained-provider-id",
        },
    )
    diagnostics.denial_hook(("synthetic-secret",), ledger)(response)
    assert ledger[0]["cause"] == cause
    rendered = json.dumps(ledger)
    assert message not in rendered and "unretained-provider-id" not in rendered
    assert "synthetic-secret" not in rendered
