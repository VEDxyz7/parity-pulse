"""RFQ signed-order verification: bound the outcome before any signature is produced.

RFQ settlement is asynchronous. These local definitions validate a constrained signed-order
bound; they do not prove deployed compatibility or settlement simulation equivalence. Unknown
features fail closed. Real unsigned provider payloads and deployment/hash evidence are still
required; no mocked test unlocks a live capability gate.

Vendor formats implemented from their public specifications (no live payload captured yet):
- CowSwap: GPv2 `Order`, domain "Gnosis Protocol", verifying contract = GPv2Settlement.
- InchFusion: 1inch Limit Order Protocol v4 `Order`, domain "1inch Aggregation Router".
- PcsXRfq: PancakeSwap X, Permit2 `PermitWitnessTransferFrom` with a reactor order witness.
"""

import re
from dataclasses import dataclass, field

from eth_account.messages import encode_typed_data
from eth_utils import keccak

from app.services.eip712_validation import validate_typed_data
from app.services.protocol_definitions import CONTRACTS, DOMAINS, PCS_PERMIT2

ZERO = "0x" + "0" * 40
PERMIT2 = PCS_PERMIT2
MAX_DEADLINE_SECONDS = 600
MAX_FEE_FRACTION_BPS = 100  # outputs to third parties may not exceed 1% of our output

# Reviewed protocol identities retained from the audit. They are NOT proof of current
# deployed bytecode/contract-computed hash or Binance payload compatibility. Pcs is opt-in.
DEFAULT_SETTLEMENTS = {
    "CowSwap": {"0x9008d19f58aabd9ed0d60971565aa8510560ab41"},
    "InchFusion": {"0x111111125421ca6dc452d289314280a0f8842a65"},
    "PcsXRfq": set(),
}
DEFAULT_SPENDERS = {
    "CowSwap": "0xc92e8bdf79f0507f65a392b0ab4667716bfe0110",  # GPv2VaultRelayer
    "InchFusion": "0x111111125421ca6dc452d289314280a0f8842a65",  # router itself
    "PcsXRfq": PERMIT2,
}

# 1inch LOP v4 MakerTraits bits.
NO_PARTIAL_FILLS = 1 << 255
ALLOW_MULTIPLE_FILLS = 1 << 254
PRE_INTERACTION = 1 << 252
POST_INTERACTION = 1 << 251
HAS_EXTENSION = 1 << 249


