"""Read-only CLI inspection and strict preview validation; runtime execution unavailable.

Official preview covers from/to/value/data, not our exact legacy gas/nonce envelope.
No invented echo/expiry fields or status aliases may authorize an execute command.
Use the established AgenticWalletAdapter for application reads and proposals.
"""

import re
import shutil
from pathlib import Path

from app.clients.baw_cli import BawReadOnlyClient
from app.services.execution_gates import LIVE_GATES, LiveExecutionError


class AgenticWalletError(LiveExecutionError):
    pass


def validate_preview(preview):
    if not isinstance(preview, dict):
        raise AgenticWalletError("WALLET_PREVIEW_MISSING")
    sim = preview.get("simulationResult")
    if (
        not isinstance(sim, dict)
        or sim.get("simulationCode") != "000000000"
        or sim.get("simulationErrorDetail") not in (None, "")
        or sim.get("preCheckCode") != ""
    ):
        raise AgenticWalletError("WALLET_SIMULATION_FAILED_OR_MISSING")
    risks = preview.get("risks")
    if (
        not isinstance(risks, dict)
        or risks.get("riskDetails") != []
        or risks.get("riskBehaviors") != []
        or risks.get("addresses") != {}
        or sim.get("authorityChanges") != []
    ):
        raise AgenticWalletError("WALLET_RISK_OR_AUTHORITY_REQUIRES_REVIEW")
    if preview.get("requireConfirmation") is not False:
        raise AgenticWalletError("WALLET_EXPLICIT_CONFIRMATION_REQUIRED")
    request_id = preview.get("requestId")
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id):
        raise AgenticWalletError("PREVIEW_REQUEST_ID_MISSING")
    return request_id


def assemble_signature(result):
    if not isinstance(result, dict) or result.get("status") != "COMPLETED":
        raise AgenticWalletError("WALLET_SIGNATURE_UNAVAILABLE")
    value, recovery = result.get("signature"), result.get("signatureRecovery")
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"0x[0-9a-fA-F]{128}", value)
        or type(recovery) is not int
        or recovery not in (0, 1, 27, 28)
    ):
        raise AgenticWalletError("WALLET_SIGNATURE_MALFORMED")
    return value.lower() + format(recovery + 27 if recovery < 2 else recovery, "02x")


class AgenticWalletSigner:
    kind = "AGENTIC_WALLET"
    rfq_signing_scheme = "eip712"

    def __init__(self, rpc, *, executable=None, gates=LIVE_GATES):
        self.rpc, self.gates = rpc, gates
        found = executable or shutil.which("baw")
        if not found:
            raise AgenticWalletError("BAW_UNAVAILABLE")
        self.executable = Path(found).resolve()
        self.reader = BawReadOnlyClient(enabled=True, executable=str(self.executable))

    def send(self, **_kwargs):
        self.gates.require("SWAP", wallet=True)
        raise AgenticWalletError("WALLET_GAS_NONCE_PREVIEW_EQUIVALENCE_UNVERIFIED")

    def sign_typed_data(self, _typed, *, order):
        self.gates.require("RFQ", wallet=True)
        raise AgenticWalletError("WALLET_SIGNING_PREVIEW_CONFIRMATION_RUNTIME_UNVERIFIED")
