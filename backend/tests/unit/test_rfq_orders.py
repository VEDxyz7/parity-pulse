"""Synthetic RFQ orders built from vendor public specifications (no live payload captured)."""

import copy

import pytest

from app.services.rfq_orders import (
    NO_PARTIAL_FILLS,
    PERMIT2,
    Expected,
    RFQRejected,
    parse_allowlist,
    verify,
)

NOW = 1_791_640_000
WALLET = "0x" + "a" * 40
OTHER = "0x" + "e" * 40
USDT = "0x55d398326f99059ff775485246999027b3197955"
TOKEN = "0xa9ee28c80f960b889dfbd1902055218cba016f75"
REACTOR = "0x" + "d" * 40
COW = "0x9008d19f58aabd9ed0d60971565aa8510560ab41"
INCH = "0x111111125421ca6dc452d289314280a0f8842a65"
E18 = 10**18
DOMAIN_TYPE = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
    {"name": "verifyingContract", "type": "address"},
]
EXPECTED = Expected(
    wallet=WALLET, sell_token=USDT, sell_max=10 * E18, buy_token=TOKEN, min_buy=42 * 10**15, now=NOW
)
ALLOW = parse_allowlist(f"PcsXRfq:{REACTOR}")


def cow(**m):
    message = {
        "sellToken": USDT,
        "buyToken": TOKEN,
        "receiver": WALLET,
        "sellAmount": str(10 * E18),
        "buyAmount": str(42 * 10**15),
        "validTo": NOW + 120,
        "appData": "0x" + "0" * 64,
        "feeAmount": "0",
        "kind": "sell",
        "partiallyFillable": False,
        "sellTokenBalance": "erc20",
        "buyTokenBalance": "erc20",
        **m,
    }
    return {
        "types": {
            "EIP712Domain": DOMAIN_TYPE,
            "Order": [
                {"name": "sellToken", "type": "address"},
                {"name": "buyToken", "type": "address"},
                {"name": "receiver", "type": "address"},
                {"name": "sellAmount", "type": "uint256"},
                {"name": "buyAmount", "type": "uint256"},
                {"name": "validTo", "type": "uint32"},
                {"name": "appData", "type": "bytes32"},
                {"name": "feeAmount", "type": "uint256"},
                {"name": "kind", "type": "string"},
                {"name": "partiallyFillable", "type": "bool"},
                {"name": "sellTokenBalance", "type": "string"},
                {"name": "buyTokenBalance", "type": "string"},
            ],
        },
        "domain": {"name": "Gnosis Protocol", "version": "v2", "chainId": 56, "verifyingContract": COW},
        "primaryType": "Order",
        "message": message,
    }


def inch(traits=None, **m):
    if traits is None:
        traits = NO_PARTIAL_FILLS | ((NOW + 120) << 80)
    message = {
        "salt": "1",
        "maker": WALLET,
        "receiver": "0x" + "0" * 40,
        "makerAsset": USDT,
        "takerAsset": TOKEN,
        "makingAmount": str(10 * E18),
        "takingAmount": str(42 * 10**15),
        "makerTraits": str(traits),
        **m,
    }
    return {
        "types": {
            "EIP712Domain": DOMAIN_TYPE,
            "Order": [
                {"name": "salt", "type": "uint256"},
                {"name": "maker", "type": "address"},
                {"name": "receiver", "type": "address"},
                {"name": "makerAsset", "type": "address"},
                {"name": "takerAsset", "type": "address"},
                {"name": "makingAmount", "type": "uint256"},
                {"name": "takingAmount", "type": "uint256"},
                {"name": "makerTraits", "type": "uint256"},
            ],
        },
        "domain": {
            "name": "1inch Aggregation Router",
            "version": "6",
            "chainId": 56,
            "verifyingContract": INCH,
        },
        "primaryType": "Order",
        "message": message,
    }


