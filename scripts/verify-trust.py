"""Canonical Phase 2 read-only verification, isolated from historical milestone databases."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.clients.binance_web3 import PREFIX, READ_OPERATIONS
from app.config import ROOT_DIR, Settings
from app.database import Database
from app.services.data_layer import DataLayer
from app.services.trust import TrustService
from app.utils.logging import configure_logging


def main(live=False):
    settings = Settings(data_mode="LIVE_READ_ONLY" if live else "DEMO")
    configure_logging(settings.log_level, settings.redaction_values())
    mode = "LIVE" if live else "DEMO"
    db = Database(f"sqlite:///{ROOT_DIR / f'data/phase2-trust-{mode.lower()}-verification.db'}")
    db.initialize()
    layer = DataLayer(settings, db)
    if live:
        layer.clients[0].recv_window = 60000  # Isolated diagnostic only, unchanged safe default.
    try:
        service = TrustService(layer, db)
        result = service.assess(
            "NVDA", run_id=str(uuid4()), request_id=str(uuid4()), correlation_id=str(uuid4())
        )
        assert result.transaction_broadcast is False and result.execution_ready is False
        assert result.live_trading_enabled is False and result.llm_authoritative is False
        assert service.repository.get(result.assessment_id, mode) == result
        assert service.repository.get(result.assessment_id, "DEMO" if live else "LIVE") is None
        reads = []
        for client in layer.clients:
            for record in client.evidence:
                if client.provider == "BINANCE_WEB3":
                    method, path = record["endpoint"].split(" ", 1)
                    assert path.startswith(PREFIX)
                    assert path[len(PREFIX) :] in READ_OPERATIONS[method]
                reads.append(
                    {
                        "endpoint_tested": record["endpoint"],
                        "http_business_response_status": {
                            "http": record["http_status"],
                            "business": record["business_status"],
                        },
                        "permission_result": "VERIFIED_FOR_THIS_READ"
                        if record["capability_result"] == "PASS"
                        else "UNAVAILABLE",
                        "capability_result": record["capability_result"],
                        "timestamp_utc": record["timestamp"],
                    }
                )
        evidence = {
            "timestamp": datetime.now(UTC).isoformat(),
            "data_mode": mode,
            "verification": "ACTUAL_READ_ONLY_PROVIDERS" if live else "SYNTHETIC_DEMO",
            "ticker": result.ticker,
            "status": result.status,
            "market_regime": result.regime.state if result.regime else None,
            "representations": [
                {
                    "issuer": r.issuer,
                    "classification": r.classification,
                    "reference_status": r.reference.status,
                    "reference_quality": r.reference.observation.data_quality
                    if r.reference.observation
                    else "MISSING",
                    "liquidity_status": r.liquidity.status,
                    "news_state": r.news.state,
                    "news_coverage": r.news.coverage,
                    "baseline_episodes": r.baseline.sample_count,
                    "analogues": r.analogues.retrieved_sample_count,
                    "economic_comparison_available": r.economic_comparison is not None,
                    "reason_codes": r.reason_codes,
                    "missing_evidence": r.missing_evidence,
                }
                for r in result.representations
            ],
            "limitations": result.limitations,
            "persisted": "PASS",
            "mode_isolation": "PASS",
            "no_broadcast": "PASS",
            "llm_authoritative": False,
            "trust_gate": "BLOCKED",
            "reads": reads,
        }
        output = ROOT_DIR / f"docs/evidence/CANONICAL_PHASE_2_TRUST_{mode}.json"
        output.write_text(json.dumps(evidence, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "mode": mode,
                    "status": result.status,
                    "ticker": result.ticker,
                    "representations": len(result.representations),
                    "persisted": "PASS",
                    "no_broadcast": "PASS",
                    "evidence": str(output.relative_to(ROOT_DIR)),
                }
            )
        )
    finally:
        layer.close()
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-read-only", action="store_true")
    main(parser.parse_args().live_read_only)
