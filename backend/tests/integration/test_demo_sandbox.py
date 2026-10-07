"""Synthetic sandbox exercises the actual Trust engine, never the configured history."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from app.config import Settings
from app.main import create_app
from app.models.demo_sandbox import DemoTrustDataset
from app.services.demo_sandbox import DemoTrustSandbox
from app.services.trust import TrustService
from app.services.trust_classifier import TrustClassifier

CASES = [
    ("steady", "NORMAL"),
    ("thin-move", "LIKELY_NOISE"),
    ("supported-move", "LIKELY_INFORMATION"),
]
IDS = dict(run_id="test-demo", request_id="test-demo", correlation_id="test-demo")


@pytest.fixture
def sandbox_app(tmp_path):
    return create_app(
        Settings(
            _env_file=None,
            app_env="test",
            runtime_mode="DEMO",
            database_url=f"sqlite:///{tmp_path}/must-not-be-opened.db",
        )
    )


@pytest.mark.parametrize("identifier,expected", CASES)
def test_synthetic_scenarios_use_existing_assess_features_and_classifier(
    sandbox_app, monkeypatch, identifier, expected
):
    original_assess = TrustService.assess
    original_classify = TrustClassifier.classify
    entered = []
    inputs = []

    def assess(self, *args, **kwargs):
        entered.append(self)
        return original_assess(self, *args, **kwargs)

    def classify(self, **kwargs):
        inputs.append(kwargs)
        return original_classify(self, **kwargs)

    monkeypatch.setattr(TrustService, "assess", assess)
    monkeypatch.setattr(TrustClassifier, "classify", classify)
    with TestClient(sandbox_app) as client:
        response = client.get("/api/demo/trust/scenarios/" + identifier)
        assert response.status_code == 200
        result = response.json()
        row = result["assessment"]["representations"][0]
        assert len(entered) == len(inputs) == 1
        assert row["classification"] == expected
        assert row["baseline"]["sample_count"] == 30
        assert row["analogues"]["retrieved_sample_count"] == 3
        assert row["evidence_quality"] == "SYNTHETIC_DEMO" and row["confidence"] == "LOW"
        assert inputs[0]["features"].deviation == (
            inputs[0]["features"].effective_price_per_share_usd / 100 - 1
        )
        assert row["features"]["persistence_seconds"] == (
            "0" if identifier == "thin-move" else "900"
        )
        assert result["dataset_type"] == "DEMO_FIXTURE" and result["synthetic"] is True
        assert result["production_eligible"] is False and result["runtime_mode"] == "DEMO"
        assert len(result["fixture_sha256"]) == 64 and result["fixture_episode_count"] == 30
        assessment = result["assessment"]
        assert assessment["trust_gate"] == "BLOCKED"
        assert assessment["execution_ready"] is assessment["transaction_broadcast"] is False
        assert (
            assessment["live_trading_enabled"] is False and assessment["require_simulation"] is True
        )
        assert (
            assessment["execution_mode"] == "DRY_RUN"
            and assessment["approval_mode"] == "PROPOSE_ONLY"
        )
        for name in ("run_id", "request_id", "correlation_id"):
            assert assessment[name] == response.headers["x-" + name.replace("_", "-")]
        assert result["production_gates"]["TRUST_GATE"] == "BLOCKED"
        assert result["production_gates"]["OPPORTUNITY_GATE"] == "BLOCKED_BY_TRUST"
        assert all(v == "BLOCKED" for k, v in result["production_gates"].items() if "LIVE" in k)


def test_demo_never_opens_configured_database_or_calls_real_providers(sandbox_app, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No real provider or external transport allowed")

    monkeypatch.setattr("app.clients.binance_web3.BinanceWeb3Client.__init__", forbidden)
    monkeypatch.setattr("app.clients.massive.MassiveClient.__init__", forbidden)
    monkeypatch.setattr("httpx.HTTPTransport.handle_request", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)
    with TestClient(sandbox_app) as client:
        assert client.get("/api/system-status").json()["runtime_mode"] == "DEMO"
        assert client.get("/api/health").status_code == 200
        for identifier, _ in CASES:
            assert client.get("/api/demo/trust/scenarios/" + identifier).status_code == 200
        assert sandbox_app.state.database.engine.url.database == ":memory:"
    configured = Path(sandbox_app.state.settings.database_url.removeprefix("sqlite:///"))
    assert not configured.exists()


def test_existing_configured_database_bytes_and_history_remain_untouched(tmp_path):
    # A sentinel need not even be SQLite: sandbox must never open it.
    protected = tmp_path / "protected.db"
    protected.write_bytes(b"existing production historical database sentinel")
    before = protected.read_bytes()
    app = create_app(
        Settings(_env_file=None, runtime_mode="DEMO", database_url=f"sqlite:///{protected}")
    )
    with TestClient(app) as client:
        with app.state.database.engine.connect() as connection:
            before_counts = {
                table: connection.execute(text("SELECT count(*) FROM " + table)).scalar()
                for table in ("trust_samples", "trust_episodes", "trust_assessments")
            }
        for identifier, _ in CASES:
            client.get("/api/demo/trust/scenarios/" + identifier).raise_for_status()
        with app.state.database.engine.connect() as connection:
            after_counts = {
                table: connection.execute(text("SELECT count(*) FROM " + table)).scalar()
                for table in before_counts
            }
        assert before_counts == after_counts == dict.fromkeys(before_counts, 0)
    assert protected.read_bytes() == before


def test_each_request_has_its_own_history_and_is_deterministic():
    sandbox = DemoTrustSandbox()
    first = sandbox.assess("thin-move", **IDS)
    sandbox.assess("supported-move", **IDS)
    second = sandbox.assess("thin-move", **IDS)
    assert first.assessment.model_dump(exclude={"assessment_id"}) == second.assessment.model_dump(
        exclude={"assessment_id"}
    )
    assert first.fixture_sha256 == second.fixture_sha256


def test_scenario_name_cannot_determine_classification():
    sandbox = DemoTrustSandbox()
    # Keep the noise selection and its displayed label; replace only the evidence.
    altered = sandbox.datasets["steady"].model_dump()
    altered.update(scenario_id="thin-move", title="LIKELY NOISE")
    sandbox.datasets["thin-move"] = DemoTrustDataset.model_validate(altered)
    result = sandbox.assess("thin-move", **IDS)
    assert result.title == "LIKELY NOISE"
    assert result.assessment.representations[0].classification == "NORMAL"


def test_classifier_return_is_used_and_missing_liquidity_fails_closed(monkeypatch):
    sandbox = DemoTrustSandbox()
    altered = sandbox.datasets["supported-move"].model_dump()
    altered["price"]["record"]["provider_metadata"].pop("liquidity")
    sandbox.datasets["supported-move"] = DemoTrustDataset.model_validate(altered)
    result = sandbox.assess("supported-move", **IDS)
    assert result.assessment.representations[0].classification == "INSUFFICIENT_EVIDENCE"
    assert result.assessment.representations[0].features is None
    assert result.assessment.trust_gate == "BLOCKED"
    monkeypatch.setattr(
        TrustClassifier,
        "classify",
        lambda *args, **kwargs: ("INSUFFICIENT_EVIDENCE", None, ["TEST_ENGINE_RETURN"]),
    )
    engine_return = DemoTrustSandbox().assess("steady", **IDS)
    assert engine_return.assessment.representations[0].classification == "INSUFFICIENT_EVIDENCE"
    assert "TEST_ENGINE_RETURN" in engine_return.assessment.representations[0].reason_codes


@pytest.mark.parametrize("identifier,_expected", CASES)
def test_fixture_records_all_marked_synthetic_and_no_final_label(identifier, _expected):
    from app.config import ROOT_DIR

    raw = json.loads((ROOT_DIR / f"data/demo/trust-sandbox/{identifier}.json").read_text())
    wrappers = [raw] + [raw[k] for k in ("asset", "issuer", "token", "price", "equity")]
    wrappers += raw["baseline_episodes"] + raw["preceding_samples"] + raw["news"]
    for record in wrappers:
        assert record["dataset_type"] == "DEMO_FIXTURE" and record["synthetic"] is True
        assert record["production_eligible"] is False
    assert '"classification"' not in json.dumps(raw)
    parsed = DemoTrustDataset.model_validate(raw)
    assert all(e.record.evidence_kind == "SYNTHETIC_TEST" for e in parsed.baseline_episodes)


@pytest.mark.parametrize(
    "mutation", ["missing-marker", "live-record", "real-contract", "local-episode"]
)
def test_mislabeled_or_contaminated_fixture_rejected(mutation):
    raw = DemoTrustSandbox().datasets["steady"].model_dump()
    if mutation == "missing-marker":
        raw["baseline_episodes"][0].pop("production_eligible")
    elif mutation == "live-record":
        raw["equity"]["record"]["data_mode"] = "LIVE"
    elif mutation == "real-contract":
        raw["token"]["record"]["chain_id"] = "56"
        raw["token"]["record"]["contract"] = "0x" + "1" * 40
    else:
        raw["baseline_episodes"][0]["record"]["evidence_kind"] = "LOCAL_OBSERVATIONS"
    with pytest.raises(ValidationError):
        DemoTrustDataset.model_validate(raw)


def test_live_runtime_keeps_legacy_response_and_does_not_load_sandbox(settings, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("LIVE runtime must not load sandbox fixtures")

    monkeypatch.setattr("app.main.DemoTrustSandbox", forbidden)
    app = create_app(settings)
    assert settings.runtime_mode == "LIVE"
    with TestClient(app) as client:
        status = client.get("/api/system-status").json()
        assert "runtime_mode" not in status
        assert set(status) == {
            "environment",
            "data_mode",
            "execution_mode",
            "approval_mode",
            "live_trading_enabled",
            "require_simulation",
            "database_status",
            "service_version",
            "phase",
            "run_id",
            "gates",
            "demo_fixture",
        }
        assert app.state.demo_sandbox is None
        assert app.state.database.engine.url.database != ":memory:"
        assert client.get("/api/demo/trust/scenarios").status_code == 404
        result = client.get("/api/assets/NVDA/trust").json()
        assert result["representations"][0]["classification"] == "INSUFFICIENT_EVIDENCE"
        assert result["representations"][0]["baseline"]["sample_count"] == 0
        assert result["trust_gate"] == "BLOCKED"


@pytest.mark.parametrize(
    "override",
    [{"runtime_mode": "REPLAY"}, {"runtime_mode": "DEMO", "data_mode": "LIVE_READ_ONLY"}],
)
def test_runtime_invalid_or_mixed_provider_mode_rejected(override):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **override)


def test_catalog_and_api_fail_closed_for_unknown_scenario_queries_and_posts(sandbox_app):
    with TestClient(sandbox_app) as client:
        catalog = client.get("/api/demo/trust/scenarios").json()
        assert [s["scenario_id"] for s in catalog["scenarios"]] == [name for name, _ in CASES]
        assert catalog["synthetic"] is True and catalog["production_eligible"] is False
        assert client.get("/api/demo/trust/scenarios/unknown").status_code == 422
        assert client.get("/api/demo/trust/scenarios/steady?execute=true").status_code == 404
        assert (
            client.post("/api/demo/trust/scenarios/steady", json={"execute": True}).status_code
            == 405
        )
        assert client.post("/api/demo/trust/scenarios/steady/broadcast").status_code == 404
