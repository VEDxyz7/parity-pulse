"""Opt-in local Agentic Wallet read diagnostic. Prints capability metadata only."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.clients.baw_cli import BawReadOnlyClient  # noqa: E402
from app.services.agentic_wallet import AgenticWalletAdapter  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--read-only", action="store_true", help="Opt into installed official baw reads"
    )
    args = parser.parse_args()
    client = BawReadOnlyClient(enabled=args.read_only)
    adapter = AgenticWalletAdapter(client, data_mode="LIVE_READ_ONLY")
    snapshot = adapter.snapshot()
    # No address, balance, settings value, CLI body, auth material or provider message is printed.
    print(
        json.dumps(
            {
                "mode": snapshot.data_mode,
                "source": snapshot.source,
                "capability_status": snapshot.capability_status,
                "connection": snapshot.connection,
                "requested_at": snapshot.requested_at.isoformat(),
                "received_at": snapshot.received_at.isoformat(),
                "bsc_support_observed": "56" in snapshot.supported_chains,
                "errors": snapshot.errors,
                "limitations": snapshot.limitations,
                "live_authorized": False,
            }
        )
    )


if __name__ == "__main__":
    main()
