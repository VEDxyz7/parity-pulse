"""Typed startup configuration; live execution requires an explicit, capped, multi-flag opt-in."""

from decimal import Decimal
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
    postopen_exit_minutes: int = Field(default=10, ge=1, le=120)
    # Live rebalance execution: every flag checked in non_live_only must agree before any order.
    live_max_notional_usd: Decimal | None = Field(default=None, gt=0, le=1000)
    live_max_slippage_bps: int = Field(default=100, ge=1, le=500)
    trust_required_for_rebalance: bool = True
    equity_reference_source: Literal["MASSIVE", "BINANCE_PERP_INDEX"] = "MASSIVE"
    # POSITIONS: Phase 10 journal is the holdings authority. WALLET: on-chain balances are.
    portfolio_inventory: Literal["POSITIONS", "WALLET"] = "POSITIONS"
    live_wallet_address: str | None = Field(default=None, pattern=r"^0x[0-9a-fA-F]{40}$")
    live_signer: Literal["LOCAL_KEY", "AGENTIC_WALLET", "ALTANA"] = "LOCAL_KEY"
    altana_sidecar_url: str = Field(default="http://127.0.0.1:8787", pattern=r"^http://127\.0\.0\.1:")
    sidecar_token: SecretStr | None = Field(default=None, exclude=True, repr=False)
    live_signer_private_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    bsc_rpc_url: str = Field(default="https://bsc-dataseed.bnbchain.org", pattern=r"^https://")

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
        "trust_required_for_rebalance",
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
        "live_signer_private_key",
        "sidecar_token",
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

    @field_validator("postopen_exit_minutes", mode="before")
    @classmethod
    def exact_exit_minutes(cls, value):
        if isinstance(value, (float, bool)):
            raise ValueError("Exit minutes must be an integer configuration value")
        return value

    @model_validator(mode="after")
    def non_live_only(self) -> "Settings":
        if (
            self.runtime_mode == "LIVE"
            and self.app_env == "production"
            and make_url(self.database_url).database == ":memory:"
        ):
            raise ValueError("Production canonical lifecycle requires durable SQLite storage")
        if self.llm_enabled and not (self.llm_provider and self.llm_model and self.llm_base_url):
            raise ValueError("Enabled LLM requires explicit provider/model/base URL")
        if self.runtime_mode == "DEMO" and self.data_mode != "DEMO":
            raise ValueError("DEMO sandbox requires explicit DEMO data mode")
        live = self.execution_mode == "LIVE"
        if (live or self.live_trading_enabled or self.approval_mode != "PROPOSE_ONLY") and not (
            live
            and self.live_trading_enabled
            and self.runtime_mode == "LIVE"
            and self.data_mode == "LIVE_READ_ONLY"
            and self.live_max_notional_usd is not None
        ):
            raise ValueError(
                "LIVE execution requires EXECUTION_MODE=LIVE, LIVE_TRADING_ENABLED=true, "
                "RUNTIME_MODE=LIVE, DATA_MODE=LIVE_READ_ONLY and LIVE_MAX_NOTIONAL_USD"
            )
        if not self.require_simulation:
            raise ValueError("Simulation cannot be disabled")
        if live and self.portfolio_inventory != "WALLET":
            raise ValueError("LIVE execution is wallet-inventory rebalancing only")
        if live and self.live_signer == "LOCAL_KEY" and self.live_signer_private_key is None:
            raise ValueError("LIVE LOCAL_KEY signer requires LIVE_SIGNER_PRIVATE_KEY")
        if live and self.live_signer == "ALTANA" and self.sidecar_token is None:
            raise ValueError("LIVE ALTANA signer requires SIDECAR_TOKEN")
        if self.portfolio_inventory == "WALLET" and self.data_mode != "LIVE_READ_ONLY":
            raise ValueError("Wallet inventory requires LIVE_READ_ONLY data")
        return self

    @property
    def live_execution(self) -> bool:
        return self.execution_mode == "LIVE" and self.live_trading_enabled

    def redaction_values(self) -> tuple[str, ...]:
        """Only for the log redactor. Never serialize this return value."""
        values = (
            self.binance_web3_api_key,
            self.binance_web3_secret_key,
            self.massive_api_key,
            self.llm_api_key,
            self.live_signer_private_key,
            self.sidecar_token,
        )
        return tuple(value.get_secret_value() for value in values if value is not None)
