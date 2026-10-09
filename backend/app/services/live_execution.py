"""Live rebalance execution for wallet-inventory plans (BSC mainnet, SWAP routes only).

Per action, in plan priority order (sales before purchases):
  fresh quote -> bound checks vs plan -> exact approval (simulated, sent, confirmed)
  -> build -> provider simulation must SUCCEED with the expected balance changes
  -> native gas check -> sign + send -> receipt status 1 -> on-chain balance reconciliation.

Hard limits enforced here independently of planning: per-action notional cap, slippage cap,
SWAP-only (no RFQ signing), wallet identity, journal idempotency (an action that already has
a journal row is reconciled, never re-sent). Any failed check stops the whole plan.
"""

import threading
import time
from datetime import UTC, datetime
from decimal import Decimal, localcontext

from app.clients.bsc_rpc import approve_calldata
from app.clients.common import ProviderError
from app.models.execution import EvmTransaction, QuoteRequest
from app.services.live_portfolio_source import USDT, USDT_DECIMALS

APPROVE_GAS = 80000
RECEIPT_TIMEOUT_SECONDS = 90
MAX_PLAN_AGE_SECONDS = 600


class LiveExecutionError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class LiveRebalanceExecutor:
    def __init__(
        self,
        portfolio,
        trading,
        rpc,
        signer,
        journal,
        *,
        max_notional_usd,
        max_slippage_bps,
        gas_reserve_wei,
        clock=lambda: datetime.now(UTC),
        sleep=time.sleep,
    ):
        if portfolio.inventory != "WALLET":
            raise ValueError("Live execution requires wallet-inventory planning")
        self.portfolio, self.trading, self.rpc = portfolio, trading, rpc
        self.signer, self.journal = signer, journal
        self.max_notional = Decimal(str(max_notional_usd))
        self.max_slippage_bps = Decimal(str(max_slippage_bps))
        self.gas_reserve_wei = int(gas_reserve_wei)
        self.clock, self.sleep = clock, sleep
        self.lock = threading.Lock()
        self._usdt_price = None

    # -- public --------------------------------------------------------------------------
    def execute(self, plan_id):
        if not self.lock.acquire(blocking=False):
            raise LiveExecutionError("LIVE_EXECUTION_ALREADY_RUNNING")
        try:
            plan = self.portfolio.store.get(plan_id, mode=self.portfolio.mode)
            if plan.status != "REBALANCE_REQUIRED":
                raise LiveExecutionError("PLAN_NOT_ACTIONABLE")
            age = (self.clock() - plan.created_at).total_seconds()
            if not 0 <= age <= MAX_PLAN_AGE_SECONDS and not any(
                self.journal.get(a.action_id) for a in plan.actions
            ):
                raise LiveExecutionError("PLAN_TOO_OLD_REEVALUATE")
            if plan.snapshot.inputs.funding.wallet != self.signer.address:
                raise LiveExecutionError("PLAN_WALLET_IS_NOT_SIGNER_WALLET")
            results = []
            for action in sorted(plan.actions, key=lambda a: a.priority):
                record = self._leg(plan, action)
                results.append(record)
                if record["status"] != "CONFIRMED":
                    break
            if results and all(r["status"] == "CONFIRMED" for r in results) and len(
                results
            ) == len(plan.actions):
                self.portfolio.mark_executed(plan_id)
            return results
        finally:
            self.lock.release()

    # -- one leg -------------------------------------------------------------------------
    def _leg(self, plan, action):
        existing = self.journal.get(action.action_id)
        if existing is not None:
            return self._reconcile(existing)
        token = action.route.selected_representation.contract
        base = dict(
            plan_id=plan.plan_id,
            asset=action.asset,
            side=action.side,
            token=token,
            notional_usd=action.notional_usd,
            signer=self.signer.kind,
        )
        record = self.journal.upsert(action.action_id, status="PREPARING", **base)
        self._usdt_price = plan.snapshot.inputs.funding.unit_price_usd
        try:
            return self._run(action, token, record)
        except (LiveExecutionError, ProviderError, ValueError, ArithmeticError) as error:
            code = getattr(error, "code", None) or getattr(error, "kind", None)
            code = code or type(error).__name__.upper()
            current = self.journal.get(action.action_id)
            if current.get("swap_tx"):
                # A swap was sent: never call it rejected; settle it from its receipt.
                current = self.journal.upsert(
                    action.action_id, status="SUBMITTED", reasons=[str(code)]
                )
                return self._reconcile(current)
            return self.journal.upsert(action.action_id, status="REJECTED", reasons=[str(code)])

    def _run(self, action, token, record):
        if action.notional_usd > self.max_notional:
            raise LiveExecutionError("LIVE_NOTIONAL_CAP")
        if not action.eligible_for_preparation or action.risk.status != "PASS":
            raise LiveExecutionError("ACTION_NOT_RISK_APPROVED")
        wallet = self.signer.address
        mark = action.route.selected_candidate.inputs
        slip = min(self.max_slippage_bps, action.risk_inputs.slippage_bps + Decimal(50))
        if action.side == "BUY":
            with localcontext() as ctx:
                ctx.prec = 72
                usdt_price = self.portfolio_usdt_price()
                amount = int(action.notional_usd / usdt_price * 10**USDT_DECIMALS)
            sell, buy = USDT, token
            minimum_out = int(
                Decimal(action.quantity_base_units) * (1 - slip / Decimal(10000))
            )
        else:
            amount = int(action.quantity_base_units)
            sell, buy = token, USDT
            with localcontext() as ctx:
                ctx.prec = 72
                minimum_out = int(
                    action.notional_usd
                    * (1 - slip / Decimal(10000))
                    / self.portfolio_usdt_price()
                    * 10**USDT_DECIMALS
                )
        held = self.rpc.erc20_balance(sell, wallet)
        if held < amount:
            raise LiveExecutionError("INSUFFICIENT_ON_CHAIN_BALANCE")
        request = QuoteRequest(
            binanceChainId="56",
            amount=str(amount),
            fromTokenAddress=sell,
            toTokenAddress=buy,
            userWalletAddress=wallet,
        )
        quotes = [
            q
            for q in self.trading.quote(request, mode="LIVE_READ_ONLY")
            if q.route.executionMode == "SWAP" and q.route.approveTarget
        ]
        if not quotes:
            raise LiveExecutionError("NO_SIMULATABLE_SWAP_ROUTE")
        quote = max(quotes, key=lambda q: int(q.route.toTokenAmount))
        impact = abs(quote.route.priceImpactPercent or Decimal(0)) * 10000
        if impact > self.max_slippage_bps:
            raise LiveExecutionError("PRICE_IMPACT_LIMIT")
        if int(quote.route.toTokenAmount) < minimum_out:
            raise LiveExecutionError("QUOTE_BELOW_PLAN_MINIMUM")
        spender = quote.route.approveTarget
        evidence = dict(
            quote_id=quote.route.quoteId,
            vendor=quote.route.vendorName,
            amount_in=str(amount),
            quoted_out=quote.route.toTokenAmount,
            minimum_out=str(minimum_out),
            price_impact_bps=str(impact),
            spender=spender,
            plan_mark_usd=str(mark.token_price_usd),
        )
        record = self.journal.upsert(action.action_id, status="QUOTED", evidence=evidence)
        # Exact approval only for this leg's amount; never unlimited.
        if self.rpc.allowance(sell, wallet, spender) < amount:
            approve_tx = EvmTransaction.model_validate(
                {
                    "from": wallet,
                    "to": sell,
                    "data": approve_calldata(spender, amount),
                    "value": "0",
                    "gas": str(APPROVE_GAS),
                    "gasPrice": str(self.rpc.gas_price()),
                }
            )
            sim, _ = self.trading.simulate(approve_tx, mode="LIVE_READ_ONLY")
            if sim.status != "SUCCESS":
                raise LiveExecutionError("APPROVAL_SIMULATION_FAILED")
            self._gas(approve_tx)
            approve_hash = self._send(approve_tx)
            record = self.journal.upsert(
                action.action_id, status="APPROVING", approve_tx=approve_hash
            )
            if not self._confirmed(approve_hash):
                raise LiveExecutionError("APPROVAL_NOT_CONFIRMED")
            if self.rpc.allowance(sell, wallet, spender) < amount:
                raise LiveExecutionError("APPROVAL_NOT_OBSERVED")
        # Requote after approval if the 30s quote lifetime is close to expiry.
        if (quote.expires_at - self.clock()).total_seconds() < 10:
            quote = max(
                (
                    q
                    for q in self.trading.quote(request, mode="LIVE_READ_ONLY")
                    if q.route.executionMode == "SWAP" and q.route.approveTarget == spender
                ),
                key=lambda q: int(q.route.toTokenAmount),
                default=None,
            )
            if quote is None or int(quote.route.toTokenAmount) < minimum_out:
                raise LiveExecutionError("REQUOTE_BELOW_PLAN_MINIMUM")
        build = self.trading.build(quote, slippage_bps=slip)
        tx = build.tx
        if build.executionMode != "SWAP" or tx is None:
            raise LiveExecutionError("BUILD_NOT_SWAP")
        if tx.sender != wallet or tx.to != spender or int(tx.value) != 0:
            raise LiveExecutionError("BUILD_IDENTITY_MISMATCH")
        if tx.minReceiveAmount is None or int(tx.minReceiveAmount) < minimum_out:
            raise LiveExecutionError("BUILD_MIN_RECEIVE_BELOW_PLAN_MINIMUM")
        sim, _ = self.trading.simulate(tx, mode="LIVE_READ_ONLY")
        if sim.status != "SUCCESS":
            raise LiveExecutionError("SWAP_SIMULATION_FAILED")
        gained = sum(
            int(c.change)
            for c in sim.balanceChanges
            if c.owner == wallet and c.contractAddress.lower() == buy
        )
        if sim.balanceChanges and gained < int(tx.minReceiveAmount):
            raise LiveExecutionError("SIMULATED_RECEIVE_BELOW_MINIMUM")
        evidence = dict(
            evidence,
            build_min_receive=tx.minReceiveAmount,
            simulated_receive=str(gained) if sim.balanceChanges else None,
            simulation="SUCCESS",
        )
        self._gas(tx)
        before_in = self.rpc.erc20_balance(sell, wallet)
        before_out = self.rpc.erc20_balance(buy, wallet)
        swap_hash = self._send(tx)
        record = self.journal.upsert(
            action.action_id, status="SUBMITTED", swap_tx=swap_hash, evidence=evidence
        )
        receipt = self._wait(swap_hash)
        if receipt is None:
            return self.journal.upsert(action.action_id, status="SUBMITTED")
        if receipt.get("status") != "0x1":
            return self.journal.upsert(
                action.action_id, status="FAILED", reasons=["SWAP_REVERTED_ON_CHAIN"]
            )
        spent = before_in - self.rpc.erc20_balance(sell, wallet)
        received = self.rpc.erc20_balance(buy, wallet) - before_out
        evidence = dict(
            evidence,
            spent=str(spent),
            received=str(received),
            gas_used=str(int(receipt.get("gasUsed", "0x0"), 16)),
            block=str(int(receipt.get("blockNumber", "0x0"), 16)),
        )
        return self.journal.upsert(
            action.action_id,
            status="CONFIRMED",
            evidence=evidence,
            realized_cost_usd=self._cost(action, spent, received),
        )

    # -- helpers -------------------------------------------------------------------------
    def portfolio_usdt_price(self):
        return self._usdt_price

    def _cost(self, action, spent, received):
        """Realized execution cost vs plan mark (positive = worse than mark)."""
        usdt = self.portfolio_usdt_price()
        mark = action.route.selected_candidate.inputs.token_price_usd
        dec = action.decimals
        with localcontext() as ctx:
            ctx.prec = 72
            if action.side == "BUY":
                paid = Decimal(spent) / 10**USDT_DECIMALS * usdt
                value = Decimal(received) / Decimal(10) ** dec * mark
                return paid - value
            sold = Decimal(spent) / Decimal(10) ** dec * mark
            got = Decimal(received) / 10**USDT_DECIMALS * usdt
            return sold - got

    def _gas(self, tx):
        need = int(tx.gas) * int(tx.gasPrice) + self.gas_reserve_wei
        if self.rpc.native_balance(self.signer.address) < need:
            raise LiveExecutionError("INSUFFICIENT_NATIVE_GAS_AND_RESERVE")

    def _send(self, tx):
        return self.signer.send(
            to=tx.to, data=tx.data, value=tx.value, gas=tx.gas, gas_price=tx.gasPrice
        )

    def _wait(self, tx_hash):
        deadline = time.monotonic() + RECEIPT_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            receipt = self.rpc.receipt(tx_hash)
            if receipt:
                return receipt
            self.sleep(1.5)
        return None

    def _confirmed(self, tx_hash):
        receipt = self._wait(tx_hash)
        return bool(receipt) and receipt.get("status") == "0x1"

    def _reconcile(self, record):
        """Never resend a journaled leg; only observe its submitted transaction."""
        if record["status"] in {"CONFIRMED", "FAILED"}:
            return record
        if not record.get("swap_tx"):
            if record["status"] != "REJECTED":
                return self.journal.upsert(
                    record["action_id"], status="REJECTED", reasons=["INTERRUPTED_BEFORE_SEND"]
                )
            return record
        try:
            receipt = self.rpc.receipt(record["swap_tx"])
        except ProviderError:
            return record
        if not receipt:
            return record
        return self.journal.upsert(
            record["action_id"],
            status="CONFIRMED" if receipt.get("status") == "0x1" else "FAILED",
        )
