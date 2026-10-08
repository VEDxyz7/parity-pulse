"""Official SDK stdio transport forwarding only seven bounded tools to the UI backend.

No database, wallet session, provider credentials or financial engine in this process.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from app.models.agent_api import INPUTS, ToolError, ToolResult
from app.services.agent_api import inventory
from app.services.audit import safe_record


def create_server(client):
    async def tools(_context, params):
        if params and params.cursor:
            raise ValueError("Unknown tool catalog cursor")
        return types.ListToolsResult(
            tools=[types.Tool.model_validate(t) for t in inventory()["tools"]]
        )

    async def call(_context, params):
        now = datetime.now(UTC)
        ids = [uuid4() for _ in range(3)]
        # Unknown names are refused by the SDK input schema resolver before HTTP dispatch.
        if params.name not in INPUTS:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text='{"error":"UNKNOWN_TOOL"}')],
                is_error=True,
            )
        try:
            response = await client.post(
                f"/api/agent/tools/{params.name}",
                json=params.arguments or {},
                headers={"X-Correlation-ID": str(ids[0])},
            )
            response.raise_for_status()
            result = ToolResult.model_validate_json(response.content)
            if result.tool != params.name:
                raise ValueError("Mismatched tool response")
            safe_record(result)
        except (httpx.HTTPError, ValueError, TypeError):
            # No automatic retries. Lost response might already have persisted a proposal.
            result = ToolResult(
                tool=params.name,
                status="UNAVAILABLE",
                request_id=ids[1],
                correlation_id=ids[0],
                invocation_id=ids[2],
                run_id="MCP_BRIDGE",
                generated_at=now,
                as_of=now,
                data_mode="UNKNOWN",
                data_quality="UNKNOWN",
                source="MCP_TRANSPORT",
                error=ToolError(
                    code="DATA_UNAVAILABLE",
                    category="DATA_PROVIDER",
                    retry_policy="DO_NOT_RESUBMIT_WITH_NEW_KEY",
                ),
                reason_codes=("BACKEND_RESPONSE_UNAVAILABLE",),
            )
        payload = result.model_dump(mode="json")
        return types.CallToolResult(
            content=[
                types.TextContent(type="text", text=json.dumps(payload, separators=(",", ":")))
            ],
            structured_content=payload,
            is_error=result.error is not None,
        )

    return Server(
        "parity-pulse",
        version="agent-api-1",
        on_list_tools=tools,
        on_call_tool=call,
        get_tool_input_schema=lambda name: (
            INPUTS[name].model_json_schema() if name in INPUTS else None
        ),
    )


async def serve(port):
    # Fixed loopback origin, no caller-supplied URL, redirects, proxies or credential forwarding.
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{port}", timeout=40, follow_redirects=False, trust_env=False
    ) as client:
        server = create_server(client)
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())


def main():
    parser = argparse.ArgumentParser(description="Parity Pulse bounded MCP stdio bridge")
    parser.add_argument(
        "--port", type=int, default=8000, choices=range(1024, 65536), metavar="BACKEND_PORT"
    )
    asyncio.run(serve(parser.parse_args().port))


if __name__ == "__main__":
    main()
