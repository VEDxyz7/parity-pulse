"""Offline Phase 16 timing/functional probes. Synthetic, temporary, no live providers.

Measures warm local latency, not provider/network throughput or predictive quality.
No credentials are loaded. Writes evidence only to the explicitly requested path.
"""

import argparse
import contextlib
import json
import math
import os
import statistics
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from fastapi.testclient import TestClient  # noqa: E402

from app.services.routing import RoutingService  # noqa: E402
from backend.tests.fixtures.frontend_phase15 import factory  # noqa: E402
from backend.tests.unit.test_opportunity_scan import (  # noqa: E402
    request,
    scan,
    snapshot,
    universe,
)
from backend.tests.unit.test_portfolio import evaluate, route, setup  # noqa: E402


def measure(operation, samples=7):
    operation()  # Explicit warmup; included nowhere in the latency distribution.
    times = []
    for _ in range(samples):
        start = perf_counter()
        operation()
        times.append((perf_counter() - start) * 1000)
    ordered = sorted(times)
    return {
        "samples": samples,
        "median_ms": round(statistics.median(times), 3),
        "p95_ms": round(ordered[math.ceil(0.95 * samples) - 1], 3),
        "min_ms": round(min(times), 3),
        "max_ms": round(max(times), 3),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    if args.evidence.exists():
        raise ValueError("Refuse to overwrite evidence")
    result = {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "dataset_type": "SYNTHETIC_TEST_ONLY",
        "production_eligible": False,
        "methodology": (
            "Single process, perf_counter monotonic, one warmup, seven measured samples; "
            "p95 nearest-rank. No provider latency; no pass threshold invented."
        ),
        "paths": {},
        "universes": {},
        "live_execution_calls": 0,
    }
    original = os.environ.get("PARITY_PHASE15_DIR")
    with tempfile.TemporaryDirectory(prefix="parity-phase16-perf-") as folder:
        os.environ["PARITY_PHASE15_DIR"] = folder
        try:
            with (Path(folder) / "benchmark.log").open("w") as log, contextlib.redirect_stdout(log):
                app = factory("DEMO")
                with TestClient(
                    app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 123)
                ) as client:

                    def read(path):
                        response = client.get(path)
                        assert response.status_code == 200
                        return response.json()

                    state = app.state
                    result["paths"]["asset_discovery"] = measure(
                        lambda: state.data_layer.discovery.resolve("NVDA")
                    )
                    for name, path in (
                        ("issuer_comparison", "/api/terminal/issuers?ticker=NVDA"),
                        ("trust_calculation", "/api/demo/trust/scenarios/supported-move"),
                        ("scorecard_query", "/api/scorecard"),
                        ("audit_query", "/api/audit"),
                        ("terminal_api", "/api/terminal"),
                    ):
                        result["paths"][name] = measure(lambda path=path: read(path))

                    def tool():
                        response = client.post("/api/agent/tools/get_portfolio", json={})
                        assert response.status_code == 200
                        value = response.json()
                        assert not value["transaction_broadcast"] and not value["execution_ready"]

                    result["paths"]["agent_api_tool"] = measure(tool)
                    router = RoutingService()
                    candidate = route()
                    result["paths"]["route_evaluation"] = measure(
                        lambda: router.decide(
                            "NVDA", "50", [candidate], mode="DEMO", now=candidate.price_timestamp
                        )
                    )
                    portfolio, _, _ = setup()
                    try:
                        result["paths"]["portfolio_evaluation"] = measure(
                            lambda: evaluate(portfolio, persist=False)
                        )
                    finally:
                        portfolio.store.close()
                        portfolio.positions.store.close()
                        portfolio.positions.execution.store.close()
                    for size in (10, 25, 50, 100):
                        dataset = universe(snapshot(), size, price_changes=True)

                        def run(dataset=dataset, size=size):
                            output = scan(dataset, request())
                            assert output.universe_count == size
                            assert not output.execution_ready and not output.transaction_broadcast
                            assert output.opportunity_gate == "BLOCKED_BY_TRUST"

                        result["universes"][str(size)] = measure(run)
        finally:
            if original is None:
                os.environ.pop("PARITY_PHASE15_DIR", None)
            else:
                os.environ["PARITY_PHASE15_DIR"] = original
    args.evidence.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
