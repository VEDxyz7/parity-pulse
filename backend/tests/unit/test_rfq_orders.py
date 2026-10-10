"""Synthetic canonical vectors; these are NOT deployed protocol compatibility evidence."""

import copy

import pytest
from eth_abi import encode
from eth_utils import keccak

from app.services.protocol_definitions import CONTRACTS, PCS_PERMIT2
from app.services.rfq_orders import (
    HAS_EXTENSION,
    NO_PARTIAL_FILLS,
    Expected,
    RFQRejected,
    parse_allowlist,
    verify,
)
from backend.tests.fixtures.rfq_orders import (
    ALLOW,
    EXPECTED,
    NOW,
    OTHER,
    WALLET,
    cow,
    inch,
    pcsx,
)


@pytest.mark.parametrize(
    "vendor,factory", [("CowSwap", cow), ("InchFusion", inch), ("PcsXRfq", pcsx)]
)
def test_canonical_order_bound_hash(vendor, factory):
    order = verify(vendor, factory(), EXPECTED, ALLOW)
    assert order.wallet == WALLET and order.sell_amount <= EXPECTED.sell_max
    assert order.min_buy_to_wallet >= EXPECTED.min_buy
    assert len(order.order_hash) == 66 and len(order.payload_digest) == 64
    assert order.summary()["verification"] == "SIGNED_ORDER_BOUND"
    assert verify(vendor, factory(), EXPECTED, ALLOW) == order


@pytest.mark.parametrize(
    "vendor,factory", [("CowSwap", cow), ("InchFusion", inch), ("PcsXRfq", pcsx)]
)
@pytest.mark.parametrize("change", ["chain", "contract", "name", "version", "type", "extra_type"])
def test_noncanonical_protocol_rejected(vendor, factory, change):
    typed = factory()
    if change == "chain":
        typed["domain"]["chainId"] = 1
    elif change == "contract":
        typed["domain"]["verifyingContract"] = OTHER
    elif change in {"name", "version"}:
        typed["domain"][change] = "UNREVIEWED"
    elif change == "type":
        typed["types"][typed["primaryType"]][0]["type"] = "uint128"
    else:
        typed["types"]["Extra"] = [{"name": "x", "type": "uint256"}]
    with pytest.raises(RFQRejected):
        verify(vendor, typed, EXPECTED, ALLOW)


@pytest.mark.parametrize(
    "factory,vendor,field,value",
    [
        (cow, "CowSwap", "receiver", OTHER),
        (cow, "CowSwap", "buyAmount", "1"),
        (cow, "CowSwap", "sellAmount", str(EXPECTED.sell_max + 1)),
        (cow, "CowSwap", "feeAmount", str(EXPECTED.sell_max)),
        (cow, "CowSwap", "validTo", NOW - 1),
        (cow, "CowSwap", "partiallyFillable", True),
        (cow, "CowSwap", "kind", "buy"),
        (cow, "CowSwap", "sellTokenBalance", "internal"),
        (inch, "InchFusion", "maker", OTHER),
        (inch, "InchFusion", "receiver", OTHER),
        (inch, "InchFusion", "takingAmount", "1"),
        (inch, "InchFusion", "makingAmount", str(EXPECTED.sell_max + 1)),
        (inch, "InchFusion", "makerTraits", "0"),
    ],
)
def test_order_bounds_fail_closed(factory, vendor, field, value):
    typed = factory()
    typed["message"][field] = value
    with pytest.raises(RFQRejected):
        verify(vendor, typed, EXPECTED, ALLOW)


def extension_order(raw):
    return inch(
        traits=NO_PARTIAL_FILLS | HAS_EXTENSION | ((NOW + 120) << 80),
        salt=str(int.from_bytes(keccak(raw), "big") & (2**160 - 1)),
    )


def test_supported_empty_extension_exact_hash_bound():
    raw = bytes(32)
    typed = extension_order(raw)
    order = verify("InchFusion", typed, EXPECTED, ALLOW, extension="0x" + raw.hex())
    assert order.extension_hash == "0x" + keccak(raw).hex()
    assert order.min_buy_to_wallet == EXPECTED.min_buy
    with pytest.raises(RFQRejected, match="HASH_MISMATCH"):
        verify("InchFusion", typed, EXPECTED, ALLOW, extension="0x" + (bytes(31) + b"1").hex())