def pcsx(outputs=None, info=None, spender=REACTOR, permitted=10 * E18, deadline=NOW + 120):
    outputs = outputs or [
        {"token": TOKEN, "startAmount": str(43 * 10**15), "endAmount": str(42 * 10**15), "recipient": WALLET}
    ]
    order_info = {
        "reactor": REACTOR,
        "swapper": WALLET,
        "nonce": "7",
        "deadline": str(deadline),
        "additionalValidationContract": "0x" + "0" * 40,
        "additionalValidationData": "0x",
        **(info or {}),
    }
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "PermitWitnessTransferFrom": [
                {"name": "permitted", "type": "TokenPermissions"},
                {"name": "spender", "type": "address"},
                {"name": "nonce", "type": "uint256"},
                {"name": "deadline", "type": "uint256"},
                {"name": "witness", "type": "ExclusiveDutchOrder"},
            ],
            "TokenPermissions": [
                {"name": "token", "type": "address"},
                {"name": "amount", "type": "uint256"},
            ],
            "ExclusiveDutchOrder": [
                {"name": "info", "type": "OrderInfo"},
                {"name": "decayStartTime", "type": "uint256"},
                {"name": "decayEndTime", "type": "uint256"},
                {"name": "exclusiveFiller", "type": "address"},
                {"name": "exclusivityOverrideBps", "type": "uint256"},
                {"name": "inputToken", "type": "address"},
                {"name": "inputStartAmount", "type": "uint256"},
                {"name": "inputEndAmount", "type": "uint256"},
                {"name": "outputs", "type": "DutchOutput[]"},
            ],
            "OrderInfo": [
                {"name": "reactor", "type": "address"},
                {"name": "swapper", "type": "address"},
                {"name": "nonce", "type": "uint256"},
                {"name": "deadline", "type": "uint256"},
                {"name": "additionalValidationContract", "type": "address"},
                {"name": "additionalValidationData", "type": "bytes"},
            ],
            "DutchOutput": [
                {"name": "token", "type": "address"},
                {"name": "startAmount", "type": "uint256"},
                {"name": "endAmount", "type": "uint256"},
                {"name": "recipient", "type": "address"},
            ],
        },
        "domain": {"name": "Permit2", "chainId": 56, "verifyingContract": PERMIT2},
        "primaryType": "PermitWitnessTransferFrom",
        "message": {
            "permitted": {"token": USDT, "amount": str(permitted)},
            "spender": spender,
            "nonce": "7",
            "deadline": str(deadline),
            "witness": {
                "info": order_info,
                "decayStartTime": str(NOW),
                "decayEndTime": str(NOW + 60),
                "exclusiveFiller": OTHER,
                "exclusivityOverrideBps": "0",
                "inputToken": USDT,
                "inputStartAmount": str(10 * E18),
                "inputEndAmount": str(10 * E18),
                "outputs": outputs,
            },
        },
    }


@pytest.mark.parametrize("vendor,typed", [("CowSwap", cow()), ("InchFusion", inch()), ("PcsXRfq", pcsx())])
def test_valid_orders_verify_with_bound_and_hash(vendor, typed):
    order = verify(vendor, typed, EXPECTED, ALLOW)
    assert order.vendor == vendor and order.order_hash.startswith("0x") and len(order.order_hash) == 66
    assert order.min_buy_to_wallet >= EXPECTED.min_buy and order.sell_amount <= EXPECTED.sell_max
    assert order.summary()["verification"] == "SIGNED_ORDER_BOUND"


def test_hash_is_deterministic_and_field_sensitive():
    a = verify("CowSwap", cow(), EXPECTED, ALLOW).order_hash
    assert a == verify("CowSwap", cow(), EXPECTED, ALLOW).order_hash
    assert a != verify("CowSwap", cow(buyAmount=str(43 * 10**15)), EXPECTED, ALLOW).order_hash


