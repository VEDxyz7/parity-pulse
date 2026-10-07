"""Offline Phase 7 scan: existing synthetic fixtures or a captured typed real snapshot."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.memory import AgentStore  # noqa: E402
from app.agents.orchestrator import AgentOrchestrator  # noqa: E402
from app.models.opportunity_scan import OpportunityRequest, ScanSnapshot  # noqa: E402
from app.repositories.opportunity_scan import OpportunityScanStore  # noqa: E402
from app.services.opportunity_scan import OpportunityScanService  # noqa: E402
from app.services.opportunity_sources import DemoScanSource  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", choices=("steady", "thin-move", "supported-move"))
    source.add_argument("--snapshot", type=Path)
    parser.add_argument("--budget", required=True)
    parser.add_argument("--risk-budget", required=True)
    parser.add_argument("--window", choices=("PRE_OPEN", "BEFORE_MONDAY"), default="PRE_OPEN")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--store", type=Path, default=ROOT / "data/opportunity/phase7")
    args = parser.parse_args()
    if args.evidence and args.evidence.exists():
        raise ValueError("Historical evidence cannot be overwritten")
    request = OpportunityRequest(
        budget_usd=args.budget,
        risk_budget_usd=args.risk_budget,
        time_window=args.window,
        demo_scenario=args.demo,
    )
    store, agents = OpportunityScanStore(args.store), AgentStore(args.store / "agents")
    try:
        service = OpportunityScanService(store=store, orchestrator=AgentOrchestrator(store=agents))
        snapshot = (
            ScanSnapshot.model_validate_json(args.snapshot.read_text())
            if args.snapshot
            else DemoScanSource().capture(request, service.policy)
        )
        result = asyncio.run(service.scan(request, snapshot))
        output = result.model_dump_json(indent=2)
        if args.evidence:
            with args.evidence.open("x") as stream:
                stream.write(output + "\n")
        print(output)
    finally:
        store.close()
        agents.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            json.dumps(
                {
                    "status": "FAILED_CLOSED",
                    "execution_authorized": False,
                    "reason": "INVALID_OR_UNAVAILABLE_SCAN_INPUT",
                }
            )
        )
        raise SystemExit(1) from None
