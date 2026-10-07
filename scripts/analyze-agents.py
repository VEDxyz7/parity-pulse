"""Phase 6 structured JSON analysis. Offline; no keys, providers or execution gateways."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.adapters import DemoEvidenceAdapter, LiveReadOnlyEvidenceAdapter  # noqa: E402
from app.agents.memory import AgentStore  # noqa: E402
from app.agents.orchestrator import AgentOrchestrator  # noqa: E402
from app.repositories.research import ResearchStore  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", choices=("steady", "thin-move", "supported-move"))
    source.add_argument("--real-replay", type=Path)
    parser.add_argument("--row", type=int, default=0)
    parser.add_argument(
        "--intent",
        default=("I have $60 and can lose up to $2; find me an opportunity before Monday."),
    )
    parser.add_argument("--store", type=Path, default=ROOT / "data/agents/phase6")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.evidence and args.evidence.exists():
        raise ValueError("Do not overwrite historical evidence")
    if args.real_replay:
        replay = ResearchStore(args.real_replay.parent).load(args.real_replay.stem)
        bundle = LiveReadOnlyEvidenceAdapter().from_replay(replay, row_index=args.row)
    else:
        bundle = DemoEvidenceAdapter().load(args.demo)
    store = AgentStore(args.store)
    try:
        result = asyncio.run(AgentOrchestrator(store=store).analyze(args.intent, bundle))
        output = result.model_dump_json(indent=2)
        if args.evidence:
            with args.evidence.open("x") as stream:
                stream.write(output + "\n")
        print(output)
    finally:
        store.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never render arbitrary source/provider/validation exceptions or raw request text.
        print(
            json.dumps(
                {
                    "status": "FAILED_CLOSED",
                    "execution_authorized": False,
                    "reason": "INVALID_OR_UNAVAILABLE_AGENT_INPUT",
                }
            )
        )
        raise SystemExit(1) from None
