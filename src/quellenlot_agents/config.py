"""Load validated model configuration without storing API secrets in files."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

from quellenlot_agents.models import ContractModel


class ModelConfig(ContractModel):
    """Settings for one OpenAI-compatible model endpoint."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    model: str = Field(min_length=1, max_length=200)
    base_url: AnyHttpUrl
    api_key_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,100}$")


class WorkflowConfig(BaseModel):
    """Exactly five distinct configured model identities."""

    model_config = ConfigDict(extra="forbid", strict=True)
    models: list[ModelConfig] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def require_distinct_models(self) -> WorkflowConfig:
        """Reject duplicate IDs or model names before any provider is called."""
        ids = [item.id for item in self.models]
        names = [item.model for item in self.models]
        if len(set(ids)) != len(ids) or len(set(names)) != len(names):
            msg = "The five configured model IDs and model names must be distinct."
            raise ValueError(msg)
        return self


def load_config(path: Path) -> WorkflowConfig:
    """Read TOML and require every referenced API key to exist in the environment."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        msg = f"Could not read TOML configuration at {path}."
        raise ValueError(msg) from exc

    config = WorkflowConfig.model_validate(raw)
    for model in config.models:
        if not os.environ.get(model.api_key_env):
            msg = f"Environment variable {model.api_key_env} is missing or empty."
            raise ValueError(msg)
    return config


def api_key_for(model: ModelConfig) -> str:
    """Return the secret value referenced by a validated model configuration."""
    value = os.environ.get(model.api_key_env)
    if not value:
        msg = f"Environment variable {model.api_key_env} is missing or empty."
        raise ValueError(msg)
    return value
