import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


def test_safe_defaults_need_no_credentials():
    settings = Settings(_env_file=None)
    assert settings.data_mode == "DEMO"
    assert settings.execution_mode == "DRY_RUN"
    assert settings.approval_mode == "PROPOSE_ONLY"
    assert settings.live_trading_enabled is False
    assert settings.require_simulation is True
    assert settings.binance_web3_api_key is None


def test_local_environment_file_and_process_precedence(tmp_path, monkeypatch):
    env = tmp_path / "configuration.env"
    env.write_text("APP_ENV=test\nDATA_MODE=LIVE_READ_ONLY\nLOG_LEVEL=WARNING\n")
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    settings = Settings(_env_file=env)
    assert settings.app_env == "test" and settings.data_mode == "LIVE_READ_ONLY"
    assert settings.log_level == "ERROR"


@pytest.mark.parametrize(
    "override",
    [
        {"execution_mode": "LIVE", "live_trading_enabled": False},
        {"execution_mode": "LIVE", "live_trading_enabled": True},
        {"live_trading_enabled": True},
        {"require_simulation": False},
        {"approval_mode": "AUTONOMOUS"},
        {"data_mode": "LIVE"},
        {"data_mode": "BAD"},
        {"log_level": "VERBOSE"},
        {"app_env": "unrecognized"},
        {"require_simulation": "maybe"},
        {"live_trading_enabled": "yes"},
        {"database_url": "postgresql://user:password@remote/db"},
        {"database_url": "not-a-url"},
        {"database_url": "sqlite:///x.db?mode=ro"},
    ],
)
def test_unsafe_or_malformed_configuration_rejected(override):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **override)


def test_unsafe_environment_fails_app_factory_without_values(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "LIVE")
    monkeypatch.setenv("BINANCE_WEB3_SECRET_KEY", "synthetic-credential-must-not-appear")
    with pytest.raises(RuntimeError, match="startup refused") as caught:
        create_app()
    assert "synthetic-credential" not in str(caught.value)


def test_secret_fields_excluded_from_serialization_and_repr():
    secret = "synthetic-credential-for-config-test"
    settings = Settings(_env_file=None, binance_web3_secret_key=secret, llm_api_key=secret)
    assert secret not in repr(settings)
    assert secret not in settings.model_dump_json()
    assert "binance_web3_secret_key" not in settings.model_dump()


def test_settings_cannot_be_mutated_or_injected_to_bypass_safety():
    settings = Settings(_env_file=None)
    with pytest.raises(ValidationError):
        settings.live_trading_enabled = True
    unsafe = Settings.model_construct(execution_mode="LIVE", live_trading_enabled=True)
    with pytest.raises(RuntimeError, match="startup refused"):
        create_app(unsafe)
