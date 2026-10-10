"""Teammate RFQ regressions ported to audited canonical deployment/type fixtures."""

import copy

import pytest

from app.services.rfq_orders import NO_PARTIAL_FILLS, RFQRejected, parse_allowlist, verify
from backend.tests.fixtures.rfq_orders import (
    ALLOW,
    E18,
    EXPECTED,
    NOW,
    OTHER,
    TOKEN,
    WALLET,
    cow,
    inch,
    pcsx,
)


@pytest.mark.parametrize(
    "vendor,typed", [("CowSwap", cow()), ("InchFusion", inch()), ("PcsXRfq", pcsx())]
)
def test_valid_orders_verify_with_bound_and_hash(vendor, typed):
    order = verify(vendor, typed, EXPECTED, ALLOW)
    assert (
        order.vendor == vendor and order.order_hash.startswith("0x") and len(order.order_hash) == 66
    )
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
        (
            "InchFusion",
            inch(traits=NO_PARTIAL_FILLS | (1 << 251) | ((NOW + 60) << 80)),
            "RFQ_UNSUPPORTED_MAKER_TRAITS",
        ),
        ("PcsXRfq", pcsx(spender=OTHER), "RFQ_PERMIT_SPENDER_NOT_REACTOR"),
        ("PcsXRfq", pcsx(info={"swapper": OTHER}), "RFQ_SWAPPER_NOT_WALLET"),
        (
            "PcsXRfq",
            pcsx(info={"additionalValidationContract": OTHER}),
            "RFQ_ADDITIONAL_VALIDATION_REFUSED",
        ),
        ("PcsXRfq", pcsx(permitted=9 * E18), "RFQ_INPUT_EXCEEDS_PERMIT"),
        ("PcsXRfq", pcsx(deadline=NOW + 3600), "RFQ_DEADLINE_OUT_OF_RANGE"),
        (
            "PcsXRfq",
            pcsx(
                outputs=[
                    {
                        "token": TOKEN,
                        "startAmount": str(42 * 10**15),
                        "endAmount": str(42 * 10**15),
                        "recipient": WALLET,
                    },
                    {
                        "token": TOKEN,
                        "startAmount": str(10**15),
                        "endAmount": str(10**15),
                        "recipient": OTHER,
                    },
                ]
            ),
            "RFQ_FEE_OUTPUT_LIMIT",
        ),
        (
            "PcsXRfq",
            pcsx(
                outputs=[{"token": TOKEN, "startAmount": "1", "endAmount": "1", "recipient": OTHER}]
            ),
            "RFQ_FEE_OUTPUT_LIMIT",
        ),
        (
            "PcsXRfq",
            pcsx(
                outputs=[
                    {
                        "token": TOKEN,
                        "startAmount": str(43 * 10**15),
                        "endAmount": "1",
                        "recipient": WALLET,
                    }
                ]
            ),
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
    assert caught.value.code == "RFQ_PROTOCOL_DEPLOYMENT_MISMATCH"


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda t: t["domain"].update(chainId=1), "RFQ_WRONG_CHAIN"),
        (
            lambda t: (
                t.update(primaryType="Order2") or t["types"].update(Order2=t["types"]["Order"])
            ),
            "RFQ_NONCANONICAL_DOMAIN_OR_TYPES",
        ),
        (lambda t: t["domain"].update(name="Evil"), "RFQ_NONCANONICAL_DOMAIN_OR_TYPES"),
        (lambda t: t["message"].update(extra="1"), "RFQ_TYPED_DATA_INVALID"),
    ],
)
def test_wrong_chain_unknown_type_or_extra_fields_rejected(mutate, code):
    typed = copy.deepcopy(cow())
    mutate(typed)
    with pytest.raises(RFQRejected) as caught:
        verify("CowSwap", typed, EXPECTED, ALLOW)
    assert caught.value.code == code


def test_vendor_must_match_order_format():
    with pytest.raises(RFQRejected) as caught:
        verify("PcsXRfq", cow(), EXPECTED, ALLOW)
    assert caught.value.code == "RFQ_NONCANONICAL_DOMAIN_OR_TYPES"


def test_allowlist_parsing_is_strict():
    with pytest.raises(ValueError):
        parse_allowlist("Unknown:0x" + "1" * 40)
    with pytest.raises(ValueError):
        parse_allowlist("CowSwap:not-an-address")
