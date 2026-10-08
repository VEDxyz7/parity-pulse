"""Vendor-independent structured LLM boundary, injected explicitly; no implicit network access.

An async transport implements generate(request). Production provider entitlement is not claimed.
The orchestrator rejects any output that changes deterministic facts or financial authority.
"""

from typing import Protocol

from pydantic import Field, SecretStr, StrictStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.agents.schemas import AgentName, Identifier
from app.models.data import DataModel


class LLMRequest(DataModel):
    provider: Identifier
    model: Identifier
    agent: AgentName
    instruction: StrictStr = Field(max_length=400)
    structured_evidence_json: StrictStr = Field(max_length=50000)
    validated_response_json: StrictStr = Field(max_length=50000)
    response_schema_json: StrictStr = Field(max_length=50000)
    allowed_claims_json: StrictStr = Field(default="[]", max_length=50000)


class LLMProvider(Protocol):
    provider: str
    model: str

    async def generate(self, request: LLMRequest) -> str: ...


class StructuredLLMProvider:
    """Explicit configured transport adapter; agents never import vendor SDKs or read keys."""

    def __init__(self, *, provider, model, transport):
        # Validate only public provider/model identifiers, never accept credentials here.
        request = LLMRequest(
            provider=provider,
            model=model,
            agent="MARKET",
            instruction="",
            structured_evidence_json="{}",
            validated_response_json="{}",
            response_schema_json="{}",
        )
        self.provider, self.model, self._transport = request.provider, request.model, transport

    @classmethod
    def from_configuration(cls, configuration, *, transport):
        if configuration.provider is None or configuration.model is None:
            raise ValueError("Explicit provider/model configuration required")
        return cls(provider=configuration.provider, model=configuration.model, transport=transport)

    async def generate(self, request):
        if request.provider != self.provider or request.model != self.model:
            raise ValueError("Configured provider/model mismatch")
        result = await self._transport(request)
        if type(result) is not str or len(result) > 50000:
            raise ValueError("Invalid structured provider response")
        return result


# Configuration is owned by the transport host, never passed to an agent or controlled reader.


class LLMConfiguration(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LLM_", extra="ignore", frozen=True, hide_input_in_errors=True
    )
    provider: Identifier | None = None
    model: Identifier | None = None
    api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    base_url: StrictStr | None = Field(default=None, exclude=True, repr=False)
    timeout_seconds: int = Field(default=5, strict=True, ge=1, le=30)
    max_output_bytes: int = Field(default=50000, strict=True, ge=1024, le=50000)
    max_output_tokens: int = Field(default=4096, strict=True, ge=128, le=8192)
    structured_output: bool = Field(default=True, strict=True)

    @model_validator(mode="after")
    def configured(self):
        if (self.provider is None) != (self.model is None):
            raise ValueError("Both configured provider and model are required")
        return self
