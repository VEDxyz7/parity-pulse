"""Bounded configurable Chat Completions protocol transport; interpretation only.

No implicit provider/model, hidden HTTP retries, tools, redirects or raw-error logging.
The orchestrator alone owns retries and the five-generation budget.
"""

import asyncio
import json
from urllib.parse import urlsplit

import httpx

from app.agents.provider import LLMConfiguration, StructuredLLMProvider
from app.clients.common import unique_object


class LLMUnavailable(RuntimeError):
    """Sanitized capability error; never includes URLs, response bodies or credentials."""


class ChatCompletionsTransport:
    retry_cap = 0

    def __init__(self, configuration, *, http=None):
        self.configuration = configuration
        parsed = urlsplit(configuration.base_url or "")
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (
                configuration.api_key
                and configuration.api_key.get_secret_value() in configuration.base_url
            )
        ):
            raise ValueError("Explicit credential-free HTTPS LLM base URL required")
        self.url = configuration.base_url.rstrip("/") + "/chat/completions"
        self.http = http or httpx.AsyncClient(
            timeout=configuration.timeout_seconds, follow_redirects=False, trust_env=False
        )

    async def __call__(self, request):
        c = self.configuration
        if request.provider != c.provider or request.model != c.model:
            raise LLMUnavailable("LLM_CONFIGURATION_MISMATCH")
        headers = {"Content-Type": "application/json"}
        if c.api_key is not None:
            headers["Authorization"] = "Bearer " + c.api_key.get_secret_value()
        body = {
            "model": c.model,
            "stream": False,
            "max_tokens": c.max_output_tokens,
            "messages": [
                {"role": "system", "content": request.instruction},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "evidence": json.loads(request.structured_evidence_json),
                            "authoritative_fields": json.loads(request.validated_response_json),
                            "allowed_summary_claims": json.loads(request.allowed_claims_json),
                        }
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "parity_agent",
                    "schema": json.loads(request.response_schema_json),
                    "strict": True,
                },
            }
            if c.structured_output
            else {"type": "json_object"},
        }
        # Inbound/outbound sizes are bounded independently of server token accounting.
        if len(json.dumps(body).encode()) > 200000:
            raise LLMUnavailable("LLM_REQUEST_TOO_LARGE")
        try:
            async with asyncio.timeout(c.timeout_seconds):
                async with self.http.stream(
                    "POST",
                    self.url,
                    json=body,
                    headers=headers,
                    timeout=c.timeout_seconds,
                ) as response:
                    if response.status_code != 200:
                        raise LLMUnavailable("LLM_HTTP_FAILURE")
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > c.max_output_bytes + 8192:
                            raise LLMUnavailable("LLM_RESPONSE_TOO_LARGE")
                    value = json.loads(raw, object_pairs_hook=unique_object)
                    choices = value["choices"]
                    if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
                        raise LLMUnavailable("LLM_INCOMPLETE_RESPONSE")
                    message = choices[0]["message"]
                    content = message["content"]
                    if (
                        message.get("tool_calls")
                        or message.get("refusal")
                        or type(content) is not str
                        or not content.strip()
                        or len(content.encode()) > c.max_output_bytes
                        or (c.api_key and c.api_key.get_secret_value() in content)
                    ):
                        raise LLMUnavailable("LLM_UNSAFE_OR_EMPTY_RESPONSE")
                    return content
        except TimeoutError:
            raise TimeoutError("LLM_TIMEOUT") from None
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError, AttributeError):
            raise LLMUnavailable("LLM_TRANSPORT_OR_SCHEMA_UNAVAILABLE") from None

    async def close(self):
        await self.http.aclose()


def configured_provider(settings):
    """No network during construction; explicit opt-in, no model or vendor inference."""
    if not settings.llm_enabled:
        return None, None
    config = LLMConfiguration(
        provider=settings.llm_provider,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        max_output_bytes=settings.llm_max_output_bytes,
        max_output_tokens=settings.llm_max_output_tokens,
        structured_output=settings.llm_structured_output,
    )
    transport = ChatCompletionsTransport(config)
    return StructuredLLMProvider.from_configuration(config, transport=transport), transport
