"""Strict Agentic Wallet normalization and DRY_RUN checks; no raw CLI in callers."""

from datetime import UTC, datetime
from decimal import Decimal, localcontext

from app.clients.baw_cli import WalletReadError, human_base_units
from app.models.data import source_time, utc
from app.models.execution import address, fingerprint
from app.models.wallet import (
    WalletBalance,
    WalletCheck,
    WalletIndicativeQuote,
    WalletOrder,
    WalletPreflight,
    WalletReadResult,
    WalletSettings,
    WalletSnapshot,
    WalletTransaction,
)

NATIVE_BSC = "0x" + "e" * 40  # Official baw native-token sentinel, not a funding contract.
LIMITATIONS = (
    "READ_WINDOW_NOT_PROVIDER_OBSERVATION",
    "BALANCES_BELOW_0_01_USD_OMITTED",
    "RESTRICTED_TOKEN_LIST_NOT_EXPOSED",
    "QUOTA_RESET_TIMEZONE_NOT_DOCUMENTED",
    "SESSION_READS_NOT_ATOMIC",
    "LIVE_EXECUTION_BLOCKED",
)


def obj(value):
    if not isinstance(value, dict):
        raise ValueError("Object required")
    return value


def rows(value, maximum=1000):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError("Bounded list required")
    return [obj(row) for row in value]


def settings(value):
    s = obj(value)
    d = obj(s["devMode"])
    return WalletSettings(
        daily_limit_usd=s["dailyLimit"],
        quota_used_usd=s["quotaUsed"],
        quota_left_usd=s["quotaLeft"],
        quota_date=s["quotaDate"],
        trade_all_tokens=s["tradeAllTokens"],
        abnormal_handling=s["abnormalTxnHandling"],
        session_expires_at=s["sessionExpireTime"],
        inactive_signout_at=s["inactiveSignOutTime"],
        developer_enabled=d["enabled"],
        developer_expires_at=None if d["expiresAt"] is None else source_time(d["expiresAt"] * 1000),
        developer_daily_limit_usd=d["dailyLimit"],
        developer_quota_used_usd=s["developerModeQuotaUsed"],
        developer_quota_date=s["developerModeQuotaDate"],
        developer_balance_exceeded=d["balanceExceeded"],
    )


