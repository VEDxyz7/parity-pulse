"""Reviewed canonical schemas, NOT proof of deployed bytecode or Binance compatibility.

Sources and unverified deployment requirements: docs/EXECUTION_REMEDIATION.md.
A configuration allowlist cannot change these chain/domain/type identities.
"""


def fields(*pairs):
    return [{"name": name, "type": kind} for name, kind in pairs]


DOMAIN = fields(
    ("name", "string"),
    ("version", "string"),
    ("chainId", "uint256"),
    ("verifyingContract", "address"),
)
COW_TYPES = {
    "EIP712Domain": DOMAIN,
    "Order": fields(
        ("sellToken", "address"),
        ("buyToken", "address"),
        ("receiver", "address"),
        ("sellAmount", "uint256"),
        ("buyAmount", "uint256"),
        ("validTo", "uint32"),
        ("appData", "bytes32"),
        ("feeAmount", "uint256"),
        ("kind", "string"),
        ("partiallyFillable", "bool"),
        ("sellTokenBalance", "string"),
        ("buyTokenBalance", "string"),
    ),
}
INCH_TYPES = {
    "EIP712Domain": DOMAIN,
    "Order": fields(
        ("salt", "uint256"),
        ("maker", "address"),
        ("receiver", "address"),
        ("makerAsset", "address"),
        ("takerAsset", "address"),
        ("makingAmount", "uint256"),
        ("takingAmount", "uint256"),
        ("makerTraits", "uint256"),
    ),
}
PCS_TYPES = {
    "EIP712Domain": fields(
        ("name", "string"), ("chainId", "uint256"), ("verifyingContract", "address")
    ),
    "PermitWitnessTransferFrom": fields(
        ("permitted", "TokenPermissions"),
        ("spender", "address"),
        ("nonce", "uint256"),
        ("deadline", "uint256"),
        ("witness", "ExclusiveDutchOrder"),
    ),
    "TokenPermissions": fields(("token", "address"), ("amount", "uint256")),
    "ExclusiveDutchOrder": fields(
        ("info", "OrderInfo"),
        ("decayStartTime", "uint256"),
        ("decayEndTime", "uint256"),
        ("exclusiveFiller", "address"),
        ("exclusivityOverrideBps", "uint256"),
        ("inputToken", "address"),
        ("inputStartAmount", "uint256"),
        ("inputEndAmount", "uint256"),
        ("outputs", "DutchOutput[]"),
    ),
    "OrderInfo": fields(
        ("reactor", "address"),
        ("swapper", "address"),
        ("nonce", "uint256"),
        ("deadline", "uint256"),
        ("additionalValidationContract", "address"),
        ("additionalValidationData", "bytes"),
    ),
    "DutchOutput": fields(
        ("token", "address"),
        ("startAmount", "uint256"),
        ("endAmount", "uint256"),
        ("recipient", "address"),
    ),
}
PCS_PERMIT2 = "0x31c2f6fcff4f8759b3bd5bf0e1084a055615c768"
PCS_REACTOR = "0xdb9d365b50e62fce747a90515d2bd1254a16ebb9"
DOMAINS = {
    "CowSwap": ("Gnosis Protocol", "v2", "Order", COW_TYPES),
    "InchFusion": ("1inch Aggregation Router", "6", "Order", INCH_TYPES),
    "PcsXRfq": ("Permit2", None, "PermitWitnessTransferFrom", PCS_TYPES),
}
CONTRACTS = {
    "CowSwap": "0x9008d19f58aabd9ed0d60971565aa8510560ab41",
    "InchFusion": "0x111111125421ca6dc452d289314280a0f8842a65",
    "PcsXRfq": PCS_REACTOR,
}
