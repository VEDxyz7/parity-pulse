import json
import stat

import pytest

from app.services.agentic_wallet_signer import AgenticWalletError, AgenticWalletSigner

WALLET = "0x" + "a" * 40
TX = "0x" + "c" * 64


def fake_baw(tmp_path, preview):
    """Executable stub answering the documented baw commands with JSON envelopes."""
    script = tmp_path / "baw"
    replies = {
        "cli-check": {"currentCliVersion": "1.10.0", "needUpdateCli": False},
        "address": {"address": WALLET},
        "preview": preview,
        "execute": {"txHash": TX},
    }
    script.write_text(
        "#!/usr/bin/env python3\nimport json,sys\nr="
        + repr(json.dumps(replies))
        + "\nr=json.loads(r)\na=sys.argv[1:]\n"
        "k='cli-check' if a[0]=='cli-check' else a[1] if a[0] in ('wallet','contract-call') "
        "else a[0]\nprint(json.dumps({'success':True,'data':r[k]}))\n"
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
