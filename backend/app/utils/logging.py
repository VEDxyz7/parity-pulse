"""JSON logs with safe metadata and no request bodies, headers or query strings."""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
correlation_id_context: ContextVar[str | None] = ContextVar("correlation_id", default=None)
SAFE_FIELDS = {
    "run_id",
    "request_id",
    "correlation_id",
    "method",
    "route",
    "status_code",
    "duration_ms",
    "database_status",
    "error_type",
    "service_version",
    "provider",
    "endpoint",
    "assessment_id",
    "trust_status",
    "proposal_id",
    "proposal_status",
    "data_mode",
    "decision_id",
    "universe_count",
    "eligible_count",
    "rejected_count",
    "action",
    "agent_calls",
    "llm_calls",
}


class JsonFormatter(logging.Formatter):
    def __init__(self, secrets: tuple[str, ...] = ()):
        super().__init__()
        self.secrets = secrets

    def redact(self, value: str) -> str:
        for secret in self.secrets:
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", value)
        return re.sub(
            r"(?i)(api[_-]?key|secret|password|authorization|private[_-]?key|seed)\s*[:=]\s*\S+",
            r"\1=[REDACTED]",
            value,
        )

    def format(self, record: logging.LogRecord) -> str:
        output = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "event": self.redact(record.getMessage()),
            "request_id": request_id_context.get(),
            "correlation_id": correlation_id_context.get(),
        }
        for key, value in getattr(record, "event_fields", {}).items():
            if key in SAFE_FIELDS and (value is None or isinstance(value, (str, int, float, bool))):
                output[key] = self.redact(value) if isinstance(value, str) else value
        if record.exc_info:
            output["error_type"] = record.exc_info[0].__name__
        return json.dumps(output, separators=(",", ":"))


def configure_logging(level: str, secrets: tuple[str, ...]) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(secrets))
    logging.basicConfig(level=level, handlers=[handler], force=True)
    for name in ("uvicorn", "uvicorn.error"):
        server_logger = logging.getLogger(name)
        server_logger.handlers.clear()
        server_logger.propagate = True
    # Uvicorn access logs include untrusted raw URLs; use the request middleware instead.
    logging.getLogger("uvicorn.access").disabled = True
