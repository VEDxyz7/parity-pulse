"""Bounded official CLI help/status reads. Never authenticate, preview, sign or execute."""

import json
import shutil
from datetime import UTC, datetime

from app.clients.baw_cli import REQUIRED_CLI_VERSION, BawReadOnlyClient, WalletReadError, command
from app.services.agentic_wallet import AgenticWalletAdapter
from app.services.execution_gates import LIVE_GATES


def check():
    report = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "required_cli_version": REQUIRED_CLI_VERSION,
        "installed_on_path": shutil.which("baw") is not None,
        "authenticated": "NOT_VERIFIED",
        "bsc_session": "NOT_VERIFIED",
        "preview_execution_commands": "NOT_VERIFIED",
        "execution_equivalence": "NOT_VERIFIED",
        "gates": LIVE_GATES.statuses(),
        "signing_approval_broadcast_calls": 0,
    }
    if not report["installed_on_path"]:
        return report
    reader = BawReadOnlyClient(enabled=True, timeout=2)
    try:
        version, _, _ = reader.read("cli-check")
        report["version_matches"] = (
            version.get("currentCliVersion") == REQUIRED_CLI_VERSION
            and version.get("needUpdateCli") is False
        )
        if not report["version_matches"]:
            return report
        help_text = reader._run(command("contract-help")).decode("utf-8", errors="replace")
        report["preview_execution_commands"] = (
            "HELP_OBSERVED"
            if ("preview" in help_text and "execute" in help_text)
            else "NOT_VERIFIED"
        )
        snapshot = AgenticWalletAdapter(reader, clock=reader.clock).snapshot()
        report["authenticated"] = snapshot.connection
        report["bsc_session"] = (
            "VERIFIED_READ"
            if (
                snapshot.capability_status == "VERIFIED_READ"
                and "56" in snapshot.supported_chains
                and snapshot.bsc_address is not None
            )
            else "NOT_VERIFIED"
        )
        report["snapshot_errors"] = snapshot.errors
        report["developer_mode"] = (
            snapshot.settings.developer_enabled if snapshot.settings else None
        )
        report["pending_state"] = snapshot.pending_state
    except (WalletReadError, ValueError, TypeError, AttributeError):
        report["runtime_check"] = "UNAVAILABLE_OR_INVALID"
    return report


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
