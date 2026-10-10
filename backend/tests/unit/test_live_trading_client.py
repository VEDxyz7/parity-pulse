import pytest
from pydantic import SecretStr

from app.clients.binance_trading import BinanceSafetyClient, LiveTradingClient, provider_reason
from app.clients.binance_web3 import sign_request
from app.clients.common import ProviderError
from app.services.execution_gates import LiveExecutionError

KEYS = (SecretStr("k"), SecretStr("s"))
SUBMIT = "/api/v1/dex/aggregator/order/submit"


def test_only_live_client_may_submit_rfq_orders():
    with pytest.raises(ProviderError):
        BinanceSafetyClient(*KEYS).authorize("POST", SUBMIT)
    with pytest.raises(LiveExecutionError, match="RFQ_LIVE_GATE_BLOCKED"):
        LiveTradingClient(*KEYS).authorize("POST", SUBMIT)
    with pytest.raises(ProviderError):
        LiveTradingClient(*KEYS).authorize("POST", "/api/v1/dex/transaction/broadcast")
    with pytest.raises(LiveExecutionError):
        LiveTradingClient(None, None).authorize("POST", SUBMIT)


def test_submit_signing_requires_explicit_live_writes():
    with pytest.raises(ValueError):
        sign_request(KEYS[1], "t", "POST", "/build" + SUBMIT, b"{}")
    with pytest.raises(TypeError):
        sign_request(KEYS[1], "t", "POST", "/build" + SUBMIT, b"{}", live_writes=True)


def test_business_codes_map_to_journal_reasons():
    assert provider_reason(ProviderError("X", "BUSINESS_FAILURE", 200, 40367)) == (
        "ONDO_MARKET_STATE_NOT_TRADABLE"
    )
    assert provider_reason(ProviderError("X", "BUSINESS_FAILURE", 200, "40374")) == (
        "RWA_INSUFFICIENT_LIQUIDITY"
    )
    assert provider_reason(ProviderError("X", "RATE_LIMITED", 429)) == "RATE_LIMITED"
