"""Live rebalance execution for wallet-inventory plans (BSC mainnet).

Per action, in plan priority order (sales before purchases), the best of two route kinds:

SWAP (verification=EXACT_SIMULATION):
  fresh quote -> bound checks vs plan -> exact approval (simulated, sent, confirmed)
  -> build -> provider simulation must SUCCEED with the expected balance changes
  -> native gas check -> sign + send -> receipt status 1 -> on-chain balance reconciliation.

RFQ (verification=SIGNED_ORDER_BOUND; never while the underlying market is closed):
  fresh quote -> exact approval to the vendor's known spender -> /swap payload captured
  -> EIP-712 order verified against plan bounds (rfq_orders) -> sign -> signature recovered
  -> requestId journaled before submit -> /order/submit -> poll -> receipt + balance diff must
  satisfy the signed bounds.

Hard limits enforced here independently of planning: per-action notional cap (half when the
underlying is closed), slippage cap, wallet identity, settlement allowlist, journal idempotency
(a journaled leg is reconciled, never re-sent or re-signed). Any failed check stops the plan.
"""

import threading
import time
from datetime import UTC, datetime
from decimal import Decimal, localcontext

import json
from uuid import uuid4

from app.clients.bsc_rpc import approve_calldata
from app.clients.common import ProviderError
from app.models.execution import BuildResponse, EvmTransaction, QuoteRequest, RFQSubmission
from app.services.live_portfolio_source import USDT, USDT_DECIMALS
from app.services.routing import CLOSED_STATES