@pytest.mark.parametrize(
    "vendor,typed,code",
    [
        ("CowSwap", cow(receiver=OTHER), "RFQ_RECEIVER_NOT_WALLET"),
        ("CowSwap", cow(buyAmount="1"), "RFQ_MIN_OUTPUT_BELOW_PLAN_MINIMUM"),
        ("CowSwap", cow(sellAmount=str(11 * E18)), "RFQ_SELL_ABOVE_PLAN_MAXIMUM"),
        ("CowSwap", cow(feeAmount=str(E18)), "RFQ_SELL_ABOVE_PLAN_MAXIMUM"),
        ("CowSwap", cow(validTo=NOW + 3600), "RFQ_DEADLINE_OUT_OF_RANGE"),
        ("CowSwap", cow(validTo=NOW - 1), "RFQ_DEADLINE_OUT_OF_RANGE"),
        ("CowSwap", cow(partiallyFillable=True), "RFQ_PARTIAL_FILL_REFUSED"),
        ("CowSwap", cow(kind="buy"), "RFQ_COW_BUY_ORDER_REFUSED"),
        ("CowSwap", cow(sellTokenBalance="internal"), "RFQ_COW_BALANCE_MODE_REFUSED"),
        ("CowSwap", cow(buyToken=OTHER), "RFQ_TOKEN_MISMATCH"),
        ("InchFusion", inch(maker=OTHER), "RFQ_MAKER_NOT_WALLET"),
        ("InchFusion", inch(receiver=OTHER), "RFQ_RECEIVER_NOT_WALLET"),
        ("InchFusion", inch(traits=(NOW + 120) << 80), "RFQ_PARTIAL_FILL_REFUSED"),
        ("InchFusion", inch(traits=NO_PARTIAL_FILLS), "RFQ_DEADLINE_OUT_OF_RANGE"),
        ("InchFusion", inch(traits=NO_PARTIAL_FILLS | (1 << 251) | ((NOW + 60) << 80)), "RFQ_INTERACTION_WITHOUT_EXTENSION"),
        ("PcsXRfq", pcsx(spender=OTHER), "RFQ_PERMIT_SPENDER_NOT_REACTOR"),
        ("PcsXRfq", pcsx(info={"swapper": OTHER}), "RFQ_SWAPPER_NOT_WALLET"),
        ("PcsXRfq", pcsx(info={"additionalValidationContract": OTHER}), "RFQ_ADDITIONAL_VALIDATION_REFUSED"),
        ("PcsXRfq", pcsx(permitted=9 * E18), "RFQ_INPUT_EXCEEDS_PERMIT"),
        ("PcsXRfq", pcsx(deadline=NOW + 3600), "RFQ_DEADLINE_OUT_OF_RANGE"),
        (
            "PcsXRfq",
            pcsx(outputs=[
                {"token": TOKEN, "startAmount": str(42 * 10**15), "endAmount": str(42 * 10**15), "recipient": WALLET},
                {"token": TOKEN, "startAmount": str(10**15), "endAmount": str(10**15), "recipient": OTHER},
            ]),
            "RFQ_FEE_OUTPUT_LIMIT",
        ),
        (
            "PcsXRfq",
            pcsx(outputs=[{"token": TOKEN, "startAmount": "1", "endAmount": "1", "recipient": OTHER}]),
            "RFQ_FEE_OUTPUT_LIMIT",
        ),
        (
            "PcsXRfq",
            pcsx(outputs=[{"token": TOKEN, "startAmount": str(43 * 10**15), "endAmount": "1", "recipient": WALLET}]),
            "RFQ_MIN_OUTPUT_BELOW_PLAN_MINIMUM",
        ),
    ],
)
def test_every_rule_fails_closed(vendor, typed, code):
    with pytest.raises(RFQRejected) as caught:
        verify(vendor, typed, EXPECTED, ALLOW)
    assert caught.value.code == code


def test_settlement_must_be_allowlisted_reactor_has_no_default():
    with pytest.raises(RFQRejected) as caught:
        verify("PcsXRfq", pcsx(), EXPECTED, parse_allowlist(""))
    assert caught.value.code == "RFQ_SETTLEMENT_NOT_ALLOWLISTED"
    rogue = cow()
    rogue["domain"]["verifyingContract"] = OTHER
    with pytest.raises(RFQRejected) as caught:
        verify("CowSwap", rogue, EXPECTED, ALLOW)
    assert caught.value.code == "RFQ_SETTLEMENT_NOT_ALLOWLISTED"


@pytest.mark.parametrize("mutate,code", [
    (lambda t: t["domain"].update(chainId=1), "RFQ_WRONG_CHAIN"),
    (lambda t: t.update(primaryType="Order2") or t["types"].update(Order2=t["types"]["Order"]), "RFQ_ORDER_TYPE_UNRECOGNIZED"),
    (lambda t: t["domain"].update(name="Evil"), "RFQ_ORDER_TYPE_UNRECOGNIZED"),
    (lambda t: t["message"].update(extra="1"), "RFQ_TYPED_DATA_INVALID"),
])
def test_wrong_chain_unknown_type_or_extra_fields_rejected(mutate, code):
    typed = copy.deepcopy(cow())
    mutate(typed)
    with pytest.raises(RFQRejected) as caught:
        verify("CowSwap", typed, EXPECTED, ALLOW)
    assert caught.value.code == code


def test_vendor_must_match_order_format():
    with pytest.raises(RFQRejected) as caught:
        verify("PcsXRfq", cow(), EXPECTED, ALLOW)
    assert caught.value.code == "RFQ_ORDER_TYPE_UNRECOGNIZED"


def test_allowlist_parsing_is_strict():
    with pytest.raises(ValueError):
        parse_allowlist("Unknown:0x" + "1" * 40)
    with pytest.raises(ValueError):
        parse_allowlist("CowSwap:not-an-address")
