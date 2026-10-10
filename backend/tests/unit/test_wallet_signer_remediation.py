"""Wallet adapters are tested with synthetic responses and no CLI/sidecar execution."""

from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.services.agentic_wallet_signer import (
    AgenticWalletError,
    AgenticWalletSigner,
    assemble_signature,
    validate_preview,
)
from app.services.execution_gates import LiveExecutionError
from app.services.live_signer import AltanaSigner, verify_contract_signature
from app.services.rfq_orders import verify
from backend.tests.fixtures.rfq_orders import ALLOW, EXPECTED, OTHER, WALLET, cow
from backend.tests.unit.test_live_execution import OfflinePolicy


def preview():
    return {
        "requestId": "fixture",
        "requireConfirmation": False,
        "simulationResult": {
            "simulationCode": "000000000",
            "simulationErrorDetail": None,
            "preCheckCode": "",
            "authorityChanges": [],
        },
        "risks": {"riskDetails": [], "addresses": {}, "riskBehaviors": []},
    }


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "missing_sim",
        "old_status",
        "error",
        "risk",
        "authority",
        "confirmation",
        "missing_precheck",
    ],
)
def test_missing_or_ambiguous_preview_never_authorizes_execute(defect):
    value = preview()
    if defect == "missing":
        value = None
    elif defect == "missing_sim":
        value.pop("simulationResult")
    elif defect == "old_status":
        value["simulationResult"] = {"status": "SUCCESS"}
    elif defect == "error":
        value["simulationResult"]["simulationCode"] = "351805"
    elif defect == "risk":
        value["risks"]["riskDetails"] = [{"code": "RISK"}]
    elif defect == "authority":
        value["simulationResult"]["authorityChanges"] = [{}]
    elif defect == "confirmation":
        value.pop("requireConfirmation")
    else:
        value["simulationResult"].pop("preCheckCode")
    with pytest.raises(AgenticWalletError):
        validate_preview(value)


def test_success_code_does_not_claim_exact_runtime_equivalence():
    assert validate_preview(preview()) == "fixture"
    signer = AgenticWalletSigner.__new__(AgenticWalletSigner)
    signer.gates = OfflinePolicy()
    with pytest.raises(AgenticWalletError, match="EQUIVALENCE_UNVERIFIED"):
        signer.send(to=OTHER, data="0x1234", value=0, gas=200000, gas_price=1)


@pytest.mark.parametrize("recovery,expected", [(0, "1b"), (1, "1c"), (27, "1b"), (28, "1c")])
def test_separate_recovery_byte_is_not_dropped(recovery, expected):
    assert assemble_signature(
        {"status": "COMPLETED", "signature": "0x" + "a" * 128, "signatureRecovery": recovery}
    ).endswith(expected)


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"status": "COMPLETED", "signature": "0x1234"},
        {"status": "COMPLETED", "signature": "0x" + "a" * 128, "signatureRecovery": True},
    ],
)
def test_malformed_signature_response_rejected(result):
    with pytest.raises(AgenticWalletError):
        assemble_signature(result)


def test_erc1271_checks_exact_wallet_digest_and_chain():
    calls = []
    rpc = SimpleNamespace(chain_id=lambda: 56, has_code=lambda _: True)
    rpc.read = lambda *args: calls.append(args) or "0x1626ba7e" + "0" * 56
    digest = "0x" + "b" * 64
    assert verify_contract_signature(rpc, WALLET, digest, "0x1234")
    assert calls[0][1]["to"] == WALLET and digest[2:] in calls[0][1]["data"]
    rpc.read = lambda *args: "0xffffffff" + "0" * 56
    with pytest.raises(LiveExecutionError, match="SIGNATURE_INVALID"):
        verify_contract_signature(rpc, WALLET, digest, "0x1234")
    rpc.chain_id = lambda: 1
    with pytest.raises(LiveExecutionError, match="IDENTITY_INVALID"):
        verify_contract_signature(rpc, WALLET, digest, "0x1234")


def test_sidecar_http_signature_is_not_proof():
    rpc = SimpleNamespace(
        chain_id=lambda: 56, has_code=lambda _: True, read=lambda *args: "0xffffffff" + "0" * 56
    )
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"signature": "0x1234"}))
    signer = AltanaSigner(
        "http://127.0.0.1:8787",
        SecretStr("fixture-token"),
        rpc=rpc,
        wallet=WALLET,
        http=httpx.Client(transport=transport),
        gates=OfflinePolicy(),
    )
    order = verify("CowSwap", cow(), EXPECTED, ALLOW)
    with pytest.raises(LiveExecutionError, match="ERC1271_SIGNATURE_INVALID"):
        signer.sign_typed_data(cow(), order=order)
    with pytest.raises(LiveExecutionError, match="IDENTITY_MISMATCH"):
        signer.sign_typed_data(cow(buyAmount=str(EXPECTED.min_buy + 1)), order=order)
    wrong = AltanaSigner(
        "http://127.0.0.1:8787",
        SecretStr("fixture-token"),
        rpc=rpc,
        wallet=OTHER,
        http=signer.http,
        gates=OfflinePolicy(),
    )
    with pytest.raises(LiveExecutionError, match="IDENTITY_MISMATCH"):
        wrong.sign_typed_data(cow(), order=order)
    signer.http.close()


def test_agentic_gate_blocks_before_runtime_access():
    from app.services.execution_gates import LIVE_GATES

    signer = AgenticWalletSigner.__new__(AgenticWalletSigner)
    signer.gates = LIVE_GATES
    with pytest.raises(LiveExecutionError, match="SWAP_LIVE_GATE_BLOCKED"):
        signer.send()