class AgenticWalletAdapter:
    """Injected controlled worker only. An absent runtime is an explicit capability result."""

    def __init__(self, client=None, *, data_mode="LIVE_READ_ONLY", clock=None):
        if data_mode not in {"DEMO", "LIVE_READ_ONLY"}:
            raise ValueError("Unsupported wallet data mode")
        self.client, self.data_mode = client, data_mode
        self.clock = clock or (lambda: datetime.now(UTC))

    def _source(self):
        if self.client is None:
            return "UNAVAILABLE"
        return "TEST_FIXTURE" if getattr(self.client, "fixture_only", False) else "BINANCE_BAW"

    def _read(self, operation, **params):
        if self.client is None:
            raise WalletReadError("WORKER_UNAVAILABLE")
        if (self.data_mode == "DEMO") != (getattr(self.client, "fixture_only", False) is True):
            raise WalletReadError("WALLET_MODE_ISOLATION")
        value, started, received = self.client.read(operation, **params)
        started, received = utc(started), utc(received)
        if not 0 <= (received - started).total_seconds() <= 30:
            raise WalletReadError("WALLET_READ_WINDOW_INVALID")
        if not 0 <= (self.clock() - received).total_seconds() <= 120:
            raise WalletReadError("WALLET_READ_STALE")
        return value, started, received

    def _verified(self):
        return "FIXTURE_VERIFIED" if self._source() == "TEST_FIXTURE" else "VERIFIED_READ"

    def snapshot(self):
        start = self.clock()
        connection = "UNKNOWN"
        try:
            value, _, _ = self._read("status")
            connection = obj(value)["status"]
            if connection not in {"CONNECTED", "UNCONNECTED", "CREATING"}:
                raise ValueError("Unknown connection")
            if connection != "CONNECTED":
                raise WalletReadError("WALLET_NOT_CONNECTED")
            value, _, _ = self._read("settings")
            security = settings(value)
            value, _, _ = self._read("chains")
            chains = tuple(row["binanceChainId"] for row in rows(value))
            value, _, _ = self._read("address")
            identities = [
                row for row in rows(obj(value)["addresses"]) if row["binanceChainId"] == "56"
            ]
            if len(identities) > 1:
                raise ValueError("Ambiguous BSC wallet")
            wallet = address(identities[0]["address"]) if identities else None
            balances, lock = (), "UNKNOWN"
            if "56" in chains and wallet is not None:
                value, _, _ = self._read("balance")
                balances = tuple(
                    WalletBalance(
                        chain_id=row["binanceChainId"],
                        contract=row["address"],
                        symbol=row["symbol"],
                        quantity=row["balance"],
                        indicative_unit_price_usd=row["price"],
                        indicative_value_usd=row["value"],
                    )
                    for row in rows(value)
                )
                value, _, _ = self._read("tx-lock")
                lock = obj(value)["status"]
            pending_orders = self.read_records("orders", pending=True)
            pending_history = self.read_records("history", pending=True)
            verified = {"VERIFIED_READ", "FIXTURE_VERIFIED"}
            pending = "UNKNOWN"
            if (
                pending_orders.capability_status in verified
                and pending_history.capability_status in verified
                and not pending_orders.more_available
                and not pending_history.more_available
                and all(o.status == "PENDING" for o in pending_orders.orders)
                and all(t.status == "pending" for t in pending_history.transactions)
            ):
                pending = (
                    "PENDING" if pending_orders.orders or pending_history.transactions else "CLEAR"
                )
            # Bind the read window to the same BSC identity and connection at its end.
            end_status, _, _ = self._read("status")
            end_addresses, _, _ = self._read("address")
            end_ids = [
                r for r in rows(obj(end_addresses)["addresses"]) if r["binanceChainId"] == "56"
            ]
            end_wallet = address(end_ids[0]["address"]) if len(end_ids) == 1 else None
            if obj(end_status)["status"] != connection or end_wallet != wallet:
                raise WalletReadError("WALLET_SESSION_CHANGED")
            result = WalletSnapshot(
                data_mode=self.data_mode,
                source=self._source(),
                capability_status=self._verified(),
                requested_at=start,
                received_at=self.clock(),
                connection=connection,
                supported_chains=chains,
                bsc_address=wallet,
                balances=balances,
                settings=security,
                transaction_lock=lock,
                pending_state=pending,
                limitations=LIMITATIONS,
            )
            if (result.received_at - start).total_seconds() > 30:
                raise WalletReadError("WALLET_READ_WINDOW_INVALID")
            return result
        except (WalletReadError, ValueError, KeyError, TypeError, OverflowError):
            import sys

            error = sys.exception()
            code = error.code if isinstance(error, WalletReadError) else "WALLET_SCHEMA_INVALID"
            # No partial state or raw body can accidentally become a verified wallet.
            return WalletSnapshot(
                data_mode=self.data_mode,
                source="UNAVAILABLE",
                capability_status="INVALID" if code == "WALLET_SCHEMA_INVALID" else "UNAVAILABLE",
                requested_at=start,
                received_at=max(start, self.clock()),
                connection=connection
                if connection in {"CONNECTED", "UNCONNECTED", "CREATING"}
                else "UNKNOWN",
                errors=(code,),
                limitations=LIMITATIONS,
            )

    def read_records(self, capability, **params):
        if capability not in {"history", "orders", "quote"}:
            raise ValueError("Read capability required")
        start = self.clock()
        try:
            connected, _, _ = self._read("status")
            if obj(connected)["status"] != "CONNECTED":
                raise WalletReadError("WALLET_NOT_CONNECTED")
            value, _, received = self._read(capability, **params)
            records, transactions, quote, more = (), (), None, False
            if capability == "orders":
                value = obj(value)
                entries = rows(value["list"], 100)
                records = tuple(
                    WalletOrder(
                        order_id=r["orderId"],
                        chain_id=r["chain"],
                        sell_token=r["fromToken"],
                        buy_token=r["toToken"],
                        sell_quantity=r["fromTokenQty"],
                        status=r["status"]
                        if r["status"] in {"PENDING", "FINISHED", "FAILED"}
                        else "UNKNOWN",
                        tx_hash=r["txHash"],
                        created_at=r["bookTime"],
                        updated_at=r["updatedTime"],
                    )
                    for r in entries
                )
                total, page, size = value["total"], value["page"], value["pageSize"]
                if any(type(n) is not int for n in (total, page, size)) or not (
                    total >= len(entries) and page >= 1 and 1 <= size <= 100
                ):
                    raise ValueError("Invalid pagination")
                more = (page - 1) * size + len(entries) < total
                if params.get("order_id") and any(
                    r.order_id != params["order_id"] for r in records
                ):
                    raise ValueError("Order binding mismatch")
                if len({r.order_id for r in records}) != len(records):
                    raise ValueError("Duplicate order")
                if any(r.updated_at > received for r in records):
                    raise ValueError("Future order")
            elif capability == "history":
                value = obj(value)
                entries = rows(value["transactions"], 100)
                transactions = tuple(
                    WalletTransaction(
                        chain_id=r["binanceChainId"],
                        tx_hash=r["txHash"],
                        transaction_type=r["txType"],
                        status=r["status"]
                        if r["status"] in {"pending", "confirmed", "failed"}
                        else "UNKNOWN",
                        occurred_at=r["txTime"],
                    )
                    for r in entries
                )
                if type(value["hasMore"]) is not bool:
                    raise ValueError("Invalid history pagination")
                more = value["hasMore"]
                if params.get("tx_hash") and any(
                    t.tx_hash.lower() != params["tx_hash"].lower() for t in transactions
                ):
                    raise ValueError("Transaction binding mismatch")
                if len({t.tx_hash for t in transactions}) != len(transactions) or any(
                    t.occurred_at > received for t in transactions
                ):
                    raise ValueError("Conflicting history")
            else:
                value = obj(value)
                quote = WalletIndicativeQuote(
                    sell_symbol=value["fromCoinSymbol"],
                    sell_quantity=value["fromCoinAmount"],
                    buy_symbol=value["toCoinSymbol"],
                    buy_quantity=value["toCoinAmount"],
                    slippage_fraction=value["slippage"],
                )
                if quote.sell_quantity != Decimal(params["quantity"]):
                    raise ValueError("Quote amount mismatch")
            return WalletReadResult(
                capability=capability,
                capability_status=self._verified(),
                data_mode=self.data_mode,
                source=self._source(),
                requested_at=start,
                received_at=received,
                orders=records,
                transactions=transactions,
                quote=quote,
                more_available=more,
                limitations=(
                    "BOUNDED_PAGE_NOT_COMPLETE_HISTORY",
                    "NO_PHASE8_SETTLEMENT_EQUIVALENCE",
                ),
            )
        except (WalletReadError, ValueError, TypeError, KeyError, OverflowError):
            import sys

            error = sys.exception()
            code = error.code if isinstance(error, WalletReadError) else "WALLET_SCHEMA_INVALID"
            return WalletReadResult(
                capability=capability,
                capability_status="UNAVAILABLE",
                data_mode=self.data_mode,
                source="UNAVAILABLE",
                requested_at=start,
                received_at=max(start, self.clock()),
                errors=(code,),
            )


