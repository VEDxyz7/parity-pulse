"""Actual bounded HTTP transport and app wiring; synthetic credentials, no remote calls."""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.agents.adapters import DemoEvidenceAdapter
from app.agents.memory import AgentStore
from app.agents.orchestrator import AgentOrchestrator
from app.agents.provider import LLMConfiguration, StructuredLLMProvider
from app.agents.schemas import AgentPolicy
from app.clients.llm import ChatCompletionsTransport, LLMUnavailable, configured_provider
from app.config import Settings
from app.main import create_app
from backend.tests.unit.test_agents import REQUEST

SENTINEL = "unit-test-llm-secret-never-persist"


class Wire:
    def __init__(self, variant="valid"):
        self.variant, self.calls = variant, []

    async def __call__(self, request):
        self.calls.append(request)
        body = json.loads(request.content)
        inputs = json.loads(body["messages"][1]["content"])
        value = inputs["authoritative_fields"]
        variant = self.variant
        if variant in ("429", "500"):
            return httpx.Response(int(variant), json={"error": SENTINEL})
        if variant == "unavailable":
            raise httpx.ConnectError(SENTINEL)
        if variant == "timeout":
            await asyncio.sleep(3)
        # A valid interpretation is intentionally not a byte-for-byte echo.
        value["reasoning_summary"] = inputs["allowed_summary_claims"][:1]
        if value["agent"] == "OPPORTUNITY":
            value["output"]["strengths"] = value["output"]["strengths"][:1]
        if variant == "missing":
            del value["decision_id"]
        elif variant == "ticker":
            value["output"]["views"][0]["ticker"] = "FAKE"
        elif variant == "numeric":
            value["output"]["views"][0]["deviation"] = "999"
        elif variant == "enum":
            value["status"] = "EXECUTE"
        elif variant == "contradiction":
            value["status"] = "ABSTAIN"
        elif variant == "correlation":
            value["correlation_id"] = "different-run"
        elif variant == "provenance":
            value["reasoning_summary"] = [
                {"evidence_ref": "invented", "conclusion": "SUPPORTS_ANALYSIS"}
            ]
        elif variant == "authority":
            value["execution_authorized"] = True
        content = json.dumps(value)
        if variant == "malformed":
            content = "{broken"
        elif variant == "empty":
            content = ""
        elif variant == "duplicate":
            content = '{"status":"OK",' + content[1:]
        elif variant == "oversized":
            content = "x" * 59000
        elif variant == "secret":
            content = SENTINEL
        message = {"content": content}
        if variant == "tool":
            message["tool_calls"] = [{"function": {"name": "execute"}}]
        if variant == "refusal":
            message["refusal"] = SENTINEL
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": message}]}
        )


def config(**kwargs):
    return LLMConfiguration(
        _env_file=None,
        provider="TEST_ONLY",
        model="bounded-v1",
        base_url="https://model.example/v1",
        api_key=SecretStr(SENTINEL),
        **kwargs,
    )


def provider(wire, **kwargs):
    c = config(**kwargs)
    transport = ChatCompletionsTransport(
        c, http=httpx.AsyncClient(transport=httpx.MockTransport(wire))
    )
    return StructuredLLMProvider.from_configuration(c, transport=transport), transport


def analyze(wire, **kwargs):
    async def run():
        p, transport = provider(wire, **kwargs)
        store = AgentStore()
        try:
            result = await AgentOrchestrator(
                store=store,
                provider=p,
                policy=AgentPolicy(timeout_seconds=1 if wire.variant == "timeout" else 5),
            ).analyze(REQUEST, DemoEvidenceAdapter().load("supported-move"))
            assert store.load_run(result.run_id, mode="DEMO") == result
            return result
        finally:
            store.close()
            await transport.close()

    return asyncio.run(run())


def test_valid_non_echo_interpretation_http_contract_preserves_facts_and_is_persisted():
    w = Wire()
    run = analyze(w)
    assert run.decision.decision == "BUY" and run.llm_calls == len(w.calls) == 5
    assert all(r.reasoning_summary for r in run.responses[1:])
    assert all(r.provider == "TEST_ONLY" and r.model == "bounded-v1" for r in run.responses[1:])
    assert not run.execution_authorized and not run.transaction_broadcast
    for request, response in zip(w.calls, run.responses[1:], strict=True):
        assert (
            request.method == "POST"
            and str(request.url) == "https://model.example/v1/chat/completions"
        )
        assert request.headers["Authorization"] == "Bearer " + SENTINEL
        body = json.loads(request.content)
        assert body["model"] == "bounded-v1" and body["stream"] is False
        assert body["max_tokens"] == 4096 and body["response_format"]["type"] == "json_schema"
        canonical = json.loads(body["messages"][1]["content"])["authoritative_fields"]
        assert response.confidence.model_dump(mode="json") == canonical["confidence"]
        assert response.evidence_refs == tuple(canonical["evidence_refs"])
        assert response.correlation_id == canonical["correlation_id"]
    assert SENTINEL not in run.model_dump_json()


