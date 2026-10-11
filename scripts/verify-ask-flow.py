"""Explicit read-only Ask verification; credentials stay in memory, never in evidence."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import ROOT_DIR, Settings
from app.database import Database
from app.services.data_layer import DataLayer
from app.services.exposure import ExposureService
from app.utils.artifacts import diagnostic_output
from app.utils.logging import configure_logging


def main(live=False):
    settings = Settings(data_mode="LIVE_READ_ONLY" if live else "DEMO")
    configure_logging(settings.log_level, settings.redaction_values())
    mode = "LIVE" if live else "DEMO"
    db = Database(f"sqlite:///{ROOT_DIR / f'data/phase1-{mode.lower()}-verification.db'}")
    db.initialize()
    layer = DataLayer(settings, db)
    if live:
        layer.clients[0].recv_window = 60000  # Bounded verification only; default stays 5000.
    try:
        service = ExposureService(layer, db)
        result = service.propose(
            "I have $50 of Nvidia",
            run_id=str(uuid4()),
            request_id=str(uuid4()),
            correlation_id=str(uuid4()),
        )
        assert result.execution_ready is False and result.transaction_broadcast is False
        assert result.require_simulation is True and result.simulation_status == "UNAVAILABLE"
        assert service.repository.get(result.proposal_id, mode, result.created_at) == result
        assert (
            service.repository.get(
                result.proposal_id, "DEMO" if live else "LIVE", result.created_at
            )
            is None
        )
        assert service.repository.get(result.proposal_id, mode, result.valid_until).selected is None
        evidence = {
            "timestamp": datetime.now(UTC).isoformat(),
            "data_mode": mode,
            "verification": "ACTUAL_READ_ONLY_PROVIDERS" if live else "SYNTHETIC_DEMO",
            "request": "I have $50 of Nvidia",
            "proposal_status": result.status,
            "resolved_ticker": result.ticker,
            "selected_issuer": result.selected.issuer if result.selected else None,
            "representations": len(result.representations),
            "persisted": "PASS",
            "mode_isolation": "PASS",
            "expiry_fail_closed": "PASS",
            "no_broadcast": "PASS",
            "simulation_status": "UNAVAILABLE",
            "execution_ready": False,
            "independent_current_equity": result.independent_equity.status,
            "limitations": result.limitations,
        }
        if not live:
            assert result.status == "DRY_RUN"
            evidence["proposal"] = json.loads(result.model_dump_json())
        else:
            # Keep the entitlement ledger restricted to endpoint/status/permission/capability/time.
            evidence["reads"] = [
                {
                    "endpoint_tested": row["endpoint"],
                    "http_business_response_status": {
                        "http": row["http_status"],
                        "business": row["business_status"],
                    },
                    "permission_result": "VERIFIED_FOR_THIS_READ"
                    if row["capability_result"] == "PASS"
                    else "UNAVAILABLE",
                    "capability_result": row["capability_result"],
                    "timestamp_utc": row["timestamp"],
                }
                for client in layer.clients
                for row in client.evidence
            ]
        path = diagnostic_output(ROOT_DIR, f"CANONICAL_PHASE_1_{mode}.json")
        path.write_text(json.dumps(evidence, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "mode": mode,
                    "proposal_status": result.status,
                    "persisted": "PASS",
                    "no_broadcast": "PASS",
                    "evidence": str(path.relative_to(ROOT_DIR)),
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
