"""Synthetic raw RPC/event fixtures; no claim of real settlement or deployed compatibility."""

import copy
from types import SimpleNamespace

import pytest
from eth_abi import encode

from app.services.execution_gates import LiveExecutionError
from app.services.live_settlement import (
    COW_TRADE,
    INCH_FILL,
    PCS_FILL,
    TRANSFER,
    verify_rfq,
    verify_swap,
)
from app.services.rfq_orders import verify
from backend.tests.fixtures.rfq_orders import (
    ALLOW,
    EXPECTED,
    OTHER,
    TOKEN,
    USDT,
    WALLET,
    cow,
    inch,
    pcsx,
)

HASH = "0x" + "1" * 64
BLOCK = "0x" + "2" * 64


def topic(addr):
    return "0x" + addr[2:].rjust(64, "0")


def log(contract, topics, data, index):
    return {
        "address": contract,
        "topics": topics,
        "data": data,
        "logIndex": hex(index),
        "transactionHash": HASH,
        "blockHash": BLOCK,
        "removed": False,
    }


def transfer(token, owner, recipient, amount, index):
    return log(
        token,
        [TRANSFER, topic(owner), topic(recipient)],
        "0x" + encode(["uint256"], [amount]).hex(),
        index,
    )


def rpc_fixture(vendor="CowSwap"):
    factory = {"CowSwap": cow, "InchFusion": inch, "PcsXRfq": pcsx}[vendor]
    order = verify(vendor, factory(), EXPECTED, ALLOW).summary()
    spent, received = int(order["sell_amount"]), int(order["min_buy_to_wallet"])
    receipt = {
        "transactionHash": HASH,
        "blockNumber": "0x64",
        "blockHash": BLOCK,
        "status": "0x1",
        "logs": [
            transfer(USDT, WALLET, OTHER, spent, 0),
            transfer(TOKEN, OTHER, WALLET, received, 1),
        ],
    }
    if vendor == "CowSwap":
        receipt["logs"].append(
            log(
                order["settlement"],
                [COW_TRADE, topic(WALLET)],
                "0x"
                + encode(
                    ["address", "address", "uint256", "uint256", "uint256", "bytes"],
                    [USDT, TOKEN, spent, received, 0, bytes.fromhex(order["uid"][2:])],
                ).hex(),
                2,
            )
        )
    elif vendor == "InchFusion":
        receipt["logs"].append(
            log(
                order["settlement"],
                [INCH_FILL],
                "0x"
                + encode(["bytes32", "uint256"], [bytes.fromhex(order["order_hash"][2:]), 0]).hex(),
                2,
            )
        )
    else:
        receipt["logs"].append(
            log(
                order["settlement"],
                [PCS_FILL, order["witness_hash"], topic(OTHER), topic(WALLET)],
                "0x" + encode(["uint256"], [order["nonce"]]).hex(),
                2,
            )
        )
    tx = {
        "from": WALLET,
        "to": OTHER,
        "input": "0x1234",
        "value": "0x0",
        "gas": "0x30d40",
        "gasPrice": "0x1",
        "hash": HASH,
        "blockHash": BLOCK,
    }
    rpc = SimpleNamespace(chain_id=lambda: 56, receipt=lambda _: receipt)
    rpc.erc20_balance = lambda token, _: 100 * spent - spent if token == USDT else received
    rpc.read = lambda method, *args: {
        "eth_getBlockByNumber": {"hash": BLOCK},
        "eth_blockNumber": "0x66",
        "eth_getTransactionByHash": tx,
    }[method]
    expected = {
        "transaction": {
            "from": WALLET,
            "to": OTHER,
            "data": "0x1234",
            "value": "0",
            "gas": "200000",
            "gasPrice": "1",
        },
        "sell": USDT,
        "buy": TOKEN,
        "amount_in": str(spent),
        "minimum_out": str(received),
        "balances_before": [str(100 * spent), "0"],
    }
    return rpc, receipt, tx, order, expected


def test_swap_bounded_transfers_and_exact_transaction_required():
    rpc, _, _, _, expected = rpc_fixture()
    assert verify_swap(rpc, HASH, expected)["status"] == "CONFIRMED"


