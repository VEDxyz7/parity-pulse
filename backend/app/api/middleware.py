import logging
from time import perf_counter
from uuid import UUID, uuid4

from app.utils.logging import correlation_id_context, request_id_context

logger = logging.getLogger("parity.request")


def canonical_id(value: str | None) -> str:
    try:
        return str(UUID(value)) if value else str(uuid4())
    except (ValueError, AttributeError):
        return str(uuid4())


class RequestContextMiddleware:
    def __init__(self, app, run_id: str):
        self.app, self.run_id = app, run_id

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        correlation_id = canonical_id(headers.get(b"x-correlation-id", b"").decode("latin-1"))
        request_id = str(uuid4())  # Never trust a client-supplied request ID.
        scope.setdefault("state", {}).update(
            request_id=request_id,
            correlation_id=correlation_id,
            run_id=self.run_id,
        )
        tokens = (request_id_context.set(request_id), correlation_id_context.set(correlation_id))
        started, status = perf_counter(), 500

        async def send_with_ids(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                id_headers = {b"x-request-id", b"x-correlation-id", b"x-run-id"}
                existing = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() not in id_headers
                ]
                message["headers"] = existing + [
                    (b"x-request-id", request_id.encode()),
                    (b"x-correlation-id", correlation_id.encode()),
                    (b"x-run-id", self.run_id.encode()),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_ids)
        finally:
            route = getattr(scope.get("route"), "path", "unmatched")
            logger.info(
                "REQUEST_COMPLETED",
                extra={
                    "event_fields": {
                        "run_id": self.run_id,
                        "method": scope["method"],
                        "route": route,
                        "status_code": status,
                        "duration_ms": round((perf_counter() - started) * 1000, 2),
                    }
                },
            )
            request_id_context.reset(tokens[0])
            correlation_id_context.reset(tokens[1])
