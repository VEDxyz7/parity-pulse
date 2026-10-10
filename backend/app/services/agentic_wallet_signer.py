"""Binance Agentic Wallet signer: `baw contract-call preview` -> `baw contract-call execute`.

The MPC wallet holds the key; this process never sees it. Spending limits, token allowlist
and abnormal-transaction handling are enforced by the wallet's own App-side settings.
`preview` runs Binance's simulation; a failed simulation or a risk that requires App
confirmation is refused here unless the operator explicitly allows App confirmation.

Command shapes follow binance-skills-hub `binance-agentic-wallet` (CLI 1.10.0,
references/external-sign.md). Output field names are parsed defensively and must be
verified against the installed CLI before a live run (`baw cli-check`).
"""

import json
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path

from app.clients.baw_cli import REQUIRED_CLI_VERSION, BawReadOnlyClient
from app.services.live_execution import LiveExecutionError

HEX = re.compile(r"^0x[0-9a-fA-F]*$")
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
TX_HASH = re.compile(r"0x[0-9a-fA-F]{64}")
REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class AgenticWalletError(LiveExecutionError):
    """Wallet-side refusal; the executor journals it as a rejected leg."""


def _find(value, keys):
    """Depth-first lookup of the first matching key in a decoded CLI payload."""
    if isinstance(value, dict):
        for key in keys:
            if key in value and value[key] not in (None, ""):
                return value[key]
        for item in value.values():
            found = _find(item, keys)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find(item, keys)
            if found is not None:
                return found
    return None


class AgenticWalletSigner:
    kind = "AGENTIC_WALLET"

    def __init__(self, rpc, *, executable=None, timeout=120, allow_app_confirmation=False):
        self.rpc = rpc
        found = executable or shutil.which("baw")
        if not found:
            raise AgenticWalletError("BAW_UNAVAILABLE")
        self.executable = Path(found).resolve()
        self.timeout = timeout
        self.allow_app_confirmation = allow_app_confirmation
        self.reader = BawReadOnlyClient(enabled=True, executable=str(self.executable))
        self._address = None

    @property
    def address(self):
        if self._address is None:
            payload, _, _ = self.reader.read("address")
            value = _find(payload, ("address", "evmAddress", "walletAddress"))
            if not isinstance(value, str) or not ADDRESS.match(value):
                raise AgenticWalletError("WALLET_ADDRESS_UNAVAILABLE")
            self._address = value.lower()
        return self._address

    def _run(self, args):
        env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR", "LANG") if k in os.environ}
        process = subprocess.Popen(
            [str(self.executable), *args],
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
        try:
            out, _ = process.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise AgenticWalletError("BAW_TIMEOUT") from None
        if process.returncode != 0 or len(out) > 1_048_576:
            raise AgenticWalletError("BAW_COMMAND_FAILED")
        try:
            body = json.loads(out)
        except ValueError:
            raise AgenticWalletError("BAW_OUTPUT_INVALID") from None
        if not isinstance(body, dict) or body.get("success") is not True:
            raise AgenticWalletError("BAW_REJECTED")
        return body.get("data")

    def send(self, *, to, data, value, gas, gas_price):
        if not ADDRESS.match(to) or not HEX.match(data) or int(value) < 0:
            raise AgenticWalletError("INVALID_TRANSACTION")
        check = self.reader.read("cli-check")[0]
        if not isinstance(check, dict) or check.get("currentCliVersion") != REQUIRED_CLI_VERSION:
            raise AgenticWalletError("CLI_VERSION_NOT_VERIFIED")
        preview = self._run(
            (
                "contract-call",
                "preview",
                "--binanceChainId",
                "56",
                "--from",
                self.address,
                "--to",
                to.lower(),
                "--value",
                str(int(value)),
                "--inputData",
                data,
                "--gasLimit",
                str(int(gas)),
                "--json",
            )
        )
        simulation = _find(preview, ("simulationResult",)) or {}
        status = _find(simulation, ("status",))
        if isinstance(status, str) and status.upper() not in {"SUCCESS", "PASS"}:
            raise AgenticWalletError("WALLET_SIMULATION_FAILED")
        if _find(preview, ("requireConfirmation",)) is True and not self.allow_app_confirmation:
            raise AgenticWalletError("WALLET_REQUIRES_APP_CONFIRMATION")
        request_id = _find(preview, ("requestId",))
        if not isinstance(request_id, str) or not REQUEST_ID.match(request_id):
            raise AgenticWalletError("PREVIEW_REQUEST_ID_MISSING")
        result = self._run(("contract-call", "execute", "--requestId", request_id, "--json"))
        tx_hash = _find(result, ("txHash", "transactionHash", "hash"))
        if not isinstance(tx_hash, str) or not TX_HASH.fullmatch(tx_hash):
            raise AgenticWalletError("EXECUTE_TX_HASH_MISSING")
        return tx_hash.lower()

    rfq_signing_scheme = "eip712"

    def sign_typed_data(self, typed):
        """`baw sign-message` (EIP712, eth_signTypedData_v4) per binance-skills-hub
        references/external-sign.md. Requires Developer Mode enabled in the Binance App."""
        settings = self.reader.read("settings")[0]
        dev = _find(settings, ("devMode",))
        if not isinstance(dev, dict) or dev.get("enabled") is not True:
            raise AgenticWalletError("AGENTIC_WALLET_DEV_MODE_REQUIRED")
        message = json.dumps(
            {"method": "eth_signTypedData_v4", "params": [self.address, json.dumps(typed)]},
            separators=(",", ":"),
        )
        preview = self._run(
            (
                "sign-message",
                "preview",
                "--binanceChainId",
                "56",
                "--message",
                message,
                "--signType",
                "EIP712",
                "--json",
            )
        )
        if _find(preview, ("requireConfirmation",)) is True and not self.allow_app_confirmation:
            raise AgenticWalletError("WALLET_REQUIRES_APP_CONFIRMATION")
        request_id = _find(preview, ("requestId",))
        if not isinstance(request_id, str) or not REQUEST_ID.match(request_id):
            raise AgenticWalletError("PREVIEW_REQUEST_ID_MISSING")
        result = self._run(("sign-message", "execute", "--requestId", request_id, "--json"))
        status = _find(result, ("status",))
        signature = _find(result, ("signature",))
        if status not in (None, "COMPLETED") or not isinstance(signature, str):
            raise AgenticWalletError("WALLET_SIGNATURE_UNAVAILABLE_" + str(status))
        if not re.fullmatch(r"0x[0-9a-fA-F]{130}", signature):
            raise AgenticWalletError("WALLET_SIGNATURE_MALFORMED")
        return signature