@pytest.mark.parametrize(
    "raw,reason",
    [
        (b"", "MISSING_OR_MALFORMED"),
        (b"\x01", "MISSING_OR_MALFORMED"),
        (
            sum(1 << (32 * i) for i in range(3, 8)).to_bytes(32, "big") + b"x",
            "GETTERS_OR_INTERACTIONS_UNVERIFIED",
        ),
        ((2**96).to_bytes(32, "big"), "MALFORMED"),
        (bytes(32) + b"x", "GETTERS_OR_INTERACTIONS_UNVERIFIED"),
    ],
)
def test_extensions_with_amount_getters_or_unverified_custom_data_rejected(raw, reason):
    with pytest.raises(RFQRejected, match=reason):
        verify("InchFusion", extension_order(raw), EXPECTED, ALLOW, extension="0x" + raw.hex())


def test_extension_missing_and_interaction_flags_rejected():
    with pytest.raises(RFQRejected, match="EXTENSION_MISSING"):
        verify("InchFusion", extension_order(bytes(32)), EXPECTED, ALLOW)
    with pytest.raises(RFQRejected, match="UNSUPPORTED_MAKER_TRAITS"):
        verify(
            "InchFusion",
            inch(traits=NO_PARTIAL_FILLS | (1 << 251) | ((NOW + 120) << 80)),
            EXPECTED,
            ALLOW,
        )


@pytest.mark.parametrize("field", ["nonce", "deadline"])
def test_outer_permit_must_equal_witness(field):
    typed = pcsx()
    typed["message"]["witness"]["info"][field] = str(int(typed["message"][field]) + 1)
    with pytest.raises(RFQRejected, match="NONCE_DEADLINE_MISMATCH"):
        verify("PcsXRfq", typed, EXPECTED, ALLOW)


def test_pcs_deployment_and_permit_maximum_are_not_guessed():
    assert PCS_PERMIT2 != "0x000000000022d473030f116ddee9f6b43ac78ba3"
    with pytest.raises(RFQRejected):
        verify("PcsXRfq", pcsx(), EXPECTED, parse_allowlist(""))
    with pytest.raises(RFQRejected, match="INPUT_EXCEEDS_PERMIT"):
        verify("PcsXRfq", pcsx(permitted=EXPECTED.sell_max + 1), EXPECTED, ALLOW)
    with pytest.raises(ValueError, match="Unreviewed"):
        parse_allowlist("PcsXRfq:" + OTHER)


def test_contract_algorithm_matches_cow_digest_and_uid():
    # Independent ABI implementation of GPv2Order + EIP712 domain, not encode_typed_data.
    typed = cow()
    m = typed["message"]
    signature = (
        "Order(" + ",".join(f"{f['type']} {f['name']}" for f in typed["types"]["Order"]) + ")"
    )
    types, values = ["bytes32"], [keccak(text=signature)]
    for f in typed["types"]["Order"]:
        kind, value = f["type"], m[f["name"]]
        if kind == "string":
            kind, value = "bytes32", keccak(text=value)
        elif kind == "bytes32":
            value = bytes.fromhex(value[2:])
        elif kind.startswith("uint"):
            value = int(value)
        types.append(kind)
        values.append(value)
    struct_hash = keccak(encode(types, values))
    domain_hash = keccak(
        encode(
            ["bytes32", "bytes32", "bytes32", "uint256", "address"],
            [
                keccak(
                    text=(
                        "EIP712Domain(string name,string version,"
                        "uint256 chainId,address verifyingContract)"
                    )
                ),
                keccak(text="Gnosis Protocol"),
                keccak(text="v2"),
                56,
                CONTRACTS["CowSwap"],
            ],
        )
    )
    expected = "0x" + keccak(b"\x19\x01" + domain_hash + struct_hash).hex()
    order = verify("CowSwap", typed, EXPECTED, ALLOW, expected_hash=expected)
    assert order.uid == expected + WALLET[2:] + format(m["validTo"], "08x")
    with pytest.raises(RFQRejected, match="ORDER_HASH_MISMATCH"):
        verify("CowSwap", typed, EXPECTED, ALLOW, expected_hash="0x" + "0" * 64)


@pytest.mark.parametrize("raw", [None, [], {}, {"types": []}])
def test_malformed_payload_is_typed_rejection(raw):
    with pytest.raises(RFQRejected):
        verify("CowSwap", raw, EXPECTED, ALLOW)


def test_input_objects_are_not_mutated_and_wrong_tokens_rejected():
    typed = cow()
    original = copy.deepcopy(typed)
    verify("CowSwap", typed, EXPECTED, ALLOW)
    assert typed == original
    wrong = Expected(WALLET, OTHER, EXPECTED.sell_max, EXPECTED.buy_token, EXPECTED.min_buy, NOW)
    with pytest.raises(RFQRejected, match="TOKEN_MISMATCH"):
        verify("CowSwap", typed, wrong, ALLOW)
