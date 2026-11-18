"""Minimal asynchronous OpenAI-compatible JSON chat-completions adapter."""

from __future__ import annotations

from typing import TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field

from quellenlot_agents.config import ModelConfig, api_key_for


class ProviderError(RuntimeError):
    """A provider response could not be used as the requested typed result."""


class _Message(BaseModel):
    """Relevant response fields from a chat-completions choice."""

    model_config = ConfigDict(extra="ignore")
    content: str | None = None


class _Choice(BaseModel):
    """One response choice."""

    model_config = ConfigDict(extra="ignore")
    message: _Message


class _Completion(BaseModel):
    """Minimal provider response envelope."""

    model_config = ConfigDict(extra="ignore")
    choices: list[_Choice] = Field(min_length=1)


OutputModel = TypeVar("OutputModel", bound=BaseModel)


async def complete_json(
    config: ModelConfig,
    system_prompt: str,
    user_prompt: str,
    output_model: type[OutputModel],
) -> OutputModel:
    """Call a model and validate its JSON response against a Pydantic schema."""
    endpoint = f"{str(config.base_url).rstrip('/')}/chat/completions"
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(90.0, connect=10.0),
            follow_redirects=False,
        ) as client:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key_for(config)}"},
                json=payload,
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        msg = f"Provider request failed ({type(exc).__name__})."
        raise ProviderError(msg) from exc

    try:
        completion = _Completion.model_validate_json(response.content)
        content = completion.choices[0].message.content
        if content is None:
            msg = "Provider returned an empty message."
            raise ProviderError(msg)
        return output_model.model_validate_json(content)
    except ValueError as exc:
        msg = f"Provider returned JSON incompatible with {output_model.__name__}."
        raise ProviderError(msg) from exc
