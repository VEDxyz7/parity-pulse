"""Remediated host-only execution worker. Public configuration cannot enable it.

Reuses the established route builder, simulation and RiskEngine. Application wiring
keeps every live gate blocked; no derived perpetual quote or disabled Trust fallback.
Uncertain submission recovery is observation-only and never automatically re-signs.
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, localcontext
from uuid import uuid4

from app.clients.common import ProviderError
from app.models.execution import AllowanceState, fingerprint, parse_object
from app.models.execution_envelope import BoundSwapEnvelope
from app.models.live import TERMINAL, ExecutionConsent
from app.services.execution_builders import ExecutionRouteBuilder, current_quote
from app.services.execution_gates import LIVE_GATES, LiveExecutionError
from app.services.execution_simulation import ExecutionSimulationService
from app.services.live_settlement import verify_rfq, verify_swap
from app.services.risk import RiskEngine


@dataclass(frozen=True)
class PreparedLeg:
    action_id: str
    route: object
    simulation: object
    risk_digest: str
    minimum_out: int
    order: object | None = None

    @property
    def digest(self):
        return fingerprint(
            {
                "action_id": self.action_id,
                "route": self.route.fingerprint,
                "simulation": self.simulation.payload_digest,
                "risk": self.risk_digest,
                "minimum_out": self.minimum_out,
                "order": self.order.summary() if self.order else None,
            }
        )


def validate_swap_effects(route, simulation, *, now):
    """Exact prepared identity + complete bounded wallet effects, not just SUCCESS."""
    if not ExecutionSimulationService.matches(simulation, route, now=now, mode="LIVE_READ_ONLY"):
        raise LiveExecutionError("EXACT_SIMULATION_REQUIRED")
    wallet = route.quote.request.userWalletAddress
    sell, buy = route.quote.request.fromTokenAddress, route.quote.request.toTokenAddress
    spent = gained = 0
    changes = simulation.response.balanceChanges
    if not changes:
        raise LiveExecutionError("SIMULATION_BALANCE_EVIDENCE_MISSING")
    seen = set()
    for change in changes:
        key = (change.owner, change.contractAddress.lower())
        if key in seen:
            raise LiveExecutionError("DUPLICATE_SIMULATION_BALANCE_CHANGE")
        seen.add(key)
        if change.owner != wallet:
            continue
        token = change.contractAddress.lower()
        amount = int(change.change)
        if change.tokenType != "ERC20":
            raise LiveExecutionError("SIMULATION_ASSET_TYPE_UNVERIFIED")
        if amount < 0:
            if token != sell:
                raise LiveExecutionError("SIMULATION_UNEXPECTED_WALLET_DEBIT")
            spent -= amount
        if amount > 0 and token == buy:
            gained += amount
    if not 0 < spent <= int(route.quote.request.amount):
        raise LiveExecutionError("SIMULATION_MAX_SPEND_VIOLATED")
    if gained < int(route.build.tx.minReceiveAmount):
        raise LiveExecutionError("SIMULATION_MIN_OUTPUT_VIOLATED")
    return spent, gained


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
        clock,
        gates=LIVE_GATES,
        rfq_allowlist=None,
        market_status_reader=None,
    ):
        if getattr(portfolio, "inventory", None) != "WALLET":
            raise ValueError("Verified wallet-inventory planning required")
        self.portfolio, self.trading, self.rpc = portfolio, trading, rpc
        self.signer, self.journal, self.gates = signer, journal, gates
        self.max_notional = Decimal(str(max_notional_usd))
        self.max_slippage_bps = Decimal(str(max_slippage_bps))
        self.gas_reserve_wei, self.clock = int(gas_reserve_wei), clock
        self.rfq_allowlist = rfq_allowlist or {}
        self.market_status_reader = market_status_reader
        self.risk = RiskEngine()
        portfolio.live_journal = journal

    def _risk(self, plan, action):
        now = self.clock()
        if not 0 <= (now - plan.created_at).total_seconds() <= 120:
            raise LiveExecutionError("PLAN_TOO_OLD_REEVALUATE")
        if not action.eligible_for_preparation or action.risk.status != "PASS":
            raise LiveExecutionError("ACTION_NOT_RISK_APPROVED")
        risk = self.risk.evaluate_execution(action.risk_inputs, now=now)
        if risk.status != "PASS" or risk.evidence_digest != action.risk.evidence_digest:
            raise LiveExecutionError("RISK_REVALIDATION_FAILED")
        if action.risk_inputs.data_mode != "LIVE_READ_ONLY":
            raise LiveExecutionError("DEMO_EXECUTION_FORBIDDEN")
        if action.notional_usd > self.max_notional:
            raise LiveExecutionError("LIVE_NOTIONAL_CAP")
        mark = action.route.selected_candidate.inputs
        if (
            mark.tradable is not True
            or mark.route_available is not True
            or not 0 <= (now - mark.price_timestamp).total_seconds() <= 120
        ):
            raise LiveExecutionError("MARKET_STATUS_OR_ROUTE_STALE")
        # Preserve main's conservative closed-market behavior. No new weekend exemption.
        from app.models.data import MarketStatus

        if self.market_status_reader is None:
            raise LiveExecutionError("FRESH_MARKET_STATUS_REQUIRED")
        status = MarketStatus.model_validate_json(
            self.market_status_reader(action.asset).model_dump_json()
        )
        if (
            status.data_mode != "LIVE"
            or status.data_quality != "LIVE"
            or status.source_timestamp is None
            or not 0 <= (now - status.source_timestamp).total_seconds() <= 120
            or status.ticker not in {action.asset, "US_EQUITY"}
        ):
            raise LiveExecutionError("MARKET_STATUS_OR_ROUTE_STALE")
        if status.state not in {"regular", "OPEN"} or mark.market_state not in {"regular", "OPEN"}:
            raise LiveExecutionError("UNDERLYING_MARKET_NOT_OPEN")
        return risk

    def prepare(self, plan, action):
        """Read-only construction. A result is not permission to sign or submit."""
        from app.models.execution import QuoteRequest
        from app.services.rfq_orders import Expected, verify

        risk = self._risk(plan, action)
        funding = plan.snapshot.inputs.funding
        wallet = self.signer.address
        token = action.route.selected_representation.contract
        if funding.wallet != wallet or funding.asset.chain_id != "56":
            raise LiveExecutionError("PLAN_WALLET_OR_CHAIN_MISMATCH")
        if self.rpc.chain_id() != 56:
            raise LiveExecutionError("RPC_CHAIN_MISMATCH")
        with localcontext() as ctx:
            ctx.prec = 256
            cash_units = int(
                action.notional_usd / funding.unit_price_usd * Decimal(10) ** funding.asset.decimals
            )
            amount = cash_units if action.side == "BUY" else int(action.quantity_base_units)
            out = int(action.quantity_base_units) if action.side == "BUY" else cash_units
            slip = action.risk_inputs.slippage_bps
            minimum = int(
                (out * (1 - slip / Decimal(10000))).to_integral_value(rounding=ROUND_CEILING)
            )
        if slip > self.max_slippage_bps:
            raise LiveExecutionError("SLIPPAGE_LIMIT")
        sell, buy = (
            (funding.asset.contract, token)
            if action.side == "BUY"
            else (token, funding.asset.contract)
        )
        request = QuoteRequest(
            binanceChainId="56",
            amount=str(amount),
            fromTokenAddress=sell,
            toTokenAddress=buy,
            userWalletAddress=wallet,
        )
        offered = self.trading.quote(request, mode="LIVE_READ_ONLY")
        # Explicit economics and stable tie break. Mode comes from provider, not issuer.
        quotes = sorted(offered, key=lambda q: (-int(q.route.toTokenAmount), q.route.quoteId))
        if not quotes:
            raise LiveExecutionError("NO_ROUTE")
        quote = quotes[0]
        current_quote(quote, self.clock())
        if quote.route.priceImpactPercent is None:
            raise LiveExecutionError("PRICE_IMPACT_UNAVAILABLE")
        if abs(quote.route.priceImpactPercent) * 100 > self.max_slippage_bps:
            raise LiveExecutionError("PRICE_IMPACT_LIMIT")
        if int(quote.route.toTokenAmount) < minimum:
            raise LiveExecutionError("QUOTE_BELOW_PLAN_MINIMUM")
        spender = quote.route.approveTarget
        if spender is None or not self.rpc.has_code(spender):
            raise LiveExecutionError("SPENDER_CONTRACT_UNVERIFIED")
        held = self.rpc.erc20_balance(sell, wallet)
        if held < amount:
            raise LiveExecutionError("INSUFFICIENT_ON_CHAIN_BALANCE")
        allowed = self.rpc.allowance(sell, wallet, spender)
        # Broad existing allowances cannot silently authorize a new plan. Existing
        # ApprovalService prepares exact scoped approvals as separate confirmed operations.
        if allowed != amount:
            raise LiveExecutionError("EXACT_ALLOWANCE_REPREPARATION_REQUIRED")
        allowance = AllowanceState(
            data_mode="LIVE_READ_ONLY",
            token=sell,
            owner=wallet,
            spender=spender,
            amount=str(allowed),
            observed_at=self.clock(),
            source="BSC_RPC",
        )
        response = self.trading.build(quote, slippage_bps=slip)
        if response.executionMode == "RFQ":
            self.journal.capture_rfq(
                response.model_dump(mode="json"),
                verdict="INCOMPLETE",
                reason="PROVIDER_PAYLOAD_DEPLOYMENT_NOT_VERIFIED",
            )
        route = ExecutionRouteBuilder().build(
            quote, response, slippage_bps=slip, allowance=allowance, now=self.clock()
        )
        simulation = ExecutionSimulationService(self.trading).simulate(route, now=self.clock())
        order = None
        if quote.route.executionMode == "SWAP":
            if int(route.build.tx.minReceiveAmount) < minimum:
                raise LiveExecutionError("BUILD_MINIMUM_BELOW_PLAN_BOUND")
            validate_swap_effects(route, simulation, now=self.clock())
        else:
            order = verify(
                quote.route.vendorName,
                parse_object(route.build.rfq.typedDataToSign),
                Expected(wallet, sell, amount, buy, minimum, int(self.clock().timestamp())),
                self.rfq_allowlist,
            )
            if order.spender != spender:
                raise LiveExecutionError("RFQ_SPENDER_MISMATCH")
        self._risk(plan, action)  # reads/build/simulation can consume evidence lifetime
        return PreparedLeg(
            action.action_id, route, simulation, risk.evidence_digest, minimum, order
        )

    def execute(self, plan_id, *, prepared, confirmations):
        """Host-only prepared objects. HTTP accepts consent, never execution safety facts."""
        plan = self.portfolio.store.get(plan_id, mode=self.portfolio.mode)
        if plan.status != "REBALANCE_REQUIRED":
            raise LiveExecutionError("PLAN_NOT_ACTIONABLE")
        if len(prepared) != len(plan.actions) or len(confirmations) != len(plan.actions):
            raise LiveExecutionError("EXACT_PREPARED_PLAN_CONFIRMATIONS_REQUIRED")
        results = []
        for action in sorted(plan.actions, key=lambda a: a.priority):
            leg = next((p for p in prepared if p.action_id == action.action_id), None)
            consent = next((c for c in confirmations if c.action_id == action.action_id), None)
            if leg is None or consent is None:
                raise LiveExecutionError("EXACT_PREPARED_PLAN_CONFIRMATIONS_REQUIRED")
            self.gates.require(
                leg.route.quote.route.executionMode, wallet=self.signer.kind != "LOCAL_KEY"
            )
            result = self._leg(plan, action, leg, consent)
            results.append(result)
            if result["status"] != "CONFIRMED":
                break
        return results

    def _leg(self, plan, action, leg, consent):
        mode = leg.route.quote.route.executionMode
        self.gates.require(mode, wallet=self.signer.kind != "LOCAL_KEY")
        old = self.journal.get(action.action_id)
        if old is not None:
            return old  # use explicit read-only reconcile; never restart a live leg
        record, owner = self.journal.claim(
            action.action_id,
            wallet=self.signer.address,
            intent_digest=leg.digest,
            plan_id=str(plan.plan_id),
            asset=action.asset,
            side=action.side,
            token=action.route.selected_representation.contract,
            notional_usd=action.notional_usd,
            signer=self.signer.kind,
        )
        if owner is None:
            return record
        try:
            risk = self._risk(plan, action)
            if risk.evidence_digest != leg.risk_digest:
                raise LiveExecutionError("PREPARED_RISK_EVIDENCE_CHANGED")
            current_quote(leg.route.quote, self.clock())
            consent = ExecutionConsent.model_validate_json(consent.model_dump_json())
            if consent.expires_at > leg.route.quote.expires_at:
                raise LiveExecutionError("CONFIRMATION_OUTLIVES_QUOTE")
            self.journal.consume_consent(consent, payload_digest=leg.digest, now=self.clock())
            request = leg.route.quote.request
            if self.rpc.chain_id() != 56 or request.userWalletAddress != self.signer.address:
                raise LiveExecutionError("SUBMISSION_WALLET_OR_CHAIN_CHANGED")
            if self.rpc.allowance(
                request.fromTokenAddress, self.signer.address, leg.route.quote.route.approveTarget
            ) != int(request.amount):
                raise LiveExecutionError("EXACT_ALLOWANCE_REPREPARATION_REQUIRED")
            if self.rpc.erc20_balance(request.fromTokenAddress, self.signer.address) < int(
                request.amount
            ):
                raise LiveExecutionError("INSUFFICIENT_ON_CHAIN_BALANCE")
            if mode == "RFQ":
                return self._submit_rfq(action, leg)
            validate_swap_effects(leg.route, leg.simulation, now=self.clock())
            # Current provider only simulates from/to/value/data. Explicitly preserve this
            # blocker; neither a mock result nor signed-order bound proves equivalence.
            if not leg.simulation.live_equivalence_verified:
                raise LiveExecutionError("SWAP_GAS_SENSITIVE_EQUIVALENCE_UNVERIFIED")
            tx = leg.route.build.tx
            if self.rpc.native_balance(self.signer.address) < (
                int(tx.gas) * int(tx.gasPrice) + int(tx.value) + self.gas_reserve_wei
            ):
                raise LiveExecutionError("INSUFFICIENT_NATIVE_GAS_AND_RESERVE")
            evidence = {
                "route": "SWAP",
                "transaction": tx.model_dump(mode="json", by_alias=True),
                "sell": leg.route.quote.request.fromTokenAddress,
                "buy": leg.route.quote.request.toTokenAddress,
                "amount_in": leg.route.quote.request.amount,
                "minimum_out": str(leg.minimum_out),
                "payload_digest": leg.digest,
                "route_fingerprint": leg.route.fingerprint,
                "balances_before": [
                    str(
                        self.rpc.erc20_balance(
                            leg.route.quote.request.fromTokenAddress, self.signer.address
                        )
                    ),
                    str(
                        self.rpc.erc20_balance(
                            leg.route.quote.request.toTokenAddress, self.signer.address
                        )
                    ),
                ],
            }
            self.journal.upsert(action.action_id, status="QUOTED", evidence=evidence)
            return self._broadcast(action.action_id, tx, route=leg.route)
        except (LiveExecutionError, ProviderError, ValueError, ArithmeticError) as error:
            attempted = self.journal.submission(action.action_id, "SWAP") or (
                self.journal.submission(action.action_id, "RFQ")
            )
            return self.journal.upsert(
                action.action_id,
                status="SUBMISSION_UNKNOWN" if attempted else "REJECTED",
                reasons=[
                    "SUBMISSION_OUTCOME_UNKNOWN_RECONCILE"
                    if attempted
                    else getattr(error, "code", None)
                    or getattr(error, "kind", None)
                    or "EXECUTION_PREREQUISITES_FAILED"
                ],
            )

    def _broadcast(self, action_id, tx, *, route=None):
        self.gates.require("SWAP", wallet=self.signer.kind != "LOCAL_KEY")
        prepared = self.signer.prepare(tx)
        if prepared.payload_digest != fingerprint(tx):
            raise LiveExecutionError("SIGNED_PREPARED_PAYLOAD_CONFLICT")
        if route is not None:
            envelope = BoundSwapEnvelope.bind(route, nonce=prepared.nonce)
            envelope.matches(route, tx, nonce=prepared.nonce)
            record = self.journal.get(action_id)
            self.journal.upsert(
                action_id,
                evidence={
                    **record["evidence"],
                    "envelope": envelope.model_dump(mode="json", by_alias=True),
                },
            )
        self.journal.begin_submission(
            action_id,
            kind="SWAP",
            identity=prepared.tx_hash,
            nonce=prepared.nonce,
            payload_digest=prepared.payload_digest,
        )
        self.journal.upsert(action_id, swap_tx=prepared.tx_hash)
        try:
            self.signer.broadcast(prepared, journal=self.journal, action_id=action_id, kind="SWAP")
        except Exception:
            # After the boundary all exceptions are ambiguous, even malformed RPC success.
            return self.journal.upsert(
                action_id,
                status="SUBMISSION_UNKNOWN",
                reasons=["BROADCAST_OUTCOME_UNKNOWN_RECONCILE"],
            )
        return self.journal.upsert(action_id, status="SUBMITTED")

    def _submit_rfq(self, action, leg):
        self.gates.require("RFQ", wallet=self.signer.kind != "LOCAL_KEY")
        if not leg.simulation.live_equivalence_verified:
            raise LiveExecutionError("RFQ_SETTLEMENT_EQUIVALENCE_UNVERIFIED")
        from app.models.execution import RFQSubmission
        from app.services.rfq_orders import order_hash

        typed = parse_object(leg.route.build.rfq.typedDataToSign)
        digest, _ = order_hash(typed)
        if leg.order is None or digest != leg.order.order_hash:
            raise LiveExecutionError("RFQ_SIGNING_PAYLOAD_CHANGED")
        if self.signer.rfq_signing_scheme != "eip712":
            raise LiveExecutionError("RFQ_CONTRACT_WALLET_SUBMIT_RUNTIME_UNVERIFIED")
        current_quote(leg.route.quote, self.clock())
        if int(self.clock().timestamp()) >= leg.order.deadline:
            raise LiveExecutionError("RFQ_ORDER_EXPIRED")
        signature = self.signer.sign_typed_data(typed, order=leg.order)
        from eth_account import Account
        from eth_account.messages import encode_typed_data

        _, full = order_hash(typed)
        try:
            recovered = Account.recover_message(
                encode_typed_data(full_message=full), signature=signature.get_secret_value()
            ).lower()
        except (ValueError, TypeError, AttributeError):
            raise LiveExecutionError("RFQ_SIGNATURE_MALFORMED") from None
        if recovered != self.signer.address:
            raise LiveExecutionError("RFQ_SIGNATURE_NOT_FROM_WALLET")
        submission = RFQSubmission(
            requestId=uuid4(),
            userSignature=signature,
            vendor=leg.order.vendor,
            quoteId=leg.route.build.rfq.orderId,
            signingScheme="EIP712",
        )
        wallet = self.signer.address
        evidence = {
            "route": "RFQ",
            "order": leg.order.summary(),
            "rfq_request_id": str(submission.requestId),
            "rfq_order_id": submission.quoteId,
            "balances_before": [
                str(self.rpc.erc20_balance(leg.order.sell_token, wallet)),
                str(self.rpc.erc20_balance(leg.order.buy_token, wallet)),
            ],
        }
        self.journal.upsert(action.action_id, status="SIGNED", evidence=evidence)
        self.journal.begin_submission(
            action.action_id,
            kind="RFQ",
            identity=str(submission.requestId),
            nonce=None,
            payload_digest=leg.digest,
        )
        try:
            order_id = self.trading.submit_rfq(submission)
        except Exception:
            return self.journal.upsert(
                action.action_id,
                status="SUBMISSION_UNKNOWN",
                reasons=["RFQ_SUBMISSION_OUTCOME_UNKNOWN_RECONCILE"],
            )
        return self.journal.upsert(
            action.action_id,
            status="SUBMITTED",
            evidence={**evidence, "rfq_status_order_id": order_id},
        )

    def reconcile(self, action_id):
        """Read-only, same complete verification on first settlement and every recovery."""
        record = self.journal.get(action_id)
        if record is None:
            raise LookupError("Execution action unavailable")
        if record["status"] in {"CONFIRMED", "FAILED"}:
            # Recheck the original block, not today's mutable account balances. A
            # temporary RPC outage retains a wallet lock until this is established.
            try:
                evidence = record["evidence"]
                if not isinstance(evidence, dict):
                    raise LiveExecutionError("SETTLEMENT_EVIDENCE_MISSING_OR_INVALID")
                settlement = evidence.get("settlement", {})
                if not isinstance(settlement, dict):
                    raise LiveExecutionError("SETTLEMENT_EVIDENCE_MISSING_OR_INVALID")
                if self.rpc.chain_id() != 56:
                    raise LiveExecutionError("RPC_CHAIN_MISMATCH")
                block = self.rpc.read("eth_getBlockByNumber", settlement["block_number"], False)
                if not isinstance(block, dict) or block.get("hash") != settlement["block_hash"]:
                    raise LiveExecutionError("SETTLEMENT_BLOCK_REORG")
                route = record["evidence"].get("route")
                if route not in {"SWAP", "RFQ"}:
                    raise LiveExecutionError("SETTLEMENT_ROUTE_MISSING_OR_INVALID")
                if route == "SWAP" or self.journal.submission(action_id, "SWAP"):
                    # Recheck immutable identity/nonce/minimum/transfers on restart.
                    # Today's balances may legitimately change after a confirmed fill.
                    result = self._swap_settlement(record, check_balances=False)
                    if (
                        result is None
                        or result != settlement
                        or result["status"] != record["status"]
                    ):
                        raise LiveExecutionError("SETTLEMENT_COMMITMENT_CHANGED")
            except (LiveExecutionError, ProviderError, ValueError, TypeError, KeyError) as error:
                reason = (
                    "SETTLEMENT_BLOCK_REORG_RECONCILE"
                    if getattr(error, "code", None) == "SETTLEMENT_BLOCK_REORG"
                    else "INCOMPLETE_OR_CONFLICTING_SETTLEMENT_EVIDENCE"
                )
                return self.journal.reopen_reorg(action_id, reason=reason)
        if record["status"] in TERMINAL:
            return record
        evidence = record["evidence"]
        try:
            if not isinstance(evidence, dict):
                raise LiveExecutionError("SETTLEMENT_EVIDENCE_MISSING_OR_INVALID")
            if "settlement" in evidence and not isinstance(evidence["settlement"], dict):
                raise LiveExecutionError("SETTLEMENT_EVIDENCE_MISSING_OR_INVALID")
            if evidence.get("route") not in {"SWAP", "RFQ"}:
                raise LiveExecutionError("SETTLEMENT_ROUTE_MISSING_OR_INVALID")
            if evidence.get("route") == "RFQ" and self.journal.submission(action_id, "SWAP"):
                raise LiveExecutionError("SETTLEMENT_SUBMISSION_KIND_CONFLICT")
            if evidence.get("route") == "RFQ":
                order_id = evidence.get("rfq_status_order_id")
                if not order_id:
                    raise LiveExecutionError("RFQ_SUBMISSION_ID_UNKNOWN_NO_RESUBMIT")
                status, _ = self.trading.order_status(order_id)
                # Cancellation/expiry can race with a fill. Provider terminal state alone
                # proves neither NOT_FILLED nor absence of a prior settlement.
                if status.status != "FILLED" or not status.txHash:
                    raise LiveExecutionError("RFQ_TERMINAL_NONFILL_REQUIRES_CHAIN_RECONCILIATION")
                result = verify_rfq(
                    self.rpc, status.txHash, evidence["order"], evidence.get("balances_before")
                )
                result["status"] = "CONFIRMED"
            else:
                result = self._swap_settlement(record)
                if result is None:
                    return record
            return self.journal.upsert(
                action_id,
                status=result["status"],
                evidence={**evidence, "settlement": result},
                reasons=[result["reason"]] if result.get("reason") else [],
            )
        except (LiveExecutionError, ProviderError, ValueError, TypeError, KeyError):
            return self.journal.upsert(
                action_id,
                status="RECONCILIATION_REQUIRED",
                reasons=["INCOMPLETE_OR_CONFLICTING_SETTLEMENT_EVIDENCE"],
            )

    def _swap_settlement(self, record, *, check_balances=True):
        action_id = record["action_id"]
        if record["evidence"].get("route") != "SWAP" or self.journal.submission(action_id, "RFQ"):
            raise LiveExecutionError("SETTLEMENT_SUBMISSION_KIND_CONFLICT")
        attempt = self.journal.submission(action_id, "SWAP")
        if not attempt:
            raise LiveExecutionError("EXECUTION_INTERRUPTED_RECONCILE_IDENTITY")
        if record.get("swap_tx") and attempt["identity"] != record["swap_tx"]:
            raise LiveExecutionError("SUBMISSION_HASH_CONFLICT")
        # Crash before swap_tx assignment still has the durable signed identity.
        if not record.get("swap_tx"):
            self.journal.upsert(action_id, swap_tx=attempt["identity"])
        return verify_swap(
            self.rpc,
            attempt["identity"],
            record["evidence"],
            submission=attempt,
            check_balances=check_balances,
        )
