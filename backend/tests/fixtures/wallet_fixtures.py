"""Synthetic baw protocol fixtures only; never runtime capability/live evidence."""

import copy
import json
from datetime import timedelta

from app.clients.baw_cli import BawReadOnlyClient
from backend.tests.fixtures.execution_fixtures import BUY, NOW, SELL, TXHASH, WALLET


def wallet_settings(**changes):
    expires = NOW + timedelta(hours=2)
    data = {
        "dailyLimit": 100,
        "quotaUsed": 0,
        "quotaLeft": 100,
        "quotaDate": NOW.date().isoformat(),
        "tradeAllTokens": True,
        "abnormalTxnHandling": "AutoReject",
        "sessionExpireTime": expires.isoformat(),
        "inactiveSignOutTime": expires.isoformat(),
        "developerModeQuotaUsed": 0,
        "developerModeQuotaDate": NOW.date().isoformat(),
        "devMode": {
            "enabled": True,
            "expiresAt": int(expires.timestamp()),
            "dailyLimit": 100,
            "balanceExceeded": False,
        },
    }
    return {**data, **changes}


def wallet_order(**changes):
    return {
        "orderType": "market",
        "orderId": "wallet-order",
        "chain": "56",
        "fromToken": SELL,
        "toToken": BUY,
        "fromTokenQty": "39.992002",
        "status": "FINISHED",
        "txHash": TXHASH,
        "bookTime": NOW.isoformat(),
        "updatedTime": NOW.isoformat(),
        **changes,
    }


def wallet_history(**changes):
    return {
        "binanceChainId": "56",
        "txHash": TXHASH,
        "txType": "swap",
        "status": "confirmed",
        "txTime": NOW.isoformat(),
        **changes,
    }


class WalletWire(BawReadOnlyClient):
    fixture_only = True

    def __init__(self):
        super().__init__(enabled=False, clock=lambda: NOW)
        self.calls = []
        self.values = {
            "status": {"status": "CONNECTED"},
            "chains": [{"binanceChainId": "56", "name": "BSC", "simpleName": "BSC"}],
            "address": {"addresses": [{"binanceChainId": "56", "address": WALLET}]},
            "balance": [
                {
                    "binanceChainId": "56",
                    "address": SELL,
                    "symbol": "USDT",
                    "balance": "100",
                    "price": "1.0002",
                    "value": "100.02",
                },
                {
                    "binanceChainId": "56",
                    "address": "0x" + "e" * 40,
                    "symbol": "BNB",
                    "balance": "0.1",
                    "price": "100",
                    "value": "10",
                },
            ],
            "settings": wallet_settings(),
            "tx-lock": {"status": "UNLOCKED"},
            "orders": {"total": 1, "page": 1, "pageSize": 100, "list": [wallet_order()]},
            "history": {"transactions": [wallet_history()], "hasMore": False, "nextCursor": None},
            "pending_orders": {"total": 0, "page": 1, "pageSize": 100, "list": []},
            "pending_history": {"transactions": [], "hasMore": False, "nextCursor": None},
            "quote": {
                "fromCoinSymbol": "USDT",
                "fromCoinAmount": "40",
                "toCoinSymbol": "NVDA",
                "toCoinAmount": "0.4",
                "slippage": "0.005",
            },
        }
        self.failure = None

    def _run(self, args):
        self.calls.append(args)
        if self.failure:
            raise self.failure
        if args[0] == "cli-check":
            value = {"currentCliVersion": "1.10.0", "needUpdateCli": False}
        else:
            operation = args[1]
            if args[0] == "market-order" and operation == "list":
                operation = "pending_orders" if "PENDING" in args else "orders"
            elif operation == "tx-history":
                operation = "pending_history" if "pending" in args else "history"
            value = copy.deepcopy(self.values[operation])
        return json.dumps({"success": True, "data": value}).encode()
