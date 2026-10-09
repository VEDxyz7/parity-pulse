"""Transaction signers for live execution. Keys never leave this module or reach logs.

LocalKeySigner signs legacy BSC transactions (chainId 56) with an operator-provided dev key
and sends them through the BSC RPC client. Other signers (Agentic Wallet, Altana) implement
the same `address` / `send` interface.
"""

from eth_account import Account
from eth_utils import to_checksum_address

CHAIN_ID = 56


class LocalKeySigner:
    kind = "LOCAL_KEY"

    def __init__(self, private_key, rpc):
        self._account = Account.from_key(private_key.get_secret_value())
        self.rpc = rpc

    @property
    def address(self):
        return self._account.address.lower()

    def send(self, *, to, data, value, gas, gas_price):
        tx = {
            "chainId": CHAIN_ID,
            "nonce": self.rpc.nonce(self.address),
            "to": to_checksum_address(to),
            "value": int(value),
            "gas": int(gas),
            "gasPrice": int(gas_price),
            "data": data,
        }
        signed = self._account.sign_transaction(tx)
        raw = signed.raw_transaction.hex()
        return self.rpc.send_raw_transaction(raw if raw.startswith("0x") else "0x" + raw)


class AltanaSigner:
    """BNB Agent Studio Altana smart wallet via the localhost sidecar's scoped session key.

    The session's on-chain permissions (router/approve allowlist, daily spend caps, expiry)
    bound what this signer can do even if this process is compromised.
    """

    kind = "ALTANA"

    def __init__(self, url, token, *, http=None):
        import httpx

        self.url, self.token = url.rstrip("/"), token
        self.http = http or httpx.Client(timeout=120, trust_env=False)
        self._address = None

    @property
    def address(self):
        if self._address is None:
            response = self.http.get(self.url + "/altana/status")
            response.raise_for_status()
            self._address = response.json()["wallet"].lower()
        return self._address

    def send(self, *, to, data, value, gas, gas_price):
        from app.services.live_execution import LiveExecutionError

        response = self.http.post(
            self.url + "/altana/execute",
            json={"to": to, "data": data, "value": str(int(value))},
            headers={"x-sidecar-token": self.token.get_secret_value()},
        )
        body = response.json() if response.content else {}
        tx_hash = body.get("transactionHash")
        if response.status_code != 200 or not isinstance(tx_hash, str) or len(tx_hash) != 66:
            raise LiveExecutionError("ALTANA_EXECUTE_FAILED")
        return tx_hash.lower()
