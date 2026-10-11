"""Offline-testable receipt/event verification. Provider FILLED is never settlement proof.

Raw RPC logs are decoded here, never accepted as caller-supplied decoded events.
Any missing identity, noncanonical block, incomplete transfer or unsupported event stays
unresolved. These checks do not establish pre-execution RFQ simulation equivalence.
"""

import re
from functools import wraps

from eth_abi import decode
from eth_abi.exceptions import DecodingError
from eth_utils import keccak

from app.models.execution import EvmTransaction, address, fingerprint, units
from app.models.execution_envelope import BoundSwapEnvelope
from app.services.execution_gates import LiveExecutionError

TRANSFER = "0x" + keccak(text="Transfer(address,address,uint256)").hex()
COW_TRADE = "0x" + keccak(text="Trade(address,address,address,uint256,uint256,uint256,bytes)").hex()
INCH_FILL = "0x" + keccak(text="OrderFilled(bytes32,uint256)").hex()
PCS_FILL = "0x" + keccak(text="Fill(bytes32,address,address,uint256)").hex()


def require(condition, code):
    if not condition:
        raise LiveExecutionError(code)


def evidence_validation(operation):
    @wraps(operation)
    def checked(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except (ValueError, TypeError, KeyError, AttributeError, IndexError, DecodingError):
            raise LiveExecutionError("MALFORMED_SETTLEMENT_EVIDENCE") from None

    return checked


def topic_address(value):
    require(
        isinstance(value, str) and len(value) == 66 and value[2:26] == "0" * 24,
        "MALFORMED_EVENT_ADDRESS",
    )
    return address("0x" + value[-40:])


def canonical_receipt(rpc, tx_hash, *, confirmations=3):
    require(rpc.chain_id() == 56, "RPC_CHAIN_MISMATCH")
    receipt = rpc.receipt(tx_hash)
    if receipt is None:
        return None
    require(isinstance(receipt, dict), "MALFORMED_RECEIPT")
    require(
        receipt.get("transactionHash", "").lower() == tx_hash.lower(),
        "RECEIPT_TRANSACTION_MISMATCH",
    )
    block_number = int(receipt.get("blockNumber", "0x0"), 16)
    require(block_number > 0, "RECEIPT_BLOCK_MISSING")
    block = rpc.read("eth_getBlockByNumber", hex(block_number), False)
    require(
        isinstance(block, dict)
        and block.get("hash") == receipt.get("blockHash")
        and isinstance(block.get("hash"), str),
        "RECEIPT_BLOCK_NOT_CANONICAL",
    )
    head = int(rpc.read("eth_blockNumber"), 16)
    require(
        confirmations >= 1 and head - block_number + 1 >= confirmations, "RECEIPT_NOT_FINAL_ENOUGH"
    )
    require(receipt.get("status") in {"0x0", "0x1"}, "RECEIPT_STATUS_MISSING")
    return receipt


def wallet_transfers(receipt, *, wallet, sell, buy, sell_max, minimum_out):
    """Aggregate exact transaction logs, reject unexpected wallet debits and gross overspend."""
    logs = receipt.get("logs")
    require(isinstance(logs, list) and logs, "SETTLEMENT_TRANSFER_EVIDENCE_MISSING")
    spent = received = gross_spent = 0
    seen = set()
    for log in logs:
        require(
            isinstance(log, dict) and log.get("removed", False) is False, "REMOVED_OR_MALFORMED_LOG"
        )
        require(
            log.get("transactionHash") == receipt["transactionHash"]
            and log.get("blockHash") == receipt["blockHash"],
            "LOG_TRANSACTION_MISMATCH",
        )
        index = log.get("logIndex")
        require(isinstance(index, str) and index not in seen, "DUPLICATE_OR_MISSING_LOG_INDEX")
        seen.add(index)
        topics = log.get("topics", [])
        require(isinstance(topics, list), "MALFORMED_EVENT_TOPICS")
        if not topics or topics[0].lower() != TRANSFER:
            continue
        require(len(topics) == 3, "MALFORMED_TRANSFER_LOG")
        owner, recipient = topic_address(topics[1]), topic_address(topics[2])
        token = address(log.get("address"))
        data = log.get("data", "")
        require(isinstance(data, str) and len(data) == 66, "MALFORMED_TRANSFER_AMOUNT")
        amount = int(data, 16)
        if owner == wallet:
            require(token == sell, "UNEXPECTED_WALLET_TOKEN_DEBIT")
            gross_spent += amount
            spent += amount
        if recipient == wallet:
            if token == buy:
                received += amount
            elif token == sell:
                spent -= amount
    require(0 < spent <= gross_spent <= sell_max, "SETTLEMENT_MAX_SPEND_VIOLATED")
    require(received >= minimum_out > 0, "SETTLEMENT_MIN_OUTPUT_VIOLATED")
    return spent, received


def swap_commitment(tx_hash, expected, submission):
    """Bind host preparation to the durable signed EVM identity, never an RFQ nonce.

    Amounts are canonical uint256 base units. The plan minimum may differ from the
    prepared minimum; neither can weaken the other. Optional envelope evidence must
    agree exactly, rather than silently replacing the prepared transaction.
    """
    tx = expected["transaction"]
    try:
        prepared_minimum = int(units(tx.get("minReceiveAmount")))
        require(prepared_minimum > 0, "PREPARED_MIN_OUTPUT_INVALID")
    except (ValueError, TypeError):
        raise LiveExecutionError("PREPARED_MIN_OUTPUT_MISSING_OR_INVALID") from None
    plan_minimum = int(units(expected["minimum_out"]))
    require(plan_minimum > 0, "SETTLEMENT_MIN_OUTPUT_INVALID")
    prepared = EvmTransaction.model_validate(tx)
    nonce = submission.get("nonce") if submission is not None else expected.get("nonce")
    require(type(nonce) is int and 0 <= nonce < 2**64, "SETTLEMENT_NONCE_MISSING_OR_INVALID")
    if "nonce" in expected:
        require(
            type(expected["nonce"]) is int and expected["nonce"] == nonce,
            "SETTLEMENT_NONCE_EVIDENCE_CONFLICT",
        )
    if submission is not None:
        require(
            submission.get("identity") == tx_hash
            and submission.get("payload_digest") == fingerprint(prepared),
            "SETTLEMENT_SIGNED_IDENTITY_CONFLICT",
        )
    if "envelope" in expected:
        envelope = BoundSwapEnvelope.model_validate(expected["envelope"])
        require(envelope.nonce == nonce, "SETTLEMENT_ENVELOPE_NONCE_CONFLICT")
        require(
            envelope.transaction == prepared
            and envelope.minimum_out == prepared.minReceiveAmount
            and envelope.recipient == prepared.sender
            and envelope.spender == prepared.to
            and envelope.sell_token == expected["sell"]
            and envelope.buy_token == expected["buy"]
            and envelope.amount_in == expected["amount_in"]
            and envelope.route_fingerprint == expected["route_fingerprint"],
            "SETTLEMENT_PREPARED_ENVELOPE_CONFLICT",
        )
    return prepared, nonce, max(prepared_minimum, plan_minimum)


@evidence_validation
def verify_swap(rpc, tx_hash, expected, *, submission=None, confirmations=3, check_balances=True):
    prepared, nonce, minimum = swap_commitment(tx_hash, expected, submission)
    receipt = canonical_receipt(rpc, tx_hash, confirmations=confirmations)
    if receipt is None:
        return None
    transaction = rpc.read("eth_getTransactionByHash", tx_hash)
    require(isinstance(transaction, dict), "SETTLEMENT_TRANSACTION_MISSING")
    tx = prepared.model_dump(mode="json", by_alias=True)
    require(
        transaction.get("hash", "").lower() == tx_hash.lower()
        and transaction.get("blockHash") == receipt["blockHash"],
        "SETTLEMENT_TX_HASH_MISMATCH",
    )
    observed_nonce = transaction.get("nonce")
    require(
        isinstance(observed_nonce, str)
        and re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]{0,15})", observed_nonce) is not None,
        "SETTLEMENT_NONCE_MISSING_OR_INVALID",
    )
    require(int(observed_nonce, 16) == nonce, "SETTLEMENT_NONCE_MISMATCH")
    require(
        (
            transaction.get("from", "").lower(),
            transaction.get("to", "").lower(),
            transaction.get("input", "").lower(),
            int(transaction.get("value", "-1"), 16),
            int(transaction.get("gas", "-1"), 16),
            int(transaction.get("gasPrice", "-1"), 16),
        )
        == (
            tx["from"],
            tx["to"],
            tx["data"],
            int(tx["value"]),
            int(tx["gas"]),
            int(tx["gasPrice"]),
        ),
        "SETTLEMENT_TRANSACTION_IDENTITY_MISMATCH",
    )
    if receipt["status"] == "0x0":
        return {
            "status": "FAILED",
            "reason": "SWAP_REVERTED_ON_CHAIN",
            "nonce": nonce,
            "minimum_out": str(minimum),
            "block_hash": receipt["blockHash"],
            "block_number": receipt["blockNumber"],
        }
    spent, received = wallet_transfers(
        receipt,
        wallet=tx["from"],
        sell=expected["sell"],
        buy=expected["buy"],
        sell_max=int(units(expected["amount_in"])),
        minimum_out=minimum,
    )
    require("balances_before" in expected, "PRE_BALANCES_MISSING")
    before = expected["balances_before"]
    require(isinstance(before, list) and len(before) == 2, "PRE_BALANCES_MISSING")
    before = tuple(int(units(value)) for value in before)
    if check_balances:
        require(
            before[0] - rpc.erc20_balance(expected["sell"], tx["from"]) == spent
            and rpc.erc20_balance(expected["buy"], tx["from"]) - before[1] == received,
            "SETTLEMENT_BALANCE_LOG_CONFLICT",
        )
    return {
        "status": "CONFIRMED",
        "spent": str(spent),
        "received": str(received),
        "nonce": nonce,
        "minimum_out": str(minimum),
        "block_hash": receipt["blockHash"],
        "block_number": receipt["blockNumber"],
    }


