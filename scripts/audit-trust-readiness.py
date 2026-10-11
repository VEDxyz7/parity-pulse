"""Offline Trust evidence audit; SQLite mode=ro, no API calls or application startup."""

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.schemas import GateStatus  # noqa: E402
from app.models.demo_sandbox import DemoProductionGates  # noqa: E402
from app.providers.finnhub import FinnhubEventProvider  # noqa: E402
from app.repositories.historical_inputs import read_historical_input  # noqa: E402
from app.repositories.research_source import HistoricalSource  # noqa: E402
from app.services.calendar import USEquityCalendar  # noqa: E402
from app.services.research_episodes import ResearchEpisodeBuilder, candidate_frames  # noqa: E402


def database_hashes():
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT / "data").glob("*.db*"))
        if p.is_file()
    }


def audit():
    before = database_hashes()
    source = HistoricalSource(ROOT).load()
    records = source.records
    builder = ResearchEpisodeBuilder(USEquityCalendar())
    episodes = []
    for frame in candidate_frames(
        builder.calendar,
        metadata=records["token_metadata"],
        tokens=[*records["token_observations"], *records["raw_token_bars"]],
        equities=records["equity_observations"],
        news=records["news_events"],
    ):
        frame = frame.model_copy(
            update={
                "samples": tuple(records["trust_samples"]),
                "baseline_episodes": tuple(records["trust_episodes"]),
            }
        )
        episodes.append(builder.build(frame))

    # Re-normalize an already captured real response; no transport/client is constructed.
    capture = read_historical_input(ROOT, "MULTI_PROVIDER_DATA_20261010.json")
    holiday = next(
        c["result"] for c in capture["finnhub"]["checks"] if c["label"] == "/stock/market-holiday"
    )
    batch = FinnhubEventProvider(
        SimpleNamespace(
            read=lambda *args, **kwargs: (
                holiday["body"],
                datetime.fromisoformat(holiday["received_at"]),
                "OK",
            )
        )
    ).get_market_holidays()
    after = database_hashes()
    if before != after:
        raise ValueError(
            "Database files changed during the read-only audit; investigate separately"
        )
    return {
        "scope": "OFFLINE_READ_ONLY_TRUST_BLOCKER_AUDIT",
        "gate_contract": DemoProductionGates().model_dump(),
        "system_status_gate_subset": GateStatus().model_dump(),
        "coverage": source.coverage(),
        "observation_inventory": {
            name: {
                "count": len(records[name]),
                "source_counts": dict(Counter(r.source for r in records[name])),
                "quality_counts": dict(Counter(r.data_quality for r in records[name])),
                "missing_source_timestamp": sum(r.source_timestamp is None for r in records[name]),
            }
            for name in (
                "token_metadata",
                "token_observations",
                "equity_observations",
                "news_events",
            )
        },
        "current_offline_replay": {
            "candidate_representation_windows": len(episodes),
            "distinct_openings": len({e.target.opening_at for e in episodes}),
            "issuer_counts": dict(Counter(e.decision.issuer for e in episodes)),
            "decision_quality_counts": dict(Counter(e.decision.data_quality for e in episodes)),
            "target_status_counts": dict(Counter(e.target.status for e in episodes)),
            "rejection_counts": dict(Counter(r for e in episodes for r in e.decision.reasons)),
            "eligible_decisions": sum(e.decision.data_quality == "ELIGIBLE" for e in episodes),
            "verified_targets": sum(e.target.status == "AVAILABLE" for e in episodes),
            "loaded_point_in_time_proofs": 0,
            "proof_limitation": "Existing candidate_frames loader supplies no proof ledger",
        },
        "holiday_replay": {
            "original_receipt": holiday["received_at"],
            "endpoint": "/stock/market-holiday",
            "quality_counts": dict(Counter(r.data_quality for r in batch.records)),
            "invalid_records": [
                r.model_dump(mode="json") for r in batch.records if r.data_quality == "INVALID"
            ],
        },
        "input_provenance": source.provenance,
        "database_sha256": before,
        "database_bytes_unchanged": before == after,
        "api_requests": 0,
        "production_writes": 0,
        "execution_calls": 0,
        "gates_modified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional NEW JSON evidence file")
    args = parser.parse_args()
    if args.output and (args.output.suffix != ".json" or args.output.exists()):
        parser.error("Output must be a new JSON file; existing evidence is never overwritten")
    report = audit()
    content = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        with args.output.open("x") as target:
            target.write(content)
        print("Offline Trust audit saved; API requests=0, production writes=0")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