@pytest.mark.parametrize(
    "defect",
    [
        "zero_output",
        "excessive_spend",
        "empty_logs",
        "wrong_hash",
        "wrong_wallet",
        "wrong_token",
        "removed_log",
        "duplicate_log",
        "wrong_block",
        "changed_calldata",
        "changed_target",
        "changed_gas",
        "missing_prebalances",
        "balance_conflict",
    ],
)
def test_swap_original_false_confirmations_rejected(defect):
    rpc, receipt, tx, _, expected = rpc_fixture()
    if defect == "zero_output":
        receipt["logs"][1]["data"] = "0x" + "0" * 64
    elif defect == "excessive_spend":
        receipt["logs"][0]["data"] = "0x" + format(int(expected["amount_in"]) * 2, "064x")
    elif defect == "empty_logs":
        receipt["logs"] = []
    elif defect == "wrong_hash":
        receipt["transactionHash"] = "0x" + "3" * 64
    elif defect == "wrong_wallet":
        receipt["logs"][1]["topics"][2] = topic(OTHER)
    elif defect == "wrong_token":
        receipt["logs"][0]["address"] = OTHER
    elif defect == "removed_log":
        receipt["logs"][1]["removed"] = True
    elif defect == "duplicate_log":
        receipt["logs"].append(copy.deepcopy(receipt["logs"][0]))
    elif defect == "wrong_block":
        receipt["blockHash"] = "0x" + "3" * 64
    elif defect.startswith("changed"):
        field = {"changed_calldata": "input", "changed_target": "to", "changed_gas": "gas"}[defect]
        tx[field] = "0x1235" if field != "to" else TOKEN
    elif defect == "missing_prebalances":
        expected.pop("balances_before")
    else:
        rpc.erc20_balance = lambda *_: 0
    with pytest.raises((LiveExecutionError, ValueError)):
        verify_swap(rpc, HASH, expected)


@pytest.mark.parametrize("vendor", ["CowSwap", "InchFusion", "PcsXRfq"])
def test_exact_protocol_order_event_and_wallet_transfers(vendor):
    rpc, _, _, order, expected = rpc_fixture(vendor)
    result = verify_rfq(rpc, HASH, order, expected["balances_before"])
    assert int(result["spent"]) > 0 and int(result["received"]) >= EXPECTED.min_buy


@pytest.mark.parametrize("vendor", ["CowSwap", "InchFusion", "PcsXRfq"])
@pytest.mark.parametrize(
    "defect",
    [
        "wrong_order",
        "wrong_contract",
        "wrong_wallet",
        "wrong_token",
        "wrong_amount",
        "missing_prebalances",
        "receipt_only",
    ],
)
def test_rfq_wrong_order_receipts_cannot_confirm(vendor, defect):
    rpc, receipt, _, order, expected = rpc_fixture(vendor)
    before = expected["balances_before"]
    if defect == "wrong_order":
        key = {"CowSwap": "uid", "InchFusion": "order_hash", "PcsXRfq": "witness_hash"}[vendor]
        order[key] = "0x" + "f" * (112 if vendor == "CowSwap" else 64)
    elif defect == "wrong_contract":
        receipt["logs"][2]["address"] = OTHER
    elif defect == "wrong_wallet":
        order["wallet"] = OTHER
    elif defect == "wrong_token":
        order["sell_token"] = OTHER
    elif defect == "wrong_amount":
        order["min_buy_to_wallet"] = str(EXPECTED.min_buy + 1)
    elif defect == "missing_prebalances":
        before = None
    else:
        receipt["logs"] = []
    with pytest.raises((LiveExecutionError, ValueError)):
        verify_rfq(rpc, HASH, order, before)


def test_finality_reorg_and_chain_are_checked():
    rpc, _, _, _, expected = rpc_fixture()
    rpc.chain_id = lambda: 1
    with pytest.raises(LiveExecutionError, match="CHAIN"):
        verify_swap(rpc, HASH, expected)
    rpc.chain_id = lambda: 56
    rpc.read = lambda *args: {"hash": BLOCK} if args[0] == "eth_getBlockByNumber" else "0x64"
    with pytest.raises(LiveExecutionError, match="NOT_FINAL"):
        verify_swap(rpc, HASH, expected)


@pytest.mark.parametrize("vendor", ["CowSwap", "InchFusion", "PcsXRfq"])
def test_malformed_abi_is_typed_failure_not_receipt_success(vendor):
    rpc, receipt, _, order, expected = rpc_fixture(vendor)
    receipt["logs"][2]["data"] = "0x1234"
    with pytest.raises(LiveExecutionError):
        verify_rfq(rpc, HASH, order, expected["balances_before"])


@pytest.mark.parametrize("defect", ["topics", "null_hash", "null_receipt", "prebalances"])
def test_malformed_swap_settlement_remains_unverified(defect):
    rpc, receipt, _, _, expected = rpc_fixture()
    if defect == "topics":
        receipt["logs"][0]["topics"] = 4
    elif defect == "null_hash":
        receipt["transactionHash"] = None
    elif defect == "null_receipt":
        rpc.receipt = lambda _: []
    else:
        expected["balances_before"] = []
    with pytest.raises(LiveExecutionError):
        verify_swap(rpc, HASH, expected)
