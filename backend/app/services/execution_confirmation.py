"""Single terminal-success predicate shared by models, tracker, state and journal.

Host request context is bound to captured provider evidence. No function submits an order.
An imported journal's creation time is not the original external order's creation time.
"""

from decimal import Decimal, localcontext

from app.models.data import source_time
from app.models.execution import SettlementEvidence, SettlementIdentity, address, units


def settlement_identity(attempt):
    if not attempt.external_tracking_only or attempt.quote is None or attempt.route is None:
        raise ValueError("EXACT_EXTERNAL_ROUTE_REQUIRED")
    return SettlementIdentity(
        execution_id=attempt.execution_id,
        request_id=attempt.request_id,
        decision_id=attempt.decision_id,
        data_mode=attempt.data_mode,
        source=attempt.source,
        execution_mode=attempt.quote.route.executionMode,
        quote_id=attempt.quote.route.quoteId,
        vendor=attempt.quote.route.vendorName,
        wallet=attempt.quote.request.userWalletAddress,
        order_id=attempt.order_id,
        route_fingerprint=attempt.route.fingerprint,
    )


def settlement_values(attempt, evidence):
    """Derive confirmation fields only from complete, consistent, exact evidence."""
    if evidence is not None:
        evidence = SettlementEvidence.model_validate_json(evidence.model_dump_json())
    if evidence is None or evidence.identity != settlement_identity(attempt):
        raise ValueError("SETTLEMENT_IDENTITY_MISMATCH_OR_MISSING")
    if (
        attempt.conflicting_tx_hashes
        or attempt.last_conflicting_tx_hash
        or attempt.settlement_conflict
    ):
        raise ValueError("CONTRADICTORY_TRANSACTION_EVIDENCE")
    if evidence.received_at < attempt.updated_at:
        raise ValueError("SETTLEMENT_RECEIPT_REGRESSION")
    q = attempt.quote
    if evidence.identity.execution_mode == "RFQ":
        s = evidence.rfq
        if (
            s.status != "FILLED"
            or s.orderId != attempt.order_id
            or s.txHash is None
            or s.fromAmount != q.request.amount
            or s.toAmount is None
            or s.filledAt is None
            or source_time(s.createdAt) > source_time(s.filledAt)
            or not q.requested_at <= source_time(s.createdAt) < q.expires_at
            or source_time(s.filledAt) > evidence.received_at
        ):
            raise ValueError("INCOMPLETE_RFQ_SETTLEMENT")
        with localcontext() as ctx:
            ctx.prec = 256
            minimum = Decimal(q.route.toTokenAmount) * (
                1 - attempt.route.slippage_bps / Decimal(10000)
            )
        if int(s.toAmount) < minimum:
            raise ValueError("RFQ_MINIMUM_RECEIVE_VIOLATED")
        tx_hash, quantity, at = s.txHash, s.toAmount, source_time(s.filledAt)
        fee = None
    else:
        s, tx = evidence.swap, attempt.route.build.tx
        if (
            tx is None
            or s.status != "success"
            or s.errorMsg
            or int(s.height) <= 0
            or s.txType != "Swap"
            or (s.fromAddress, s.toAddress, s.dexRouter) != (tx.sender, tx.to, tx.to)
            or not s.fromTokenDetails
            or not s.toTokenDetails
            or len(s.fromTokenDetails) != 1
            or len(s.toTokenDetails) != 1
        ):
            raise ValueError("INCOMPLETE_SWAP_SETTLEMENT")
        sell, buy = s.fromTokenDetails[0], s.toTokenDetails[0]
        if (
            address(sell["tokenAddress"]) != q.request.fromTokenAddress
            or units(sell["amount"]) != q.request.amount
            or address(buy["tokenAddress"]) != q.request.toTokenAddress
        ):
            raise ValueError("SETTLED_TRANSFER_MISMATCH")
        quantity = units(buy["amount"])
        if int(quantity) < int(tx.minReceiveAmount):
            raise ValueError("SWAP_MINIMUM_RECEIVE_VIOLATED")
        tx_hash, at, fee = s.txHash, source_time(int(s.txTime)), s.txFee
        if not q.requested_at <= at <= evidence.received_at:
            raise ValueError("FUTURE_SETTLEMENT")
    if attempt.tx_hash is not None and attempt.tx_hash.lower() != tx_hash.lower():
        raise ValueError("KNOWN_TRANSACTION_HASH_CONFLICT")
    if (
        evidence.corroborated_tx_hash is not None
        and evidence.corroborated_tx_hash.lower() != tx_hash.lower()
    ):
        raise ValueError("WALLET_TRANSACTION_HASH_CONFLICT")
    return dict(
        external_status="FILLED" if evidence.rfq else "success",
        tx_hash=tx_hash,
        filled_quantity_base_units=quantity,
        settled_at=at,
        fees_native_base_units=fee,
    )


def validate_confirmation(attempt):
    values = settlement_values(attempt, attempt.settlement_evidence)
    if attempt.tx_hash is None or any(getattr(attempt, k) != v for k, v in values.items()):
        raise ValueError("CONFIRMATION_NOT_DERIVED_FROM_EXACT_SETTLEMENT")
