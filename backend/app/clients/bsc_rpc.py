"""Minimal BSC JSON-RPC client: on-chain balances, allowances, nonce, receipts.

Reads use a closed method list. `send_raw_transaction` is the only write and is refused
unless the client was constructed with `allow_send=True` by the live execution wiring.
Responses and URLs are never logged (public RPC URLs can carry provider keys).
"""

import itertools
import re

import httpx

from app.clients.common import ProviderError
from app.services.execution_gates import LIVE_GATES

DEFAULT_RPC = "https://bsc-dataseed.bnbchain.org"
READ_METHODS = {
    "eth_chainId",
    "eth_call",
    "eth_getBalance",
    "eth_getTransactionCount",
    "eth_gasPrice",
    "eth_getTransactionReceipt",
    "eth_blockNumber",
    "eth_getCode",
    "eth_getTransactionByHash",
    "eth_getBlockByNumber",
}
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
BALANCE_OF = "0x70a08231"
ALLOWANCE = "0xdd62ed3e"
APPROVE = "0x095ea7b3"


def word(address):
    if not ADDRESS.match(address):
        raise ValueError("Invalid address")
    return address[2:].lower().rjust(64, "0")


def approve_calldata(spender, amount):
    if not 0 <= int(amount) < 2**256:
        raise ValueError("Invalid approval amount")
    return APPROVE + word(spender) + format(int(amount), "064x")


class BscRpcClient:
    provider = "BSC_RPC"

    def __init__(
        self, url=DEFAULT_RPC, *, allow_send=False, http=None, timeout=10, gates=LIVE_GATES
    ):
        if not url.startswith("https://"):
            raise ValueError("HTTPS RPC endpoint required")
        self.url, self.allow_send, self.gates = url, allow_send, gates
        self.http = http or httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False)
        self.ids = itertools.count(1)

    def close(self):
        self.http.close()

    def _rpc(self, method, params):
        if method == "eth_sendRawTransaction":
            self.gates.require("SWAP")
            if not self.allow_send:
                raise ProviderError(self.provider, "LIVE_SEND_DISABLED")
        elif method not in READ_METHODS:
            raise ProviderError(self.provider, "READ_ONLY_OPERATION_REQUIRED")
        request_id = next(self.ids)
        try:
            response = self.http.post(
                self.url,
                json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            )
        except httpx.RequestError:
            raise ProviderError(self.provider, "TRANSPORT_UNAVAILABLE") from None
        if response.status_code != 200:
            raise ProviderError(self.provider, "HTTP_FAILURE", response.status_code)
        try:
            body = response.json()
        except ValueError:
            raise ProviderError(self.provider, "SCHEMA_INVALID") from None
        if (
            not isinstance(body, dict)
            or body.get("id") != request_id
            or body.get("jsonrpc") != "2.0"
        ):
            raise ProviderError(self.provider, "SCHEMA_INVALID")
        if "error" in body:
            # Never expose a provider's potentially credential-bearing error text.
            raise ProviderError(self.provider, "RPC_ERROR", 200)
        return body.get("result")

    def read(self, method, *params):
        if method not in READ_METHODS:
            raise ProviderError(self.provider, "READ_ONLY_OPERATION_REQUIRED")
        return self._rpc(method, list(params))

    def chain_id(self):
        return int(self.read("eth_chainId"), 16)

    def native_balance(self, owner):
        word(owner)
        return int(self.read("eth_getBalance", owner, "latest"), 16)

    def erc20_balance(self, token, owner):
        word(token)
        result = self.read("eth_call", {"to": token, "data": BALANCE_OF + word(owner)}, "latest")
        return self._uint256(result)

    def allowance(self, token, owner, spender):
        word(token)
        data = ALLOWANCE + word(owner) + word(spender)
        return self._uint256(self.read("eth_call", {"to": token, "data": data}, "latest"))

    def _uint256(self, result):
        if not isinstance(result, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", result):
            raise ProviderError(self.provider, "ERC20_RESULT_MISSING_OR_INVALID")
        return int(result, 16)

    def has_code(self, address):
        word(address)
        return (self.read("eth_getCode", address, "latest") or "0x") not in ("0x", "0x0")

    def nonce(self, owner):
        word(owner)
        return int(self.read("eth_getTransactionCount", owner, "pending"), 16)

    def gas_price(self):
        return int(self.read("eth_gasPrice"), 16)

    def receipt(self, tx_hash):
        if not HASH.match(tx_hash):
            raise ValueError("Invalid transaction hash")
        return self.read("eth_getTransactionReceipt", tx_hash)

    def send_raw_transaction(self, raw_hex):
        self.gates.require("SWAP")
        if not self.allow_send:
            raise ProviderError(self.provider, "LIVE_SEND_DISABLED")
        if not re.fullmatch(r"0x[0-9a-fA-F]+", raw_hex):
            raise ValueError("Invalid raw transaction")
        result = self._rpc("eth_sendRawTransaction", [raw_hex])
        if not isinstance(result, str) or not HASH.match(result):
            raise ProviderError(self.provider, "SCHEMA_INVALID")
        return result.lower()
