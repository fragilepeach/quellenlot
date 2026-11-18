"""Local Ollama adapter using structured JSON output and CPU-friendly limits."""

from __future__ import annotations

from typing import TypeVar

import httpx
from pydantic import BaseModel, ConfigDict

from quellenlot_agents.provider_errors import ProviderError

_LOCAL_CHAT_ENDPOINT = "http://127.0.0.1:11434/api/chat"
OutputModel = TypeVar("OutputModel", bound=BaseModel)


class _Message(BaseModel):
    """Relevant response fields from an Ollama chat response."""

    model_config = ConfigDict(extra="ignore")
    content: str | None = None


class _Completion(BaseModel):
    """Minimal Ollama response envelope."""

    model_config = ConfigDict(extra="ignore")
    message: _Message


async def complete_json(
    model_name: str,
    context_length: int,
    system_prompt: str,
    user_prompt: str,
    output_model: type[OutputModel],
) -> OutputModel:
    """Call the local Ollama server and validate its structured JSON response."""
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "format": output_model.model_json_schema(),
        "options": {"temperature": 0, "num_ctx": context_length},
        "stream": False,
        "keep_alive": 0,
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(900.0, connect=5.0),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.post(_LOCAL_CHAT_ENDPOINT, json=payload)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        msg = f"Local Ollama request failed ({type(exc).__name__}); is Ollama running?"
        raise ProviderError(msg) from exc

    try:
        completion = _Completion.model_validate_json(response.content)
        content = completion.message.content
        if content is None:
            msg = "Ollama returned an empty message."
            raise ProviderError(msg)
        return output_model.model_validate_json(content)
    except ValueError as exc:
        msg = f"Ollama returned JSON incompatible with {output_model.__name__}."
        raise ProviderError(msg) from exc
