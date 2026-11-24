"""Verify local Ollama usage statistics without making an external model request."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

import httpx
from pydantic import BaseModel

from quellenlot_agents.metrics import collect_model_calls
from quellenlot_agents.provider import ProviderError, complete_json


class _Answer(BaseModel):
    """Minimal response schema for an isolated provider call."""

    answer: str


class MetricTests(unittest.TestCase):
    """Check successful, failed, and absent-token observations."""

    def test_success_records_wall_time_and_native_counters(self) -> None:
        """Preserve Ollama-provided token counts and evaluate duration."""

        def response(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "message": {"content": '{"answer":"okay"}'},
                    "prompt_eval_count": 32,
                    "eval_count": 10,
                    "eval_duration": 2_000_000_000,
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        with (
            patch("quellenlot_agents.provider.httpx.AsyncClient", return_value=client),
            collect_model_calls() as calls,
        ):
            result = asyncio.run(complete_json("local-model", 8192, "system", "user", _Answer))
        self.assertEqual(result.answer, "okay")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].status, "succeeded")
        self.assertEqual(calls[0].task, "_Answer")
        self.assertEqual(calls[0].prompt_tokens, 32)
        self.assertEqual(calls[0].output_tokens, 10)
        self.assertEqual(calls[0].eval_duration_ns, 2_000_000_000)
        self.assertGreaterEqual(calls[0].wall_time_ms, 0)

    def test_http_failure_keeps_missing_metrics_unknown(self) -> None:
        """Never invent token counts when Ollama did not respond."""

        def response(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="service unavailable")

        client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        with (
            patch("quellenlot_agents.provider.httpx.AsyncClient", return_value=client),
            collect_model_calls() as calls,
            self.assertRaises(ProviderError),
        ):
            asyncio.run(complete_json("local-model", 8192, "system", "user", _Answer))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].status, "failed")
        self.assertEqual(calls[0].error_code, "HTTPStatusError")
        self.assertIsNone(calls[0].prompt_tokens)
        self.assertIsNone(calls[0].output_tokens)
        with collect_model_calls() as empty:
            pass
        self.assertEqual(empty, [])


if __name__ == "__main__":
    unittest.main()
