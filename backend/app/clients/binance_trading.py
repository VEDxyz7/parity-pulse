"""Non-mutating Binance safety adapter using the sole signer/transport.

Not installed as an agent tool or public route. Submit and broadcast are impossible.
"""

import base64
import hashlib
import hmac
import json
import re
from datetime import timedelta

from pydantic import TypeAdapter, ValidationError

from app.clients.binance_web3 import SAFETY_PATHS, BinanceWeb3Client
from app.clients.common import ProviderError
from app.models.execution import (
    ApprovalBuild,
    BuildResponse,
    ProviderQuote,
    QuoteRequest,
    QuoteRoute,
    RFQStatus,
    SimulationResponse,
    SwapStatus,
)

AGGREGATOR = "/api/v1/dex/aggregator/"
SIMULATOR = "/api/v1/dex/pre-transaction/"


def validate(model, data):
    try:
        return TypeAdapter(model).validate_python(data)
    except (ValueError, TypeError, ValidationError):
        raise ProviderError("BINANCE_SAFETY", "SCHEMA_INVALID") from None


class BinanceSafetyClient(BinanceWeb3Client):
    def authorize(self, method, path):
        order_read = (
            method == "GET"
            and re.fullmatch(r"/api/v1/dex/aggregator/order/[A-Za-z0-9_-]{1,128}", path)
            and not path.endswith("/submit")
        )
        if path not in SAFETY_PATHS.get(method, set()) and not order_read:
            raise ProviderError("BINANCE_SAFETY", "EXECUTION_OPERATION_DISABLED")
        if not self.api_key or not self.secret_key:
            raise ProviderError("BINANCE_SAFETY", "NOT_CONFIGURED")

    def supported(self, *, simulation=False):
        data, _, _ = self.read(
            "GET", (SIMULATOR if simulation else AGGREGATOR) + "supported/chain", ttl=30
        )
        if not isinstance(data, list) or not all(
            isinstance(row, dict) and isinstance(row.get("binanceChainId"), str) for row in data
        ):
            raise ProviderError("BINANCE_SAFETY", "SCHEMA_INVALID")
        if not any(row["binanceChainId"] == "56" for row in data):
            raise ProviderError("BINANCE_SAFETY", "BSC_UNSUPPORTED")

    def quote(self, request, *, mode):
        if mode != "LIVE_READ_ONLY":
            raise ProviderError("BINANCE_SAFETY", "REAL_PROVIDER_MODE_REQUIRED")
        request = QuoteRequest.model_validate_json(request.model_dump_json())
        self.supported()
        start = self.clock()
        data, received, _ = self.read("GET", AGGREGATOR + "quote", request.model_dump(), ttl=0)
        rows = validate(list[QuoteRoute], data)
        if not rows or len(rows) > 100 or len({r.quoteId for r in rows}) != len(rows):
            raise ProviderError("BINANCE_SAFETY", "EMPTY_OR_CONFLICTING_ROUTES")
        return [
            validate(
                ProviderQuote,
                dict(
                    request=request,
                    route=row,
                    data_mode=mode,
                    source="BINANCE_WEB3",
                    requested_at=start,
                    received_at=received,
                    expires_at=start + timedelta(seconds=30),
                ),
            )
            for row in rows
        ]

    def build(self, quote, *, slippage_bps):
        if quote.data_mode != "LIVE_READ_ONLY" or quote.source != "BINANCE_WEB3":
            raise ProviderError("BINANCE_SAFETY", "REAL_PROVIDER_MODE_REQUIRED")
        if not quote.requested_at <= self.clock() < quote.expires_at:
            raise ProviderError("BINANCE_SAFETY", "QUOTE_EXPIRED")
        from decimal import Decimal

        from app.models.data import financial

        slip = financial(slippage_bps)
        if not 0 <= slip <= 10000:
            raise ValueError("Invalid slippage")
        params = {
            **quote.request.model_dump(),
            "quoteId": quote.route.quoteId,
            "slippagePercent": format(slip / Decimal(100), "f"),
            "autoSlippage": "false",
        }
        data, _, _ = self.read("GET", AGGREGATOR + "swap", params, ttl=0)
        return validate(BuildResponse, data)

    def approval(self, route):
        quote = route.quote
        if not quote.requested_at <= self.clock() < quote.expires_at:
            raise ProviderError("BINANCE_SAFETY", "QUOTE_EXPIRED")
        if quote.data_mode != "LIVE_READ_ONLY" or quote.source != "BINANCE_WEB3":
            raise ProviderError("BINANCE_SAFETY", "REAL_PROVIDER_MODE_REQUIRED")
        params = dict(
            binanceChainId="56",
            tokenContractAddress=quote.request.fromTokenAddress,
            approveAmount=quote.request.amount,
        )
        if quote.route.executionMode == "RFQ":
            params["vendor"] = quote.route.vendorName
        data, _, _ = self.read(
            "GET",
            AGGREGATOR + "approve-transaction",
            params,
            ttl=0,
        )
        result = validate(list[ApprovalBuild], data)
        if len(result) != 1:
            raise ProviderError("BINANCE_SAFETY", "AMBIGUOUS_APPROVAL")
        return result[0]

    def simulate(self, tx, *, mode):
        if mode != "LIVE_READ_ONLY":
            raise ProviderError("BINANCE_SAFETY", "REAL_PROVIDER_MODE_REQUIRED")
        self.supported(simulation=True)
        data, received, _ = self.read(
            "POST",
            SIMULATOR + "simulate",
            body={"binanceChainId": "56", "evmTx": tx.evm_payload()},
            ttl=0,
        )
        return validate(SimulationResponse, data), received

    def order_status(self, order_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", order_id) or order_id == "submit":
            raise ValueError("Invalid platform order ID")
        data, received, _ = self.read("GET", AGGREGATOR + "order/" + order_id, ttl=0)
        result = validate(RFQStatus, data)
        if result.orderId != order_id:
            raise ProviderError("BINANCE_SAFETY", "ORDER_BINDING_MISMATCH")
        return result, received

    def swap_status(self, tx_hash):
        if not re.fullmatch(r"0x[0-9a-fA-F]{64}", tx_hash):
            raise ValueError("Invalid transaction hash")
        data, received, _ = self.read(
            "GET", AGGREGATOR + "history", {"binanceChainId": "56", "txHash": tx_hash}, ttl=0
        )
        result = None if data is None else validate(SwapStatus, data)
        if result and result.txHash.lower() != tx_hash.lower():
            raise ProviderError("BINANCE_SAFETY", "TRANSACTION_BINDING_MISMATCH")
        return result, received

    def submit_rfq(self, _request):
        # Contract serializer exists; no HTTP submission implementation exists in Phase 8.
        raise ProviderError("BINANCE_SAFETY", "RFQ_LIVE_GATE_BLOCKED")

    def broadcast(self, _request):
        raise ProviderError("BINANCE_SAFETY", "SWAP_LIVE_GATE_BLOCKED")


class LiveTradingClient(BinanceSafetyClient):
    """Central gate checked even through inherited raw transport authorization.

    No automatic runtime constructs this write-capable client. Existing SafetyClient
    stays read-only. RFQ requires exact final-settlement equivalence independently.
    """

    live_writes = True

    def request_attempts(self, method, path):
        return 1 if method == "POST" and path == AGGREGATOR + "order/submit" else self.attempts

    def cache_request(self, method, path):
        return not (method == "POST" and path == AGGREGATOR + "order/submit")

    def sensitive_values(self, request):
        values = super().sensitive_values(request)
        if request.method == "POST" and request.url.path == "/build" + AGGREGATOR + "order/submit":
            signature = json.loads(request.content).get("userSignature")
            if isinstance(signature, str):
                return (*values, signature)
        return values

    def request_signature(self, timestamp, method, wire_path, raw):
        if method == "POST" and wire_path == "/build" + AGGREGATOR + "order/submit":
            # Keep the market/safety signer's operation allowlist unchanged. The one
            # separate submission operation always checks the server gate itself.
            self.authorize(method, AGGREGATOR + "order/submit")
            message = (timestamp + method + wire_path).encode() + raw
            return base64.b64encode(
                hmac.new(
                    self.secret_key.get_secret_value().encode(), message, hashlib.sha256
                ).digest()
            ).decode()
        return super().request_signature(timestamp, method, wire_path, raw)

    def authorize(self, method, path):
        if method == "POST" and path == AGGREGATOR + "order/submit":
            from app.services.execution_gates import LIVE_GATES

            LIVE_GATES.require("RFQ")
            if not self.api_key or not self.secret_key:
                raise ProviderError("BINANCE_SAFETY", "NOT_CONFIGURED")
            return
        super().authorize(method, path)

    def submit_rfq(self, request):
        from app.services.execution_gates import LIVE_GATES

        LIVE_GATES.require("RFQ")
        method, path, body = request.wire_request()
        data, _, _ = self.read(method, path, body=body, ttl=0)
        order_id = data.get("orderId") if isinstance(data, dict) else None
        if not isinstance(order_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", order_id):
            raise ProviderError("BINANCE_SAFETY", "SUBMISSION_OUTCOME_UNKNOWN")
        return order_id


RFQ_CODES = {
    40365: "ONDO_TOKEN_PAIR_NOT_SUPPORTED",
    40366: "ONDO_MAX_SINGLE_ORDER_LIMIT",
    40367: "ONDO_MARKET_STATE_NOT_TRADABLE",
    40368: "ONDO_STABLECOIN_PAIR_INVALID",
    40369: "BSTOCK_INVALID_TRADING_TIME",
    40370: "BSTOCK_INVALID_TRADING_PAIR",
    40374: "RWA_INSUFFICIENT_LIQUIDITY",
    40375: "ONDO_FROM_USD_AMOUNT_TOO_SMALL",
    40401: "QUOTE_EXPIRED",
    40421: "INSUFFICIENT_LIQUIDITY",
    40441: "NO_VALID_VENDOR_QUOTE",
    40462: "QUOTE_PARAMETER_MISMATCH",
}


def provider_reason(error):
    code = getattr(error, "business_status", None)
    try:
        code = int(code)
    except (TypeError, ValueError):
        return getattr(error, "kind", "PROVIDER_ERROR")
    return RFQ_CODES.get(code, getattr(error, "kind", "PROVIDER_ERROR"))