@evidence_validation
def verify_rfq(rpc, tx_hash, order, before, *, confirmations=3):
    receipt = canonical_receipt(rpc, tx_hash, confirmations=confirmations)
    require(receipt is not None and receipt["status"] == "0x1", "RFQ_RECEIPT_NOT_SUCCESSFUL")
    require(before is not None and len(before) == 2, "RFQ_PRE_BALANCES_MISSING")
    wallet = order["wallet"]
    spent, received = wallet_transfers(
        receipt,
        wallet=wallet,
        sell=order["sell_token"],
        buy=order["buy_token"],
        sell_max=int(order["sell_amount"]),
        minimum_out=int(order["min_buy_to_wallet"]),
    )
    matches = []
    for log in receipt["logs"]:
        if log["address"].lower() != order["settlement"]:
            continue
        topics = log.get("topics", [])
        if not topics:
            continue
        data = bytes.fromhex(log["data"][2:])
        if order["vendor"] == "CowSwap" and topics[0].lower() == COW_TRADE:
            require(len(topics) == 2, "RFQ_COW_EVENT_SCHEMA")
            sell, buy, outflow, inflow, fee, uid = decode(
                ["address", "address", "uint256", "uint256", "uint256", "bytes"], data
            )
            matches.append(
                topic_address(topics[1]) == wallet
                and "0x" + uid.hex() == order["uid"]
                and sell == order["sell_token"]
                and buy == order["buy_token"]
                and outflow == spent
                and spent == int(order["sell_amount"])
                and inflow == received
                and fee == int(order["fees"])
            )
        elif order["vendor"] == "InchFusion" and topics[0].lower() == INCH_FILL:
            require(len(topics) == 1, "RFQ_INCH_EVENT_SCHEMA")
            digest, remaining = decode(["bytes32", "uint256"], data)
            matches.append(
                "0x" + digest.hex() == order["order_hash"]
                and remaining == 0
                and spent == int(order["sell_amount"])
            )
        elif order["vendor"] == "PcsXRfq" and topics[0].lower() == PCS_FILL:
            # ReactorEvents: orderHash/filler/swapper indexed, nonce in data.
            require(len(topics) == 4, "RFQ_PCS_EVENT_SCHEMA")
            (nonce,) = decode(["uint256"], data)
            matches.append(
                topics[1].lower() == order["witness_hash"]
                and topic_address(topics[3]) == wallet
                and nonce == order["nonce"]
                and spent == int(order["sell_amount"])
            )
    require(matches == [True], "RFQ_EXACT_ORDER_EVENT_MISSING_OR_CONFLICTING")
    require(
        int(before[0]) - rpc.erc20_balance(order["sell_token"], wallet) == spent
        and rpc.erc20_balance(order["buy_token"], wallet) - int(before[1]) == received,
        "RFQ_BALANCE_LOG_CONFLICT",
    )
    return {
        "tx_hash": tx_hash,
        "spent": str(spent),
        "received": str(received),
        "block_hash": receipt["blockHash"],
        "block_number": receipt["blockNumber"],
    }
