"""Exact SWAP/RFQ/approval preparation. No signing, submission or financial invention."""

from decimal import Decimal, localcontext
from uuid import UUID

from app.models.execution import (
    AllowanceState,
    ApprovalBuild,
    BuildResponse,
    EvmTransaction,
    PreparedApproval,
    PreparedRoute,
    ProviderQuote,
    RFQSubmission,
    address,
    fingerprint,
    parse_object,
)


def current_quote(quote, now):
    quote = ProviderQuote.model_validate_json(quote.model_dump_json())
    if not quote.requested_at <= now < quote.expires_at:
        raise ValueError("QUOTE_EXPIRED_REQUOTE_REBUILD_RESIMULATE")
    return quote


class ExecutionRouteBuilder:
    def build(self, quote, response, *, slippage_bps, allowance, now):
        quote = current_quote(quote, now)
        response = BuildResponse.model_validate_json(response.model_dump_json())
        expected = quote.route.model_dump(exclude={"quoteId", "executionMode", "approveTarget"})
        if (
            response.executionMode != quote.route.executionMode
            or response.routerResult is None
            or response.routerResult.model_dump() != expected
        ):
            raise ValueError("QUOTE_BUILD_ROUTE_MISMATCH")
        if quote.route.approveTarget is None:
            raise ValueError("SPENDER_UNVERIFIED")
        if allowance is None:
            raise ValueError("ALLOWANCE_UNKNOWN")
        allowance = AllowanceState.model_validate_json(allowance.model_dump_json())
        if (allowance.data_mode, allowance.token, allowance.owner, allowance.spender) != (
            quote.data_mode,
            quote.request.fromTokenAddress,
            quote.request.userWalletAddress,
            quote.route.approveTarget,
        ) or not 0 <= (now - allowance.observed_at).total_seconds() <= 120:
            raise ValueError("ALLOWANCE_IDENTITY_OR_FRESHNESS_INVALID")
        with localcontext() as ctx:
            ctx.prec = 256
            if quote.route.executionMode == "SWAP":
                tx = response.tx
                minimum = int(
                    (
                        Decimal(quote.route.toTokenAmount) * (1 - slippage_bps / Decimal(10000))
                    ).to_integral_value(rounding="ROUND_CEILING")
                )
                if (
                    tx.sender != quote.request.userWalletAddress
                    or tx.value != "0"
                    or tx.to != quote.route.approveTarget
                ):
                    raise ValueError("TRANSACTION_IDENTITY_INVALID")
                if tx.minReceiveAmount is None or not minimum <= int(tx.minReceiveAmount) <= int(
                    quote.route.toTokenAmount
                ):
                    raise ValueError("MINIMUM_RECEIVE_INVALID")
                if tx.slippagePercent != slippage_bps / Decimal(100) or tx.signatureData:
                    raise ValueError("SLIPPAGE_OR_AUXILIARY_PAYLOAD_UNVERIFIED")
            else:
                rfq = response.rfq
                if rfq.vendor != quote.route.vendorName or rfq.signatureData:
                    raise ValueError("RFQ_VENDOR_OR_AUXILIARY_PAYLOAD_MISMATCH")
                # Structured/opaque typed data is preserved. Unknown vendor schemas never
                # imply settlement equivalence or authorize signing.
        fields = dict(
            quote=quote,
            build=response,
            slippage_bps=slippage_bps,
            prepared_at=now,
            approval_required=int(allowance.amount) < int(quote.request.amount),
            allowance=allowance,
        )
        serial = {
            k: (
                v.model_dump(mode="json", by_alias=True)
                if hasattr(v, "model_dump")
                else str(v)
                if isinstance(v, Decimal)
                else v
            )
            for k, v in fields.items()
            if k != "prepared_at"
        }
        return PreparedRoute(**fields, fingerprint=fingerprint(serial))

    def rfq_submission(self, route, *, request_id, signature):
        route = PreparedRoute.model_validate_json(route.model_dump_json())
        if route.quote.route.executionMode != "RFQ":
            raise ValueError("RFQ_ONLY")
        if not isinstance(request_id, UUID) or request_id.version != 4:
            raise ValueError("Persistent UUIDv4 requestId required")
        # Formatting only: no signature generation/recovery, authorization or transport.
        return RFQSubmission(
            requestId=request_id,
            userSignature=signature,
            vendor=route.build.rfq.vendor,
            quoteId=route.build.rfq.orderId,
            signingScheme=route.build.rfq.signingScheme,
        )

    def rfq_binding(self, route, *, field_map=None):
        """Read-only EIP712 inspection. A host-verified vendor field map is required.

        No mapping is inferred from issuer or field names. Opaque bytes cannot be inspected.
        This does not establish final settlement simulation, even when bindings match.
        """
        payload = route.build.rfq
        if payload is None or payload.typedDataToSign.startswith("0x") or field_map is None:
            return False
        if set(field_map) != {
            "wallet",
            "sell_token",
            "buy_token",
            "amount",
            "minimum_receive",
            "deadline",
        }:
            return False
        typed = parse_object(payload.typedDataToSign)
        message = typed["message"]
        if any(v not in message for v in field_map.values()) or len(set(field_map.values())) != 6:
            return False
        q = route.quote
        try:
            deadline = int(message[field_map["deadline"]])
            minimum = int(message[field_map["minimum_receive"]])
            with localcontext() as ctx:
                ctx.prec = 256
                required = Decimal(q.route.toTokenAmount) * (
                    1 - route.slippage_bps / Decimal(10000)
                )
            return (
                address(message[field_map["wallet"]]) == q.request.userWalletAddress
                and address(message[field_map["sell_token"]]) == q.request.fromTokenAddress
                and address(message[field_map["buy_token"]]) == q.request.toTokenAddress
                and str(message[field_map["amount"]]) == q.request.amount
                and minimum >= required
                and minimum <= int(q.route.toTokenAmount)
                and deadline >= int(q.expires_at.timestamp())
            )
        except (ValueError, TypeError):
            return False


