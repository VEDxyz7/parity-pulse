"""Single-user loopback tool interface. Public catalog contains schemas, never account data."""

import ipaddress
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.models.agent_api import ToolName, ToolResult
from app.services.agent_api import inventory

router = APIRouter(prefix="/api/agent", tags=["bounded non-executable agent tools"])


@router.get("/tools")
def catalog(request: Request):
    return {
        **inventory(),
        "ready": request.app.state.ready,
        "data_mode": request.app.state.settings.data_mode,
    }


def local_request(request):
    try:
        peer = request.client.host if request.client else ""
        if not ipaddress.ip_address(peer).is_loopback:
            return False
        # Do not trust X-Forwarded-For. Host/Origin prevent a remote site reaching loopback.
        host = request.url.hostname
        if host not in {"127.0.0.1", "localhost", "::1"}:
            return False
        if any(
            name in request.headers for name in ("forwarded", "x-forwarded-for", "x-forwarded-host")
        ):
            return False
        if "origin" in request.headers:
            origin = urlsplit(request.headers["origin"])
            if origin.scheme not in {"http", "https"} or origin.netloc != request.url.netloc:
                return False
        return (
            not request.query_params
            and request.headers.get("content-type", "").split(";")[0] == "application/json"
        )
    except (ValueError, AttributeError):
        return False


@router.post("/tools/{name}", response_model=ToolResult)
async def invoke(name: ToolName, request: Request):
    if not local_request(request):
        return JSONResponse({"error": {"code": "TOOL_ACCESS_DENIED"}}, status_code=403)
    try:
        # Bound bytes before JSON parsing; invalid body is never echoed or logged.
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 16384:
                raise ValueError("Tool request exceeds bound")
        import json

        arguments = json.loads(data)
        if not isinstance(arguments, dict):
            raise ValueError("Object required")
    except (ValueError, TypeError):
        arguments = None
    state = request.app.state
    result = await state.agent_api.call(
        name,
        arguments,
        request_id=request.state.request_id,
        correlation_id=request.state.correlation_id,
        run_id=state.run_id,
    )
    return result