class RFQRejected(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Expected:
    """What the plan authorises for this leg (base units)."""

    wallet: str
    sell_token: str
    sell_max: int
    buy_token: str
    min_buy: int
    now: int  # unix seconds

    def __post_init__(self):
        if any(_addr(value) == ZERO for value in (self.wallet, self.sell_token, self.buy_token)):
            raise RFQRejected("RFQ_ZERO_EXPECTED_ADDRESS")
        if self.sell_token.lower() == self.buy_token.lower():
            raise RFQRejected("RFQ_IDENTICAL_TOKENS")
        if any(type(v) is not int or not 0 < v < 2**256 for v in (self.sell_max, self.min_buy)):
            raise RFQRejected("RFQ_INVALID_EXPECTED_BOUND")
        if type(self.now) is not int or self.now < 0:
            raise RFQRejected("RFQ_INVALID_EXPECTED_TIME")


@dataclass(frozen=True)
class VerifiedOrder:
    vendor: str
    order_hash: str
    settlement: str
    spender: str
    sell_token: str
    sell_amount: int
    buy_token: str
    min_buy_to_wallet: int
    deadline: int
    wallet: str = ""
    uid: str | None = None
    witness_hash: str | None = None
    nonce: int | None = None
    extension_hash: str | None = None
    payload_digest: str = ""
    fees: int = 0
    warnings: list = field(default_factory=list)

    def summary(self):
        return {
            "vendor": self.vendor,
            "order_hash": self.order_hash,
            "settlement": self.settlement,
            "spender": self.spender,
            "sell_token": self.sell_token,
            "sell_amount": str(self.sell_amount),
            "buy_token": self.buy_token,
            "min_buy_to_wallet": str(self.min_buy_to_wallet),
            "deadline": self.deadline,
            "fees": str(self.fees),
            "wallet": self.wallet,
            "uid": self.uid,
            "witness_hash": self.witness_hash,
            "nonce": self.nonce,
            "extension_hash": self.extension_hash,
            "payload_digest": self.payload_digest,
            "warnings": list(self.warnings),
            "verification": "SIGNED_ORDER_BOUND",
        }


def parse_allowlist(text):
    """`vendor:address,vendor:address` -> {vendor: {address}} merged over defaults."""
    allow = {k: set(v) for k, v in DEFAULT_SETTLEMENTS.items()}
    for item in filter(None, (p.strip() for p in (text or "").split(","))):
        vendor, _, address = item.partition(":")
        if vendor not in allow or not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
            raise ValueError("RFQ_SETTLEMENT_ALLOWLIST entries must be vendor:0xaddress")
        if address.lower() != CONTRACTS[vendor]:
            raise ValueError("Unreviewed protocol deployment")
        allow[vendor].add(address.lower())
    return allow


def _addr(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        raise RFQRejected("RFQ_INVALID_ADDRESS")
    return value.lower()


def _int(value):
    if isinstance(value, bool):
        raise RFQRejected("RFQ_INVALID_INTEGER")
    if isinstance(value, int):
        if not 0 <= value < 2**256:
            raise RFQRejected("RFQ_INVALID_INTEGER")
        return value
    if isinstance(value, str) and re.fullmatch(r"(0|[1-9][0-9]{0,77})", value):
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]{1,64}", value):
        return int(value, 16)
    raise RFQRejected("RFQ_INVALID_INTEGER")


def _normalize(types, kind, value):
    """Numbers as ints for hashing; structure was already validated."""
    array = re.fullmatch(r"(.+)\[[0-9]*\]", kind)
    if array:
        return [_normalize(types, array[1], v) for v in value]
    if kind in types:
        return {f["name"]: _normalize(types, f["type"], value[f["name"]]) for f in types[kind]}
    if re.fullmatch(r"u?int[0-9]*", kind):
        return _int(value)
    return value


def order_hash(typed):
    types = typed["types"]
    message = _normalize(types, typed["primaryType"], typed["message"])
    domain = dict(typed["domain"])
    if "chainId" in domain:
        domain["chainId"] = _int(domain["chainId"])
    full = {**typed, "message": message, "domain": domain}
    signable = encode_typed_data(full_message=full)
    digest = keccak(b"\x19" + signable.version + signable.header + signable.body)
    return "0x" + digest.hex(), full


def _deadline(value, now):
    deadline = _int(value)
    if not now < deadline <= now + MAX_DEADLINE_SECONDS:
        raise RFQRejected("RFQ_DEADLINE_OUT_OF_RANGE")
    return deadline


def verify(vendor, typed, expected, allowlist, *, extension="0x", expected_hash=None):
    if not isinstance(typed, dict) or set(typed) != {"types", "domain", "primaryType", "message"}:
        raise RFQRejected("RFQ_TYPED_DATA_SHAPE")
    if (
        not isinstance(typed["types"], dict)
        or not isinstance(typed["domain"], dict)
        or not isinstance(typed["message"], dict)
        or not isinstance(typed["primaryType"], str)
    ):
        raise RFQRejected("RFQ_TYPED_DATA_SHAPE")
    try:
        validate_typed_data(typed)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise RFQRejected("RFQ_TYPED_DATA_INVALID") from None
    domain = typed["domain"]
    if _int(domain.get("chainId", 0)) != 56:
        raise RFQRejected("RFQ_WRONG_CHAIN")
    from dataclasses import replace

    from app.models.execution import fingerprint

    spec = DOMAINS.get(vendor)
    if spec is None:
        raise RFQRejected("RFQ_ORDER_TYPE_UNRECOGNIZED")
    name, version, primary, types = spec
    required_domain = {"name", "chainId", "verifyingContract"} | (
        {"version"} if version is not None else set()
    )
    if (
        typed["types"] != types
        or typed["primaryType"] != primary
        or set(domain) != required_domain
        or domain.get("name") != name
        or domain.get("version") != version
    ):
        raise RFQRejected("RFQ_NONCANONICAL_DOMAIN_OR_TYPES")
    verifying = PERMIT2 if vendor == "PcsXRfq" else CONTRACTS[vendor]
    if _addr(domain["verifyingContract"]) != verifying:
        raise RFQRejected("RFQ_PROTOCOL_DEPLOYMENT_MISMATCH")
    if expected.sell_max <= 0 or expected.min_buy <= 0:
        raise RFQRejected("RFQ_INVALID_EXPECTED_BOUNDS")
    key = (domain.get("name"), typed["primaryType"])
    handlers = {
        ("CowSwap", ("Gnosis Protocol", "Order")): _cowswap,
        ("InchFusion", ("1inch Aggregation Router", "Order")): _inch,
        ("PcsXRfq", ("Permit2", "PermitWitnessTransferFrom")): _pcsx,
    }
    handler = handlers.get((vendor, key))
    if handler is None:
        raise RFQRejected("RFQ_ORDER_TYPE_UNRECOGNIZED")
    try:
        digest, full = order_hash(typed)
    except (ValueError, TypeError, KeyError):
        raise RFQRejected("RFQ_TYPED_DATA_INVALID") from None
    order = handler(full, expected, allowlist.get(vendor, set()))
    if expected_hash is not None and digest != expected_hash.lower():
        raise RFQRejected("RFQ_ORDER_HASH_MISMATCH")
    extension_hash = _extension(full, extension) if vendor == "InchFusion" else None
    if vendor != "InchFusion" and extension != "0x":
        raise RFQRejected("RFQ_UNEXPECTED_EXTENSION")
    uid = None
    witness_hash = None
    nonce = None
    if vendor == "CowSwap":
        uid = digest + expected.wallet[2:].lower() + format(full["message"]["validTo"], "08x")
    if vendor == "PcsXRfq":
        from eth_account._utils.encode_typed_data.encoding_and_hashing import hash_struct

        witness_hash = (
            "0x"
            + hash_struct("ExclusiveDutchOrder", full["types"], full["message"]["witness"]).hex()
        )
        nonce = full["message"]["nonce"]
    order = replace(
        order,
        order_hash=digest,
        wallet=expected.wallet.lower(),
        uid=uid,
        witness_hash=witness_hash,
        nonce=nonce,
        extension_hash=extension_hash,
        payload_digest=fingerprint({"typed": full, "extension": extension}),
    )
    if order.sell_token != expected.sell_token.lower() or order.buy_token != (
        expected.buy_token.lower()
    ):
        raise RFQRejected("RFQ_TOKEN_MISMATCH")
    if not 0 < order.sell_amount <= expected.sell_max:
        raise RFQRejected("RFQ_SELL_ABOVE_PLAN_MAXIMUM")
    if order.min_buy_to_wallet < expected.min_buy:
        raise RFQRejected("RFQ_MIN_OUTPUT_BELOW_PLAN_MINIMUM")
    return order


def _cowswap(typed, e, allowed):
    m = typed["message"]
    settlement = _addr(typed["domain"].get("verifyingContract"))
    if settlement not in allowed:
        raise RFQRejected("RFQ_SETTLEMENT_NOT_ALLOWLISTED")
    receiver = _addr(m["receiver"])
    if receiver not in {ZERO, e.wallet.lower()}:
        raise RFQRejected("RFQ_RECEIVER_NOT_WALLET")
    if m["kind"] != "sell":
        raise RFQRejected("RFQ_COW_BUY_ORDER_REFUSED")
    if m["partiallyFillable"] is not False:
        raise RFQRejected("RFQ_PARTIAL_FILL_REFUSED")
    if m["sellTokenBalance"] != "erc20" or m["buyTokenBalance"] != "erc20":
        raise RFQRejected("RFQ_COW_BALANCE_MODE_REFUSED")
    fee = _int(m["feeAmount"])
    return VerifiedOrder(
        vendor="CowSwap",
        order_hash="",
        settlement=settlement,
        spender=DEFAULT_SPENDERS["CowSwap"],
        sell_token=_addr(m["sellToken"]),
        sell_amount=_int(m["sellAmount"]) + fee,
        buy_token=_addr(m["buyToken"]),
        min_buy_to_wallet=_int(m["buyAmount"]),
        deadline=_deadline(m["validTo"], e.now),
        fees=fee,
        # Hooks in appData execute from the HooksTrampoline, never with the owner's allowance.
        warnings=["COW_APPDATA_" + str(m["appData"])],
    )


def _inch(typed, e, allowed):
    m = typed["message"]
    settlement = _addr(typed["domain"].get("verifyingContract"))
    if settlement not in allowed:
        raise RFQRejected("RFQ_SETTLEMENT_NOT_ALLOWLISTED")
    if _addr(m["maker"]) != e.wallet.lower():
        raise RFQRejected("RFQ_MAKER_NOT_WALLET")
    if _addr(m["receiver"]) not in {ZERO, e.wallet.lower()}:
        raise RFQRejected("RFQ_RECEIVER_NOT_WALLET")
    traits = _int(m["makerTraits"])
    if not traits & NO_PARTIAL_FILLS or traits & ALLOW_MULTIPLE_FILLS:
        raise RFQRejected("RFQ_PARTIAL_FILL_REFUSED")
    expiration = (traits >> 80) & ((1 << 40) - 1)
    warnings = []
    # Only reviewed ERC20/static-price semantics. Epoch/permit2/unwrap/unknown flags
    # need separate verification; low80 private-taker bits must also be empty.
    supported = (
        NO_PARTIAL_FILLS | HAS_EXTENSION | (((1 << 40) - 1) << 80) | (((1 << 80) - 1) << 120)
    )
    if traits & ~supported:
        raise RFQRejected("RFQ_UNSUPPORTED_MAKER_TRAITS")
    return VerifiedOrder(
        vendor="InchFusion",
        order_hash="",
        settlement=settlement,
        spender=DEFAULT_SPENDERS["InchFusion"],
        sell_token=_addr(m["makerAsset"]),
        sell_amount=_int(m["makingAmount"]),
        buy_token=_addr(m["takerAsset"]),
        min_buy_to_wallet=_int(m["takingAmount"]),
        deadline=_deadline(expiration, e.now),
        warnings=warnings,
    )


def _amounts(item, start="startAmount", end="endAmount", single="amount"):
    if single in item:
        value = _int(item[single])
        return value, value
    return _int(item[start]), _int(item[end])


def _pcsx(typed, e, allowed):
    m = typed["message"]
    if _addr(typed["domain"].get("verifyingContract")) != PERMIT2:
        raise RFQRejected("RFQ_PERMIT2_DOMAIN_MISMATCH")
    witness = m.get("witness")
    info = witness.get("info") if isinstance(witness, dict) else None
    if not isinstance(info, dict):
        raise RFQRejected("RFQ_ORDER_TYPE_UNRECOGNIZED")
    reactor = _addr(info["reactor"])
    if _addr(m["spender"]) != reactor:
        raise RFQRejected("RFQ_PERMIT_SPENDER_NOT_REACTOR")
    if reactor not in allowed:
        raise RFQRejected("RFQ_SETTLEMENT_NOT_ALLOWLISTED")
    if _addr(info["swapper"]) != e.wallet.lower():
        raise RFQRejected("RFQ_SWAPPER_NOT_WALLET")
    if _addr(info.get("additionalValidationContract", ZERO)) != ZERO:
        raise RFQRejected("RFQ_ADDITIONAL_VALIDATION_REFUSED")
    permitted = m["permitted"]
    sell_token, sell_amount = _addr(permitted["token"]), _int(permitted["amount"])
    if "input" in witness:
        i = witness["input"]
        input_token, input_max = _addr(i["token"]), max(_amounts(i))
    else:
        input_token = _addr(witness["inputToken"])
        input_max = max(_int(witness["inputStartAmount"]), _int(witness["inputEndAmount"]))
    if input_token != sell_token or input_max != sell_amount:
        raise RFQRejected("RFQ_INPUT_EXCEEDS_PERMIT")
    deadline = _deadline(m["deadline"], e.now)
    if _int(info["deadline"]) != deadline or _int(m["nonce"]) != _int(info["nonce"]):
        raise RFQRejected("RFQ_PERMIT_WITNESS_NONCE_DEADLINE_MISMATCH")
    if info["additionalValidationData"] != "0x":
        raise RFQRejected("RFQ_ADDITIONAL_VALIDATION_REFUSED")
    start, end = _int(witness["decayStartTime"]), _int(witness["decayEndTime"])
    if not start <= end <= deadline or _int(witness["exclusivityOverrideBps"]) > 10000:
        raise RFQRejected("RFQ_DECAY_OR_EXCLUSIVITY_INVALID")
    if _int(witness["inputStartAmount"]) != _int(witness["inputEndAmount"]):
        raise RFQRejected("RFQ_VARIABLE_INPUT_UNVERIFIED")
    outputs = witness.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise RFQRejected("RFQ_ORDER_TYPE_UNRECOGNIZED")
    ours, fees, buy_token = 0, 0, None
    for out in outputs:
        token, recipient = _addr(out["token"]), _addr(out["recipient"])
        if buy_token is None:
            buy_token = token
        if token != buy_token:
            raise RFQRejected("RFQ_MIXED_OUTPUT_TOKENS")
        floor = min(_amounts(out))
        if recipient == e.wallet.lower():
            ours += floor
        else:
            fees += max(_amounts(out))
    if ours == 0 or fees * 10000 > ours * MAX_FEE_FRACTION_BPS:
        raise RFQRejected("RFQ_FEE_OUTPUT_LIMIT")
    return VerifiedOrder(
        vendor="PcsXRfq",
        order_hash="",
        settlement=reactor,
        spender=PERMIT2,
        sell_token=sell_token,
        sell_amount=sell_amount,
        buy_token=buy_token,
        min_buy_to_wallet=ours,
        deadline=deadline,
        fees=fees,
    )


def _extension(typed, value):
    """Accept only a hash-bound extension with all dynamic fields/custom data empty.

    Amount getters, asset suffixes, predicates, permits and interactions are not
    approximated. A genuine Fusion auction extension requires its own proved adapter.
    """
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", value):
        raise RFQRejected("RFQ_EXTENSION_MALFORMED")
    raw = bytes.fromhex(value[2:])
    traits, salt = typed["message"]["makerTraits"], typed["message"]["salt"]
    if not traits & HAS_EXTENSION:
        if raw:
            raise RFQRejected("RFQ_UNEXPECTED_EXTENSION")
        return None
    if len(raw) < 32:
        raise RFQRejected("RFQ_EXTENSION_MISSING_OR_MALFORMED")
    digest = keccak(raw)
    if int.from_bytes(digest, "big") & (2**160 - 1) != salt & (2**160 - 1):
        raise RFQRejected("RFQ_EXTENSION_HASH_MISMATCH")
    offsets = int.from_bytes(raw[:32], "big")
    ends = [(offsets >> (32 * i)) & (2**32 - 1) for i in range(8)]
    if ends != sorted(ends) or ends[-1] > len(raw) - 32:
        raise RFQRejected("RFQ_EXTENSION_MALFORMED")
    if any(ends) or len(raw) != 32:
        raise RFQRejected("RFQ_EXTENSION_GETTERS_OR_INTERACTIONS_UNVERIFIED")
    return "0x" + digest.hex()