class WalletSafetyChecks:
    def evaluate(self, snapshot, attempt, funding_state, *, now):
        now = utc(now)
        snapshot = WalletSnapshot.model_validate_json(snapshot.model_dump_json())
        checks = []

        def check(code, passed):
            checks.append(WalletCheck(code=code, passed=bool(passed)))

        q = attempt.quote
        s = snapshot.settings
        check(
            "WALLET_AVAILABLE",
            snapshot.capability_status in {"VERIFIED_READ", "FIXTURE_VERIFIED"}
            and snapshot.connection == "CONNECTED",
        )
        check(
            "WALLET_MODE",
            snapshot.data_mode == attempt.data_mode
            and ((snapshot.source == "TEST_FIXTURE") == (attempt.data_mode == "DEMO")),
        )
        check(
            "WALLET_READ_FRESH",
            0 <= (now - snapshot.received_at).total_seconds() <= 120
            and 0 <= (snapshot.received_at - snapshot.requested_at).total_seconds() <= 30,
        )
        check("WALLET_BSC_SUPPORTED", "56" in snapshot.supported_chains)
        check(
            "WALLET_IDENTITY",
            q is not None
            and snapshot.bsc_address == q.request.userWalletAddress
            and funding_state is not None
            and snapshot.bsc_address == funding_state.wallet,
        )
        check("WALLET_UNLOCKED", snapshot.transaction_lock == "UNLOCKED")
        check("WALLET_PENDING_RECONCILED", snapshot.pending_state == "CLEAR")
        check("WALLET_SETTINGS_AVAILABLE", s is not None)
        if s:
            check("WALLET_SESSION_VALID", min(s.session_expires_at, s.inactive_signout_at) > now)
            check(
                "WALLET_TOKEN_SCOPE_VERIFIED", s.trade_all_tokens
            )  # Missing restricted list fails closed.
            # Unknown reset timezone: date must agree with UTC and no reset-boundary claim is made.
            check(
                "WALLET_QUOTA_DATE_CURRENT",
                s.quota_date == now.date() and s.developer_quota_date == now.date(),
            )
            with localcontext() as ctx:
                ctx.prec = 256
                funding_value = attempt.evidence.notional_usd
                if q is not None and funding_state is not None:
                    funding_value = (
                        Decimal(q.request.amount)
                        / (Decimal(10) ** funding_state.asset.decimals)
                        * funding_state.unit_price_usd
                    )
                value = (
                    funding_value
                    + attempt.evidence.costs_usd
                    + attempt.evidence.conversion_cost_usd
                )
                check(
                    "WALLET_SPENDING_LIMIT",
                    value <= s.daily_limit_usd and value <= s.quota_left_usd,
                )
                check(
                    "WALLET_DEVELOPER_LIMIT",
                    value + s.developer_quota_used_usd <= s.developer_daily_limit_usd,
                )
            check(
                "WALLET_DEVELOPER_AVAILABLE",
                s.developer_enabled
                and s.developer_expires_at is not None
                and s.developer_expires_at > now
                and not s.developer_balance_exceeded,
            )
            check("WALLET_CONFIRMATION_POLICY", s.abnormal_handling == "AutoReject")
            # NeedConfirmation needs App/preview evidence; reads alone cannot prove it.
        available = False
        gas_available = False
        if funding_state is not None and q is not None:
            balances = {b.contract: b for b in snapshot.balances}
            token, native = balances.get(q.request.fromTokenAddress), balances.get(NATIVE_BSC)
            try:
                if token is not None:
                    units = human_base_units(token.quantity, funding_state.asset.decimals)
                    available = (
                        int(units) >= int(q.request.amount)
                        and units == funding_state.balance_base_units
                        and token.contract == funding_state.asset.contract
                    )
                if native is not None:
                    gas_available = (
                        human_base_units(native.quantity, 18)
                        == funding_state.native_gas_balance_wei
                    )
            except ValueError:
                pass
        check("WALLET_FUNDING_BALANCE_MATCH", available)
        check("WALLET_NATIVE_BALANCE_MATCH", gas_available)
        reasons = tuple(c.code for c in checks if not c.passed)
        return WalletPreflight(
            status="BLOCKED" if reasons else "PASS",
            data_mode=attempt.data_mode,
            evaluated_at=now,
            snapshot_digest=fingerprint(snapshot),
            route_fingerprint=attempt.route.fingerprint if attempt.route else None,
            checks=tuple(checks),
            reasons=reasons,
        )
