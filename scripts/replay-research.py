"""Offline Phase 5 real-data audit/replay. No environment secrets or network access."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.repositories.research import ResearchStore  # noqa: E402
from app.repositories.research_source import HistoricalSource  # noqa: E402
from app.services.calendar import USEquityCalendar  # noqa: E402
from app.services.research_episodes import ResearchEpisodeBuilder, candidate_frames  # noqa: E402
from app.services.research_replay import HistoricalReplay  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=ROOT / "data/research/phase5")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.evidence and args.evidence.exists():
        raise ValueError("Existing evidence must not be overwritten")
    source = HistoricalSource(ROOT).load()
    calendar = USEquityCalendar()
    builder = ResearchEpisodeBuilder(calendar)
    records = source.records
    frames = candidate_frames(
        calendar,
        metadata=records["token_metadata"],
        tokens=[*records["token_observations"], *records["raw_token_bars"]],
        equities=records["equity_observations"],
        news=records["news_events"],
    )
    episodes = []
    for frame in frames:
        frame = frame.model_copy(
            update={
                "samples": tuple(records["trust_samples"]),
                "baseline_episodes": tuple(records["trust_episodes"]),
            }
        )
        episodes.append(builder.build(frame))
    run = HistoricalReplay().run(episodes, provenance=source.provenance)
    artifact = ResearchStore(args.store).save(run)
    by_id = {e.episode_id: e for e in episodes}
    result = {
        "implementation_evidence": "OFFLINE_REAL_DATA_REPLAY_NOT_SYNTHETIC",
        "run_id": run.run_id,
        "dataset_digest": run.dataset_digest,
        "implementation_digest": run.implementation_digest,
        "coverage": source.coverage(),
        "candidate_episodes": len(episodes),
        "candidate_openings": len({e.target.opening_at for e in episodes}),
        "candidate_counts_by_issuer": dict(Counter(e.decision.issuer for e in episodes)),
        "posthoc_outcomes": sum(e.target.opening_return is not None for e in episodes),
        "qualifying_baseline_episodes": len(records["trust_episodes"]),
        "qualifying_opening_model_episodes": run.eligible_episode_count,
        "qualifying_analogues": max((r.retrieval.eligible_count for r in run.rows), default=0),
        "predictions": run.prediction_count,
        "rejection_counts": dict(
            sorted(Counter(reason for e in episodes for reason in e.decision.reasons).items())
        ),
        "phase_5_data_gate": "PASS"
        if any(
            row.prediction.status == "READY"
            and row.prediction.sample_count >= 30
            and row.retrieval.retrieved_count >= 3
            and by_id[row.episode_id].decision.trust is not None
            and by_id[row.episode_id].decision.trust.baseline.sample_count >= 30
            for row in run.rows
        )
        else "BLOCKED",
        "trust_gate": run.trust_gate,
        "opportunity_gate": run.opportunity_gate,
        "production_writes": 0,
        "execution_calls": 0,
        "artifact": str(artifact.relative_to(ROOT))
        if artifact.is_relative_to(ROOT)
        else str(artifact),
    }
    if args.evidence:
        with args.evidence.open("x") as stream:
            stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
