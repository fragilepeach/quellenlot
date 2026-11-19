"""Load the local model pool and optional comparison search endpoint."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

from quellenlot_agents.models import ContractModel


class ModelConfig(ContractModel):
    """Identity for one locally installed Ollama model."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    model: str = Field(min_length=1, max_length=200)


class SearchConfig(ContractModel):
    """Configure a trusted SearXNG JSON endpoint and bound comparison retrieval."""

    endpoint: AnyHttpUrl
    language: str = Field(default="de-DE", pattern=r"^(?:all|[a-z]{2,3}(?:-[A-Z]{2})?)$")
    max_sources: int = Field(default=3, ge=1, le=5)

    @model_validator(mode="after")
    def validate_endpoint(self) -> SearchConfig:
        """Require a plain endpoint URL to keep query and credential handling explicit.

        Returns:
            The validated search configuration.

        Raises:
            ValueError: The endpoint contains credentials, a query, or a fragment.
        """
        url = self.endpoint
        if any(part is not None for part in (url.username, url.password, url.query, url.fragment)):
            msg = "The search endpoint cannot contain credentials, a query, or a fragment."
            raise ValueError(msg)
        return self


class WorkflowConfig(BaseModel):
    """Five distinct local models and one bounded context size."""

    model_config = ConfigDict(extra="forbid", strict=True)
    models: list[ModelConfig] = Field(min_length=5, max_length=5)
    context_length: int = Field(default=8192, ge=4096, le=16384)
    search: SearchConfig | None = None

    @model_validator(mode="after")
    def require_distinct_models(self) -> WorkflowConfig:
        """Reject duplicate IDs or model names before any provider is called.

        Returns:
            The validated configuration with distinct models.

        Raises:
            ValueError: Model identifiers or model names are repeated.
        """
        ids = [item.id for item in self.models]
        names = [item.model for item in self.models]
        if len(set(ids)) != len(ids) or len(set(names)) != len(names):
            msg = "The five configured model IDs and model names must be distinct."
            raise ValueError(msg)
        return self


def load_config(path: Path) -> WorkflowConfig:
    """Read and validate the local model configuration.

    Args:
        path: Path of the TOML configuration file.

    Returns:
        The validated model order, context length, and optional search settings.

    Raises:
        ValueError: The configuration cannot be read, parsed, or validated.
    """
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        msg = f"Could not read TOML configuration at {path}."
        raise ValueError(msg) from exc
    return WorkflowConfig.model_validate(raw)
