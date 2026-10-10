"""Gated signing adapters. Broadcast requires a durably journaled signed identity.

Signed bytes exist only in memory and are excluded from repr. No keys/signatures are
returned to public status APIs. Wallet workers remain disabled by server-owned gates.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx
from eth_abi import encode
from eth_account import Account
from eth_utils import keccak, to_checksum_address
from pydantic import SecretStr

from app.models.execution import EvmTransaction, address, fingerprint
from app.services.execution_gates import LIVE_GATES, LiveExecutionError
from app.services.rfq_orders import order_hash


@dataclass(frozen=True)
class SignedTransaction:
    tx_hash: str
    nonce: int
    payload_digest: str
    raw: SecretStr = field(repr=False)


class LocalKeySigner:
    kind = "LOCAL_KEY"
    rfq_signing_scheme = "eip712"

    def __init__(self, private_key, rpc, *, gates=LIVE_GATES):
        self._account = Account.from_key(private_key.get_secret_value())
        self.rpc, self.gates = rpc, gates

    @property
    def address(self):
        return self._account.address.lower()

    def prepare(self, tx):
        self.gates.require("SWAP")
        tx = EvmTransaction.model_validate_json(tx.model_dump_json())
        if self.rpc.chain_id() != 56 or tx.sender != self.address:
            raise LiveExecutionError("SIGNER_CHAIN_OR_SENDER_MISMATCH")
        nonce = self.rpc.nonce(self.address)
        signed = self._account.sign_transaction(
            {
                "chainId": 56,
                "nonce": nonce,
                "to": to_checksum_address(tx.to),
                "value": int(tx.value),
                "gas": int(tx.gas),
                "gasPrice": int(tx.gasPrice),
                "data": tx.data,
            }
        )
        return SignedTransaction(
            "0x" + signed.hash.hex(),
            nonce,
            fingerprint(tx),
            SecretStr("0x" + signed.raw_transaction.hex()),
        )

    def broadcast(self, prepared, *, journal, action_id, kind):
        self.gates.require("SWAP")
        attempt = journal.submission(action_id, kind)
        if not attempt or attempt != {
            "identity": prepared.tx_hash,
            "nonce": prepared.nonce,
            "payload_digest": prepared.payload_digest,
        }:
            raise LiveExecutionError("DURABLE_SIGNED_IDENTITY_REQUIRED")
        if "0x" + keccak(bytes.fromhex(prepared.raw.get_secret_value()[2:])).hex() != (
            prepared.tx_hash
        ):
            raise LiveExecutionError("SIGNED_TRANSACTION_HASH_MISMATCH")
        result = self.rpc.send_raw_transaction(prepared.raw.get_secret_value())
        if result != prepared.tx_hash:
            raise LiveExecutionError("BROADCAST_RESPONSE_HASH_MISMATCH")
        return result

    def send(self, **_kwargs):
        self.gates.require("SWAP")
        raise LiveExecutionError("DURABLE_SUBMISSION_CONTEXT_REQUIRED")

    def sign_typed_data(self, typed, *, order):
        self.gates.require("RFQ")
        digest, full = order_hash(typed)
        if digest != order.order_hash or order.wallet != self.address:
            raise LiveExecutionError("SIGNATURE_ORDER_IDENTITY_MISMATCH")
        signature = self._account.sign_typed_data(full_message=full).signature
        return SecretStr("0x" + signature.hex())


def verify_contract_signature(rpc, wallet, digest, signature):
    """ERC-1271 bytes32/bytes; no HTTP/SDK assertion can replace eth_call magic value."""
    wallet = address(wallet)
    if (
        rpc.chain_id() != 56
        or not rpc.has_code(wallet)
        or not re.fullmatch(r"0x[0-9a-fA-F]{64}", digest)
        or not isinstance(signature, str)
        or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2}){1,4096}", signature)
    ):
        raise LiveExecutionError("ERC1271_IDENTITY_INVALID")
    data = (
        "0x1626ba7e"
        + encode(
            ["bytes32", "bytes"], [bytes.fromhex(digest[2:]), bytes.fromhex(signature[2:])]
        ).hex()
    )
    result = rpc.read("eth_call", {"to": wallet, "data": data}, "latest")
    if result != "0x1626ba7e" + "0" * 56:
        raise LiveExecutionError("ERC1271_SIGNATURE_INVALID")
    return True


class AltanaSigner:
    kind = "ALTANA"
    rfq_signing_scheme = "eip1271"

    def __init__(self, url, token, *, rpc, wallet, http=None, gates=LIVE_GATES):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Loopback sidecar required")
        self.url, self.token, self.rpc = url.rstrip("/"), token, rpc
        self._address, self.gates = address(wallet), gates
        self.http = http or httpx.Client(timeout=10, trust_env=False, follow_redirects=False)

    @property
    def address(self):
        return self._address

    def send(self, **_kwargs):
        self.gates.require("SWAP", wallet=True)
        # Sidecar user-operation hash, nonce and exact simulation are not verified.
        raise LiveExecutionError("ALTANA_EXECUTION_EQUIVALENCE_UNVERIFIED")

    def sign_typed_data(self, typed, *, order):
        self.gates.require("RFQ", wallet=True)
        digest, _ = order_hash(typed)
        if digest != order.order_hash or order.wallet != self.address:
            raise LiveExecutionError("SIGNATURE_ORDER_IDENTITY_MISMATCH")
        response = self.http.post(
            self.url + "/altana/sign-typed-data",
            json={"typedData": typed},
            headers={"x-sidecar-token": self.token.get_secret_value()},
        )
        try:
            body = response.json()
            signature = body.get("signature") if isinstance(body, dict) else None
        except ValueError:
            signature = None
        if response.status_code != 200:
            raise LiveExecutionError("ALTANA_SIGN_FAILED")
        verify_contract_signature(self.rpc, self.address, digest, signature)
        return SecretStr(signature)
