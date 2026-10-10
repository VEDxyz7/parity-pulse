"""Synthetic RFQ orders built from vendor public specifications (no live payload captured)."""

from app.services.rfq_orders import (
    NO_PARTIAL_FILLS,
    PERMIT2,
    Expected,
    parse_allowlist,
)

NOW = 1_791_640_000
WALLET = "0x" + "a" * 40
OTHER = "0x" + "e" * 40
USDT = "0x55d398326f99059ff775485246999027b3197955"
TOKEN = "0xa9ee28c80f960b889dfbd1902055218cba016f75"
REACTOR = "0xdb9d365b50e62fce747a90515d2bd1254a16ebb9"
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
        "domain": {
            "name": "Gnosis Protocol",
            "version": "v2",
            "chainId": 56,
            "verifyingContract": COW,
        },
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
        {
            "token": TOKEN,
            "startAmount": str(43 * 10**15),
            "endAmount": str(42 * 10**15),
            "recipient": WALLET,
        }
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
