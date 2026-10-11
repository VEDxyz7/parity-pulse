"""Immutable BSC envelope bindings. No claim that opaque calldata is decoded."""

from typing import Literal

from pydantic import Field

from app.models.execution import (
    Address,
    Digest,
    EvmTransaction,
    ExecutionModel,
    PreparedRoute,
    Units,
    fingerprint,
)


class BoundSwapEnvelope(ExecutionModel):
    chain_id: Literal[56] = 56
    nonce: int = Field(strict=True, ge=0, lt=2**64)
    transaction: EvmTransaction
    sell_token: Address
    buy_token: Address
    amount_in: Units
    minimum_out: Units
    recipient: Address
    spender: Address
    route_fingerprint: Digest
    # Provider metadata and byte fingerprints are not a verified ABI interpretation.
    calldata_semantics_verified: Literal[False] = False

    @classmethod
    def bind(cls, route, *, nonce):
        route = PreparedRoute.model_validate_json(route.model_dump_json())
        q, tx = route.quote, route.build.tx
        return cls(
            nonce=nonce,
            transaction=tx,
            sell_token=q.request.fromTokenAddress,
            buy_token=q.request.toTokenAddress,
            amount_in=q.request.amount,
            minimum_out=tx.minReceiveAmount,
            recipient=q.request.userWalletAddress,
            spender=q.route.approveTarget,
            route_fingerprint=route.fingerprint,
        )

    def matches(self, route, tx, *, nonce):
        from app.services.execution_gates import LiveExecutionError

        bound = type(self).bind(route, nonce=nonce)
        if (
            self != bound
            or fingerprint(tx) != fingerprint(self.transaction)
            or self.transaction.sender != self.recipient
        ):
            raise LiveExecutionError("APPROVED_TRANSACTION_ENVELOPE_CHANGED")
