"""Teammate CLI scenarios must not bypass the independent wallet/route gates."""

import pytest

from app.services.agentic_wallet_signer import AgenticWalletSigner
from app.services.execution_gates import LiveExecutionError


@pytest.mark.parametrize(
    "legacy_result",
    [
        {"requestId": "r1", "simulationResult": {"status": "SUCCESS"}},
        {"requestId": "r1", "simulationResult": {"status": "FAILED"}},
        {"requestId": "r1", "requireConfirmation": True},
        {"simulationResult": {"status": "SUCCESS"}},
        {"devMode": {"enabled": True}},
        {"devMode": {"enabled": False}},
        {"status": "COMPLETED", "signature": "0x" + "1b" * 65},
        {"status": "PENDING_CONFIRMATION"},
        {"status": "COMPLETED", "signature": "0x12"},
    ],
)
def test_cli_preview_signature_or_dev_mode_never_unlocks_execution(tmp_path, legacy_result):
    import json

    # Any invocation writes a sentinel. The blocked gate must run before CLI use.
    sentinel = tmp_path / "called"
    script = tmp_path / "baw"
    script.write_text(
        "#!/usr/bin/env python3\nfrom pathlib import Path\n"
        f"Path({str(sentinel)!r}).touch()\nprint({json.dumps(legacy_result)!r})\n"
    )
    script.chmod(0o700)
    signer = AgenticWalletSigner(None, executable=str(script))
    with pytest.raises(LiveExecutionError, match="SWAP_LIVE_GATE_BLOCKED"):
        signer.send(to="0x" + "b" * 40, data="0x095ea7b3", value=0, gas=80000, gas_price=1)
    with pytest.raises(LiveExecutionError, match="RFQ_LIVE_GATE_BLOCKED"):
        signer.sign_typed_data({"domain": {"chainId": 56}}, order=None)
    assert not sentinel.exists()
