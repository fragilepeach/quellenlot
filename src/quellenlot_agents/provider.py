"""Local Ollama adapter using structured JSON output and CPU-friendly limits."""

from __future__ import annotations

from time import perf_counter_ns

import httpx
from pydantic import BaseModel, ConfigDict

from quellenlot_agents.metrics import record_model_call
from quellenlot_agents.models import ModelCallMetric

_LOCAL_CHAT_ENDPOINT = "http://127.0.0.1:11434/api/chat"


class ProviderError(RuntimeError):
    """A local model request or response could not be used."""


class _Message(BaseModel):
    """Relevant response fields from an Ollama chat response."""

    model_config = ConfigDict(extra="ignore")
    content: str | None = None


class _Completion(BaseModel):
    """Minimal Ollama response envelope plus optional observed token counters."""

    model_config = ConfigDict(extra="ignore")
    message: _Message
    prompt_eval_count: int | None = None
    eval_count: int | None = None
    eval_duration: int | None = None


async def complete_json[OutputModel: BaseModel](
    model_name: str,
    context_length: int,
    system_prompt: str,
    user_prompt: str,
    output_model: type[OutputModel],
) -> OutputModel:
    """Call the local Ollama server and validate its structured JSON response.

    Args:
        model_name: Name of the installed Ollama model.
        context_length: Maximum context length in tokens.
        system_prompt: Instructions for the model role and evidence policy.
        user_prompt: Serialized task data sent to that role.
        output_model: Pydantic model for the required JSON response.

    Returns:
        An instance validated against the supplied output model.

    Raises:
        ProviderError: The local response is unavailable, empty, or invalid.
    """
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
    start_ns = perf_counter_ns()
    status: str = "failed"
    error_code: str | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    eval_duration_ns: int | None = None
    try:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(900.0, connect=5.0),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.post(_LOCAL_CHAT_ENDPOINT, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            error_code = type(exc).__name__
            msg = f"Local Ollama request failed ({error_code}); is Ollama running?"
            raise ProviderError(msg) from exc

        try:
            completion = _Completion.model_validate_json(response.content)
            prompt_tokens = completion.prompt_eval_count
            output_tokens = completion.eval_count
            eval_duration_ns = completion.eval_duration
            content = completion.message.content
            if content is None:
                msg = "Ollama returned an empty message."
                raise ProviderError(msg)
            parsed = output_model.model_validate_json(content)
        except ValueError as exc:
            error_code = type(exc).__name__
            msg = f"Ollama returned JSON incompatible with {output_model.__name__}."
            raise ProviderError(msg) from exc
        status = "succeeded"
        return parsed
    except ProviderError:
        if error_code is None:
            error_code = "ProviderError"
        raise
    finally:
        record_model_call(
            ModelCallMetric(
                model=model_name,
                task=output_model.__name__,
                status="succeeded" if status == "succeeded" else "failed",
                wall_time_ms=round((perf_counter_ns() - start_ns) / 1_000_000, 3),
                prompt_tokens=prompt_tokens,
                output_tokens=output_tokens,
                eval_duration_ns=eval_duration_ns,
                error_code=error_code,
            )
        )