class ApprovalService:
    def prepare(self, route, response, *, now):
        route = PreparedRoute.model_validate_json(route.model_dump_json())
        current_quote(route.quote, now)
        if not route.approval_required:
            raise ValueError("APPROVAL_NOT_REQUIRED")
        response = ApprovalBuild.model_validate_json(response.model_dump_json())
        spender = route.quote.route.approveTarget
        amount = route.quote.request.amount
        data = response.data
        if len(data) != 138 or data[:10] != "0x095ea7b3" or data[10:34] != "0" * 24:
            raise ValueError("INVALID_APPROVE_CALLDATA")
        if (
            address("0x" + data[34:74]) != spender
            or int(data[74:138], 16) != int(amount)
            or response.dexContractAddress != spender
        ):
            raise ValueError("APPROVAL_TOKEN_SPENDER_AMOUNT_MISMATCH")
        tx = EvmTransaction(
            sender=route.quote.request.userWalletAddress,
            to=route.quote.request.fromTokenAddress,
            data=data,
            value="0",
            gas=response.gasLimit,
            gasPrice=response.gasPrice,
        )
        fields = dict(
            route_fingerprint=route.fingerprint,
            token=tx.to,
            spender=spender,
            amount=amount,
            pre_allowance_amount=route.allowance.amount,
            transaction=tx,
        )
        serial = {**fields, "transaction": tx.model_dump(mode="json", by_alias=True)}
        return PreparedApproval(**fields, fingerprint=fingerprint(serial))

    def confirmed(self, approval, route, observation, *, now):
        """Only a fresh exact owner/token/spender allowance can confirm an approval.

        A hash/submission/simulation alone never confirms approval or trade execution.
        """
        approval = PreparedApproval.model_validate_json(approval.model_dump_json())
        observation = AllowanceState.model_validate_json(observation.model_dump_json())
        return (
            approval.route_fingerprint == route.fingerprint
            and approval.token == route.quote.request.fromTokenAddress
            and approval.transaction.sender == route.quote.request.userWalletAddress
            and approval.spender == route.quote.route.approveTarget
            and approval.amount == route.quote.request.amount
            and approval.pre_allowance_amount == route.allowance.amount
            and route.quote.requested_at <= now < route.quote.expires_at
            and (observation.token, observation.spender, observation.owner, observation.data_mode)
            == (
                approval.token,
                approval.spender,
                approval.transaction.sender,
                route.quote.data_mode,
            )
            and observation.amount == approval.amount
            and 0 <= (now - observation.observed_at).total_seconds() <= 120
        )
