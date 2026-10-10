import json
import stat

import pytest

from app.services.agentic_wallet_signer import AgenticWalletError, AgenticWalletSigner

WALLET = "0x" + "a" * 40
TX = "0x" + "c" * 64


def fake_baw(tmp_path, preview, sign_preview=None, sign_result=None, dev=True):
    """Executable stub answering the documented baw commands with JSON envelopes."""
    script = tmp_path / "baw"
    replies = {
        "cli-check": {"currentCliVersion": "1.10.0", "needUpdateCli": False},
        "address": {"address": WALLET},
        "preview": preview,
        "execute": {"txHash": TX},
        "settings": {"devMode": {"enabled": dev}},
        "sign-preview": sign_preview or {"requestId": "s1", "requireConfirmation": False},
        "sign-execute": sign_result or {"status": "COMPLETED", "signature": "0x" + "1b" * 65},
    }
    script.write_text(
        "#!/usr/bin/env python3\nimport json,sys\nr="
        + repr(json.dumps(replies))
        + "\nr=json.loads(r)\na=sys.argv[1:]\n"
        "k='cli-check' if a[0]=='cli-check' else ('sign-'+a[1]) if a[0]=='sign-message' "
        "else a[1] if a[0] in ('wallet','contract-call') else a[0]\n"
        "print(json.dumps({'success':True,'data':r[k]}))\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def send(signer):
    return signer.send(to="0x" + "b" * 40, data="0x095ea7b3", value=0, gas=80000, gas_price=1)


def test_preview_then_execute_returns_hash(tmp_path):
    exe = fake_baw(tmp_path, {"requestId": "r1", "simulationResult": {"status": "SUCCESS"}})
    signer = AgenticWalletSigner(None, executable=exe)
    assert signer.address == WALLET and send(signer) == TX


@pytest.mark.parametrize(
    "preview,code",
    [
        ({"requestId": "r1", "simulationResult": {"status": "FAILED"}}, "WALLET_SIMULATION_FAILED"),
        ({"requestId": "r1", "requireConfirmation": True}, "WALLET_REQUIRES_APP_CONFIRMATION"),
        ({"simulationResult": {"status": "SUCCESS"}}, "PREVIEW_REQUEST_ID_MISSING"),
    ],
)
def test_failed_preview_never_executes(tmp_path, preview, code):
    signer = AgenticWalletSigner(None, executable=fake_baw(tmp_path, preview))
    with pytest.raises(AgenticWalletError) as caught:
        send(signer)
    assert caught.value.code == code


TYPED = {"types": {"EIP712Domain": []}, "domain": {"chainId": 56}, "primaryType": "X", "message": {}}


def test_sign_message_preview_then_execute_returns_signature(tmp_path):
    exe = fake_baw(tmp_path, {})
    assert AgenticWalletSigner(None, executable=exe).sign_typed_data(TYPED) == "0x" + "1b" * 65


@pytest.mark.parametrize(
    "kwargs,code",
    [
        (dict(dev=False), "AGENTIC_WALLET_DEV_MODE_REQUIRED"),
        (dict(sign_preview={"requestId": "s1", "requireConfirmation": True}), "WALLET_REQUIRES_APP_CONFIRMATION"),
        (dict(sign_result={"status": "PENDING_CONFIRMATION"}), "WALLET_SIGNATURE_UNAVAILABLE_PENDING_CONFIRMATION"),
        (dict(sign_result={"status": "COMPLETED", "signature": "0x12"}), "WALLET_SIGNATURE_MALFORMED"),
    ],
)
def test_sign_message_refusals(tmp_path, kwargs, code):
    signer = AgenticWalletSigner(None, executable=fake_baw(tmp_path, {}, **kwargs))
    with pytest.raises(AgenticWalletError) as caught:
        signer.sign_typed_data(TYPED)
    assert caught.value.code == code
