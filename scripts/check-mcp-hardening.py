"""Exercise the existing stdio bridge against the disposable browser fixture only."""

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from mcp import Client  # noqa: E402
from mcp.client.stdio import StdioServerParameters  # noqa: E402

from app.models.agent_api import INPUTS, ToolResult  # noqa: E402


async def main():
    directory = Path(os.environ["PARITY_PHASE15_DIR"])
    # This diagnostic deliberately cannot target an arbitrary user/production server.
    safe = {k: os.environ[k] for k in ("PATH", "TMPDIR", "LANG", "LC_ALL") if k in os.environ}
    safe["PYTHONPATH"] = str(ROOT / "backend")
    command = ["-m", "app.mcp_server", "--port", "8056"]
    params = StdioServerParameters(command=str(ROOT / ".venv/bin/python"), args=command, env=safe)
    calls = []
    async with Client(params, read_timeout_seconds=40) as client:
        catalog = await client.list_tools()
        assert {t.name for t in catalog.tools} == set(INPUTS)
        buy = dict(
            ticker="NVDA", amount_usd="50", risk_budget_usd="5", idempotency_key=str(uuid4())
        )
        cases = [
            ("buy_stock_exposure", buy),
            (
                "find_opportunity",
                dict(
                    budget_usd="100",
                    risk_budget_usd="10",
                    time_window="PRE_OPEN",
                    idempotency_key=str(uuid4()),
                ),
            ),
            ("compare_stock_tokens", dict(ticker="NVDA")),
            ("get_stock_trust", dict(ticker="NVDA")),
            ("get_route", dict(ticker="NVDA", amount_usd="50")),
            ("get_portfolio", {}),
            ("get_autopilot_status", {}),
            ("buy_stock_exposure", buy),
        ]
        for name, args in cases:
            response = await client.call_tool(name, args)
            value = ToolResult.model_validate(response.structured_content)
            assert value.tool == name and value.error is None
            assert not value.execution_ready and not value.transaction_broadcast
            assert value.gates.TRUST_GATE == "BLOCKED"
            assert value.gates.OPPORTUNITY_GATE == "BLOCKED_BY_TRUST"
            calls.append(
                dict(
                    tool=name,
                    status=value.status,
                    decision_id=value.decision_id,
                    replayed=value.replayed,
                )
            )
        assert calls[-1]["replayed"] and calls[0]["decision_id"] == calls[-1]["decision_id"]
    (directory / "mcp-evidence.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "transport": "OFFICIAL_SDK_STDIO_SUBPROCESS",
                "synthetic": True,
                "live_execution_calls": 0,
                "calls": calls,
            },
            indent=2,
        )
        + "\n"
    )
    print("PASS: actual stdio subprocess, seven tools and original-decision retry")


if __name__ == "__main__":
    asyncio.run(main())