APPROVE_GAS = 80000
RECEIPT_TIMEOUT_SECONDS = 90
MAX_PLAN_AGE_SECONDS = 600
ORDER_POLL_SECONDS = 120
RESUBMIT_WINDOW_SECONDS = 1800  # Binance: requestId idempotent for 30 minutes
RFQ_VENDORS = {"CowSwap", "InchFusion", "PcsXRfq"}
NOT_FILLED = {"FAILED", "EXPIRED", "CANCELLED"}


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
        rfq_allowlist=None,
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
        # RFQ needs: a settlement allowlist, a client that can submit, a typed-data signer.
        self.rfq_allowlist = rfq_allowlist
        self.rfq_enabled = bool(
            rfq_allowlist is not None
            and hasattr(trading, "submit_rfq")
            and getattr(trading, "live_writes", False)
            and hasattr(signer, "sign_typed_data")
        )

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
            if isinstance(error, ProviderError):
                from app.clients.binance_trading import provider_reason

                code = provider_reason(error)
            else:
                code = getattr(error, "code", None) or type(error).__name__.upper()
            current = self.journal.get(action.action_id)
            evidence = current["evidence"]
            if evidence.get("rfq_request_id") and not evidence.get("rfq_status_order_id"):
                # Signed but submission not acknowledged: stay SIGNED; the next run resubmits
                # the identical idempotent body (same requestId), never a new signature.
                return self.journal.upsert(action.action_id, status="SIGNED", reasons=[str(code)])
            if current.get("swap_tx") or evidence.get("rfq_request_id"):
                # Something was sent: never call it rejected; settle it from chain/provider.
                current = self.journal.upsert(
                    action.action_id, status="SUBMITTED", reasons=[str(code)]
                )
                return self._reconcile(current)
            return self.journal.upsert(action.action_id, status="REJECTED", reasons=[str(code)])

    def _run(self, action, token, record):
        closed = action.route.selected_candidate.inputs.market_state in CLOSED_STATES
        cap = self.max_notional / 2 if closed else self.max_notional
        if action.notional_usd > cap:
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
        offered = self.trading.quote(request, mode="LIVE_READ_ONLY")
        swaps = [q for q in offered if q.route.executionMode == "SWAP" and q.route.approveTarget]
        rfqs = (
            [
                q
                for q in offered
                if q.route.executionMode == "RFQ" and q.route.vendorName in RFQ_VENDORS
            ]
            if self.rfq_enabled and not closed
            else []
        )
        best_swap = max(swaps, key=lambda q: int(q.route.toTokenAmount), default=None)
        best_rfq = max(rfqs, key=lambda q: int(q.route.toTokenAmount), default=None)
        # Exact simulation beats a signed-order bound: RFQ only when strictly better.
        if best_rfq is not None and (
            best_swap is None
            or int(best_rfq.route.toTokenAmount) > int(best_swap.route.toTokenAmount)
        ):
            return self._rfq_leg(action, sell, buy, amount, minimum_out, slip, best_rfq, mark)
        if best_swap is None:
            raise LiveExecutionError("NO_SIMULATABLE_SWAP_ROUTE")
        quote = best_swap
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
            route="SWAP",
            verification="EXACT_SIMULATION",
        )
        record = self.journal.upsert(action.action_id, status="QUOTED", evidence=evidence)
        self._approve(action.action_id, sell, spender, amount)
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

    # -- RFQ ---------------------------------------------------------------------------------
    def _rfq_leg(self, action, sell, buy, amount, minimum_out, slip, quote, mark):
        from app.services.rfq_orders import DEFAULT_SPENDERS, Expected, RFQRejected, verify

        wallet, vendor = self.signer.address, quote.route.vendorName
        if self.signer.rfq_signing_scheme == "eip1271" and vendor != "CowSwap":
            raise LiveExecutionError("RFQ_VENDOR_REQUIRES_EOA")
        impact = abs(quote.route.priceImpactPercent or Decimal(0)) * 10000
        if impact > self.max_slippage_bps:
            raise LiveExecutionError("PRICE_IMPACT_LIMIT")
        if int(quote.route.toTokenAmount) < minimum_out:
            raise LiveExecutionError("QUOTE_BELOW_PLAN_MINIMUM")
        spender = DEFAULT_SPENDERS[vendor]
        # Cross-check Binance's vendor approval against the vendor's known spender.
        approval = self.trading.rfq_approval(token=sell, amount=amount, vendor=vendor)
        offered_spender = approval.data[34:74] if approval.data.startswith("0x095ea7b3") else ""
        if "0x" + offered_spender.lower() != spender:
            raise LiveExecutionError("RFQ_APPROVAL_SPENDER_MISMATCH")
        evidence = dict(
            route="RFQ",
            verification="SIGNED_ORDER_BOUND",
            vendor=vendor,
            quote_id=quote.route.quoteId,
            amount_in=str(amount),
            quoted_out=quote.route.toTokenAmount,
            minimum_out=str(minimum_out),
            price_impact_bps=str(impact),
            spender=spender,
            plan_mark_usd=str(mark.token_price_usd),
        )
        self.journal.upsert(action.action_id, status="QUOTED", evidence=evidence)
        self._approve(action.action_id, sell, spender, amount)
        raw = self.trading.build_rfq(quote, slippage_bps=slip)
        try:
            build = BuildResponse.model_validate(raw)
            if build.executionMode != "RFQ" or build.rfq is None or build.rfq.vendor != vendor:
                raise LiveExecutionError("RFQ_BUILD_SHAPE_MISMATCH")
            typed = json.loads(build.rfq.typedDataToSign)
            order = verify(
                vendor,
                typed,
                Expected(
                    wallet=wallet,
                    sell_token=sell,
                    sell_max=amount,
                    buy_token=buy,
                    min_buy=minimum_out,
                    now=int(self.clock().timestamp()),
                ),
                self.rfq_allowlist,
            )
            if order.spender != spender:
                raise LiveExecutionError("RFQ_ORDER_SPENDER_MISMATCH")
        except (RFQRejected, LiveExecutionError, ValueError) as error:
            code = getattr(error, "code", None) or "RFQ_BUILD_INVALID"
            self.journal.capture_rfq(raw, verdict="REJECTED", reason=code)
            self._revoke(sell, spender)  # the exact approval is no longer needed
            raise LiveExecutionError(code) from None
        self.journal.capture_rfq(raw, verdict="ACCEPTED")
        signature = self.signer.sign_typed_data(typed)
        scheme = build.rfq.signingScheme or self.signer.rfq_signing_scheme
        if scheme.lower() != self.signer.rfq_signing_scheme:
            raise LiveExecutionError("RFQ_SIGNING_SCHEME_MISMATCH")
        if self.signer.rfq_signing_scheme == "eip712" and not self._recovers(typed, signature):
            raise LiveExecutionError("RFQ_SIGNATURE_NOT_FROM_WALLET")
        request_id = uuid4()
        evidence = dict(
            evidence,
            order=order.summary(),
            rfq_order_id=build.rfq.orderId,
            rfq_request_id=str(request_id),
            rfq_signature=signature,
            rfq_signing_scheme=scheme,
            rfq_signed_at=self.clock().isoformat(),
        )
        # Journal the requestId and signature before the POST: a crash can only resubmit the
        # identical idempotent body, never sign a second order.
        self.journal.upsert(action.action_id, status="SIGNED", evidence=evidence)
        before = (self.rpc.erc20_balance(sell, wallet), self.rpc.erc20_balance(buy, wallet))
        evidence = dict(evidence, balances_before=[str(before[0]), str(before[1])])
        self.journal.upsert(action.action_id, evidence=evidence)
        order_id = self._submit(evidence, vendor)
        evidence = dict(evidence, rfq_status_order_id=order_id)
        record = self.journal.upsert(action.action_id, status="SUBMITTED", evidence=evidence)
        return self._settle_rfq(record, poll=True)

    def _recovers(self, typed, signature):
        from eth_account import Account
        from eth_account.messages import encode_typed_data

        from app.services.rfq_orders import order_hash

        _, full = order_hash(typed)
        recovered = Account.recover_message(encode_typed_data(full_message=full), signature=signature)
        return recovered.lower() == self.signer.address

    def _submit(self, evidence, vendor):
        from pydantic import SecretStr

        submission = RFQSubmission(
            requestId=evidence["rfq_request_id"],
            userSignature=SecretStr(evidence["rfq_signature"]),
            vendor=vendor,
            quoteId=evidence["rfq_order_id"],
            signingScheme=evidence["rfq_signing_scheme"],
        )
        return self.trading.submit_rfq(submission)

    def _settle_rfq(self, record, *, poll):
        evidence = record["evidence"]
        order = evidence["order"]
        order_id = evidence.get("rfq_status_order_id") or evidence["rfq_order_id"]
        deadline = time.monotonic() + (ORDER_POLL_SECONDS if poll else 0)
        while True:
            status, _ = self.trading.order_status(order_id)
            if status.status == "FILLED" or status.status in NOT_FILLED:
                break
            if time.monotonic() >= deadline:
                return self.journal.upsert(record["action_id"], status="SUBMITTED")
            self.sleep(2)
        if status.status in NOT_FILLED:
            # Nothing moved; drop the leftover exact allowance best-effort.
            self._revoke(record["token"] if record["side"] == "SELL" else USDT, order["spender"])
            return self.journal.upsert(
                record["action_id"], status="NOT_FILLED", reasons=["RFQ_" + status.status]
            )
        receipt = self.rpc.receipt(status.txHash) if status.txHash else None
        if not receipt or receipt.get("status") != "0x1":
            return self.journal.upsert(
                record["action_id"],
                status="RECONCILIATION_REQUIRED",
                reasons=["RFQ_FILLED_WITHOUT_SUCCESSFUL_RECEIPT"],
            )
        wallet = self.signer.address
        sell, buy = order["sell_token"], order["buy_token"]
        before = evidence.get("balances_before")
        if before:
            spent = int(before[0]) - self.rpc.erc20_balance(sell, wallet)
            received = self.rpc.erc20_balance(buy, wallet) - int(before[1])
        else:  # restarted before balances were journaled: fall back to the provider amounts
            spent, received = int(status.fromAmount or 0), int(status.toAmount or 0)
        evidence = dict(
            evidence,
            swap_tx=status.txHash,
            spent=str(spent),
            received=str(received),
            gas_used=str(int(receipt.get("gasUsed", "0x0"), 16)),
            block=str(int(receipt.get("blockNumber", "0x0"), 16)),
        )
        within = spent <= int(order["sell_amount"]) and received >= int(order["min_buy_to_wallet"])
        return self.journal.upsert(
            record["action_id"],
            status="CONFIRMED" if within else "RECONCILIATION_REQUIRED",
            swap_tx=status.txHash,
            evidence=evidence,
            reasons=[] if within else ["RFQ_FILL_OUTSIDE_SIGNED_BOUNDS"],
        )

    def _reconcile_rfq(self, record):
        evidence = record["evidence"]
        if record["status"] in {"CONFIRMED", "FAILED", "NOT_FILLED", "RECONCILIATION_REQUIRED"}:
            return record
        if record["status"] == "SIGNED":
            signed = datetime.fromisoformat(evidence["rfq_signed_at"])
            if (self.clock() - signed).total_seconds() > RESUBMIT_WINDOW_SECONDS:
                return self.journal.upsert(
                    record["action_id"],
                    status="RECONCILIATION_REQUIRED",
                    reasons=["RFQ_SUBMIT_OUTCOME_UNKNOWN_PAST_IDEMPOTENCY_WINDOW"],
                )
            try:
                order_id = self._submit(evidence, evidence["vendor"])  # same requestId and body
            except ProviderError as error:
                from app.clients.binance_trading import provider_reason

                return self.journal.upsert(
                    record["action_id"], status="SIGNED", reasons=[provider_reason(error)]
                )
            record = self.journal.upsert(
                record["action_id"],
                status="SUBMITTED",
                evidence=dict(evidence, rfq_status_order_id=order_id),
            )
        try:
            return self._settle_rfq(record, poll=False)
        except ProviderError:
            return record

    # -- helpers -------------------------------------------------------------------------
    def _approve(self, action_id, token, spender, amount):
        """Exact approval for this leg only; never unlimited. Simulated, sent, confirmed."""
        wallet = self.signer.address
        if self.rpc.allowance(token, wallet, spender) >= amount:
            return
        approve_tx = EvmTransaction.model_validate(
            {
                "from": wallet,
                "to": token,
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
        self.journal.upsert(action_id, status="APPROVING", approve_tx=approve_hash)
        if not self._confirmed(approve_hash):
            raise LiveExecutionError("APPROVAL_NOT_CONFIRMED")
        if self.rpc.allowance(token, wallet, spender) < amount:
            raise LiveExecutionError("APPROVAL_NOT_OBSERVED")

    def _revoke(self, token, spender):
        try:
            if self.rpc.allowance(token, self.signer.address, spender) == 0:
                return
            self.signer.send(
                to=token,
                data=approve_calldata(spender, 0),
                value=0,
                gas=APPROVE_GAS,
                gas_price=self.rpc.gas_price(),
            )
        except (LiveExecutionError, ProviderError, ValueError):
            pass  # best effort: the order expired, an exact leftover allowance is bounded


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
        if record["evidence"].get("route") == "RFQ" and record["evidence"].get("rfq_request_id"):
            return self._reconcile_rfq(record)
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