@pytest.mark.parametrize(
    "variant",
    [
        "malformed",
        "missing",
        "ticker",
        "numeric",
        "enum",
        "contradiction",
        "correlation",
        "provenance",
        "authority",
        "empty",
        "duplicate",
        "429",
        "500",
        "unavailable",
        "oversized",
        "secret",
        "tool",
        "refusal",
    ],
)
def test_transport_or_strict_domain_failure_abstains_without_sensitive_persistence(variant, caplog):
    w = Wire(variant)
    run = analyze(w)
    assert run.decision.decision == "DEFER" and not run.execution_authorized
    assert run.responses[1].status == "UNAVAILABLE"
    assert run.llm_calls == len(w.calls) <= 2
    assert SENTINEL not in run.model_dump_json() and SENTINEL not in caplog.text


def test_timeout_has_no_hidden_retry_or_outstanding_generation():
    w = Wire("timeout")
    run = analyze(w, timeout_seconds=1)
    assert run.decision.decision == "DEFER" and run.llm_calls == len(w.calls) == 1
    assert run.calls[-1].status == "TIMEOUT"


def test_json_object_mode_still_enforces_local_strict_schema():
    w = Wire()
    assert analyze(w, structured_output=False).decision.decision == "BUY"
    assert json.loads(w.calls[0].content)["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    "url",
    [
        "http://model.example/v1",
        "https://user:password@model.example/v1",
        "https://model.example/v1?key=secret",
        "https://model.example/" + SENTINEL,
    ],
)
def test_credential_urls_and_non_https_rejected_before_transport(url):
    with pytest.raises(ValueError):
        ChatCompletionsTransport(config().model_copy(update={"base_url": url}))


def test_app_configured_transport_is_wired_into_existing_scan_and_closed(monkeypatch):
    w = Wire()
    created = []

    def construct(c):
        t = ChatCompletionsTransport(c, http=httpx.AsyncClient(transport=httpx.MockTransport(w)))
        created.append(t)
        return t

    monkeypatch.setattr("app.clients.llm.ChatCompletionsTransport", construct)
    settings = Settings(
        _env_file=None,
        app_env="test",
        runtime_mode="DEMO",
        data_mode="DEMO",
        database_url="sqlite:///:memory:",
        llm_enabled=True,
        llm_provider="TEST_ONLY",
        llm_model="bounded-v1",
        llm_base_url="https://model.example/v1",
        llm_api_key=SecretStr(SENTINEL),
    )
    app = create_app(settings)
    with TestClient(app) as web:
        result = web.post(
            "/api/opportunities/scan",
            json={
                "budget_usd": "60",
                "risk_budget_usd": "2",
                "time_window": "BEFORE_MONDAY",
                "demo_scenario": "supported-move",
            },
        )
        assert result.status_code == 200
        assert len(w.calls) == 5
        assert SENTINEL not in result.text
        assert (
            web.get("/api/system-status").json()["gates"]["AGENTIC_WALLET_LIVE_GATE"] == "BLOCKED"
        )
        assert web.post("/api/execution/submit", json={}).status_code == 404
    assert created[0].http.is_closed


def test_disabled_transport_retains_deterministic_fallback_without_any_network():
    s = Settings(_env_file=None, app_env="test", data_mode="DEMO")
    assert configured_provider(s) == (None, None)
    store = AgentStore()
    try:
        run = asyncio.run(
            AgentOrchestrator(store=store).analyze(
                REQUEST, DemoEvidenceAdapter().load("supported-move")
            )
        )
        assert run.decision.decision == "BUY" and run.llm_calls == 0
    finally:
        store.close()


def test_repeated_identical_interpretation_reuses_immutable_run_without_new_http_calls():
    async def probe():
        w = Wire()
        p, transport = provider(w)
        store = AgentStore()
        try:
            engine = AgentOrchestrator(store=store, provider=p)
            bundle = DemoEvidenceAdapter().load("supported-move")
            first = await engine.analyze(REQUEST, bundle)
            w.variant = "numeric"
            repeated = await engine.analyze(REQUEST, bundle)
            assert repeated == first and len(w.calls) == 5
            assert store.load_run(first.run_id, "DEMO") == first
        finally:
            store.close()
            await transport.close()

    asyncio.run(probe())


def test_sanitized_configuration_mismatch_cannot_send_a_request():
    from app.agents.provider import LLMRequest

    w = Wire()
    _, t = provider(w)
    request = LLMRequest(
        provider="OTHER",
        model="bounded-v1",
        agent="MARKET",
        instruction="",
        structured_evidence_json="{}",
        validated_response_json="{}",
        response_schema_json="{}",
    )

    async def probe():
        try:
            with pytest.raises(LLMUnavailable, match="LLM_CONFIGURATION_MISMATCH"):
                await t(request)
        finally:
            await t.close()

    asyncio.run(probe())
    assert not w.calls
