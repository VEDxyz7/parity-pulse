"""One-shot read-only lifecycle recovery. Suitable for a once-per-minute host scheduler.

Run from the repository root: .venv/bin/python scripts/monitor-positions.py --limit 100
Never prepares quotes, submits orders, or invokes wallet commands.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.main import create_app  # noqa: E402


async def run(limit):
    app = create_app(position_recovery_limit=limit)
    async with app.router.lifespan_context(app):
        service = app.state.positions
        # Lifespan already made one bounded recovery pass; do not immediately poll twice.
        results = app.state.position_recovery_results
        print(
            json.dumps(
                {
                    "mode": service.mode,
                    "processed": len(results),
                    "recovery_complete": service.recovery_complete,
                    "positions": [
                        {"position_id": str(p.position_id), "state": p.state} for p in results
                    ],
                    "broadcast": False,
                }
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, choices=range(1, 1001), default=100, metavar="1..1000")
    asyncio.run(run(parser.parse_args().limit))
