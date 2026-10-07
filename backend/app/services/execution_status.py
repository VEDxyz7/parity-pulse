"""Bounded read-only reconciliation. No timeout can create or retry an order."""

import time
from datetime import UTC, datetime

from app.clients.common import ProviderError
from app.models.data import source_time
from app.models.execution import ExecutionAttempt, address
from app.services.execution_state_machine import TERMINAL, ExecutionStateMachine


class ExecutionStatusTracker:
    def __init__(self, provider, store, *, sleep=time.sleep):
        self.provider, self.store, self.sleep = provider, store, sleep
        self.machine = ExecutionStateMachine()

    def reconcile(self, attempt, *, now):
        attempt = ExecutionAttempt.model_validate_json(attempt.model_dump_json())
        if attempt.state in TERMINAL:
            return attempt
        if not attempt.external_tracking_only or attempt.quote is None or attempt.route is None:
            raise ValueError("EXISTING_EXTERNAL_ATTEMPT_REQUIRED")
        q = attempt.quote
        if (q.source == "TEST_FIXTURE") != (getattr(self.provider, "fixture_only", False) is True):
            raise ValueError("STATUS_PROVIDER_MODE_MISMATCH")
        target = "EXECUTION_UNKNOWN"
        fields = {}
        try:
            if q.route.executionMode == "RFQ":
                if attempt.order_id is None:
                    raise ValueError("Platform order ID required")
                status, received = self.provider.order_status(attempt.order_id)
                if status.orderId != attempt.order_id:
                    raise ValueError("Order binding mismatch")
                fields = {"external_status": status.status}
                target = {
                    "PENDING_VENDOR": "EXECUTION_PENDING",
                    "PENDING_ONCHAIN": "EXECUTION_PENDING",
                    "FAILED": "EXECUTION_FAILED",
                    "EXPIRED": "EXECUTION_EXPIRED",
                    "CANCELLED": "EXECUTION_CANCELLED",
                }.get(status.status, "EXECUTION_UNKNOWN")
                if status.status == "FILLED":
                    if (
                        status.txHash is None
                        or status.fromAmount != q.request.amount
                        or status.toAmount is None
                        or status.filledAt is None
                        or source_time(status.filledAt) > received
                        or source_time(status.createdAt) > source_time(status.filledAt)
                    ):
                        raise ValueError("Filled settlement fields invalid")
                    from decimal import Decimal, localcontext

                    with localcontext() as ctx:
                        ctx.prec = 256
                        minimum = Decimal(q.route.toTokenAmount) * (
                            1 - attempt.route.slippage_bps / Decimal(10000)
                        )
                    if int(status.toAmount) < minimum:
                        raise ValueError("RFQ minimum receive violated")
                    target = "EXECUTION_CONFIRMED"
                    fields.update(
                        tx_hash=status.txHash,
                        filled_quantity_base_units=status.toAmount,
                        settled_at=source_time(status.filledAt),
                    )
            else:
                if attempt.tx_hash is None:
                    raise ValueError("Transaction hash required")
                status, received = self.provider.swap_status(attempt.tx_hash)
                if status is not None:
                    tx = attempt.route.build.tx
                    if status.txHash.lower() != attempt.tx_hash.lower() or (
                        status.fromAddress,
                        status.toAddress,
                    ) != (tx.sender, tx.to):
                        raise ValueError("Transaction identity mismatch")
                    fields = {"external_status": status.status}
                    if status.status == "failed":
                        target = "EXECUTION_FAILED"
                    elif (
                        status.status == "success"
                        and not status.errorMsg
                        and int(status.height) > 0
                        and status.txType == "Swap"
                        and status.dexRouter == tx.to
                    ):
                        # Match actual settled token identities and units.
                        if not status.fromTokenDetails or not status.toTokenDetails:
                            raise ValueError("Missing settled token details")
                        sells = status.fromTokenDetails
                        buys = status.toTokenDetails
                        if (
                            len(sells) != 1
                            or len(buys) != 1
                            or address(sells[0]["tokenAddress"]) != q.request.fromTokenAddress
                            or str(sells[0]["amount"]) != q.request.amount
                            or address(buys[0]["tokenAddress"]) != q.request.toTokenAddress
                        ):
                            raise ValueError("Settled token binding mismatch")
                        quantity = str(buys[0]["amount"])
                        if int(quantity) < int(tx.minReceiveAmount):
                            raise ValueError("Minimum receive violated")
                        settled = source_time(int(status.txTime))
                        if settled > received:
                            raise ValueError("Future settlement")
                        target = "EXECUTION_CONFIRMED"
                        fields.update(
                            filled_quantity_base_units=quantity,
                            settled_at=settled,
                            fees_native_base_units=status.txFee,
                        )
            if not 0 <= (received - now).total_seconds() <= 30:
                raise ValueError("Invalid receipt time")
        except (ProviderError, ValueError, TypeError, KeyError):
            target = "EXECUTION_UNKNOWN"
            fields = {"reason_codes": ("STATUS_UNRESOLVED_NO_NEW_ORDER",)}
        if target == attempt.state:
            # Repeated pending/unknown reads remain recorded, not illegal duplicate transitions.
            result = ExecutionAttempt.model_validate(
                {
                    **attempt.model_dump(),
                    **fields,
                    "version": attempt.version + 1,
                    "updated_at": now,
                }
            )
        else:
            result = self.machine.transition(attempt, target, now=now, **fields)
        self.store.save(result, expected_version=attempt.version)
        return result

    def poll(self, attempt, *, max_polls=3, spacing_seconds=1, clock=lambda: datetime.now(UTC)):
        if type(max_polls) is not int or not 1 <= max_polls <= 10 or not 0 <= spacing_seconds <= 5:
            raise ValueError("Bounded polling required")
        for i in range(max_polls):
            attempt = self.reconcile(attempt, now=clock())
            if attempt.state in TERMINAL:
                break
            if i + 1 < max_polls:
                self.sleep(spacing_seconds)
        return attempt

    def recover(self, *, mode, now):
        # No new preparation while imported pending attempts remain unresolved.
        return [self.reconcile(a, now=now) for a in self.store.pending(mode=mode)]
