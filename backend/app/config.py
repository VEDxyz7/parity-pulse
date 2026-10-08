"""Typed startup configuration; live execution remains unavailable in every runtime."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
        frozen=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    runtime_mode: Literal["LIVE", "DEMO"] = "LIVE"
    data_mode: Literal["DEMO", "LIVE_READ_ONLY"] = "DEMO"
    execution_mode: Literal["DRY_RUN", "LIVE"] = "DRY_RUN"
    approval_mode: Literal["PROPOSE_ONLY", "AUTONOMOUS"] = "PROPOSE_ONLY"
    live_trading_enabled: bool = False
    require_simulation: bool = True
    database_url: str = f"sqlite:///{ROOT_DIR / 'data' / 'parity-pulse.db'}"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    binance_web3_api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    binance_web3_secret_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    massive_data_quality: Literal["UNKNOWN", "DELAYED", "REALTIME"] = "UNKNOWN"
    massive_api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    llm_api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    llm_enabled: bool = False
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = Field(default=None, exclude=True, repr=False)
    llm_timeout_seconds: int = Field(default=5, ge=1, le=30)
    llm_max_output_bytes: int = Field(default=50000, ge=1024, le=50000)
    llm_max_output_tokens: int = Field(default=4096, ge=128, le=8192)
    llm_structured_output: bool = True

    @field_validator(
        "live_trading_enabled",
        "require_simulation",
        "llm_enabled",
        "llm_structured_output",
        mode="before",
    )
    @classmethod
    def explicit_boolean(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        raise ValueError("Boolean settings must be true or false")

    @field_validator(
        "binance_web3_api_key",
        "binance_web3_secret_key",
        "massive_api_key",
        "llm_api_key",
        mode="before",
    )
    @classmethod
    def empty_secret(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("database_url")
    @classmethod
    def sqlite_only(cls, value: str) -> str:
        try:
            url = make_url(value)
        except Exception:
            raise ValueError("A valid SQLite database URL is required") from None
        if (
            url.drivername != "sqlite"
            or url.host
            or url.username
            or url.password
            or url.query
            or not url.database
        ):
            raise ValueError("Phase 1 supports local SQLite only, without URL credentials/options")
        return value

    @model_validator(mode="after")
    def non_live_only(self) -> "Settings":
        if self.llm_enabled and not (self.llm_provider and self.llm_model and self.llm_base_url):
            raise ValueError("Enabled LLM requires explicit provider/model/base URL")
        if self.runtime_mode == "DEMO" and self.data_mode != "DEMO":
            raise ValueError("DEMO sandbox requires explicit DEMO data mode")
        if self.execution_mode != "DRY_RUN" or self.live_trading_enabled:
            raise ValueError("LIVE execution is blocked in Phase 1")
        if self.approval_mode != "PROPOSE_ONLY":
            raise ValueError("Phase 1 requires PROPOSE_ONLY")
        if not self.require_simulation:
            raise ValueError("Simulation cannot be disabled")
        return self

    def redaction_values(self) -> tuple[str, ...]:
        """Only for the log redactor. Never serialize this return value."""
        values = (
            self.binance_web3_api_key,
            self.binance_web3_secret_key,
            self.massive_api_key,
            self.llm_api_key,
        )
        return tuple(value.get_secret_value() for value in values if value is not None)
