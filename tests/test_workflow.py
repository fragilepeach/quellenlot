"""Regression tests for the claim review workflow."""

import json
import unittest
from datetime import UTC, datetime
from typing import TypedDict, cast
from unittest.mock import patch

import httpx

from quellenlot_agents.config import ModelConfig, WorkflowConfig
from quellenlot_agents.models import CaseInput, RunReport, SourceInput
from quellenlot_agents.workflow import run_review

_MODEL_IDS = ("model_a", "model_b", "model_c", "model_d", "model_e")
_QUOTE = "The tax rate fell in June."
_CASE = CaseInput(
    case_id="coverage",
    claim="The tax rate fell in June.",
    sources=[
        SourceInput(
            source_id=source_id,
            version_id="v1",
            title=f"Source {source_id}",
            captured_at=datetime(2026, 1, 1, tzinfo=UTC),
            text=_QUOTE,
            text_is_complete=source_id == "first",
        )
        for source_id in ("first", "second")
    ],
)
_CONFIG = WorkflowConfig(models=[ModelConfig(id=name, model=name) for name in _MODEL_IDS])


class _Request(TypedDict):
    model: str
    messages: list[dict[str, str]]


class ReviewWorkflowTests(unittest.IsolatedAsyncioTestCase):
    """Exercise the workflow against controlled Ollama responses."""

    async def _run(
        self,
        first_review_indexes: tuple[int, ...] = (1, 0),
        *,
        failed_models: tuple[str, ...] = (),
    ) -> RunReport:
        client = httpx.AsyncClient

        def respond(request: httpx.Request) -> httpx.Response:
            payload = cast("_Request", json.loads(request.content))
            model = payload["model"]
            task = cast("dict[str, dict[str, str]]", json.loads(payload["messages"][1]["content"]))
            target_id = task["required_output"].get("reviewed_agent_id")
            if target_id is not None:
                indexes = first_review_indexes if model == "model_a" else (0, 1)
                return httpx.Response(
                    200,
                    json={
                        "message": {
                            "content": json.dumps(
                                {
                                    "reviewed_agent_id": target_id,
                                    "summary": "Checked the assigned findings.",
                                    "findings": [
                                        {
                                            "finding_index": index,
                                            "outcome": "agrees",
                                            "reasoning": "Compared with the source.",
                                        }
                                        for index in indexes
                                    ],
                                }
                            )
                        }
                    },
                )
            if model in failed_models:
                return httpx.Response(503)
            return httpx.Response(
                200,
                json={
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Assessed the supplied texts.",
                                "open_questions": [],
                                "findings": [
                                    {
                                        "source_id": "first",
                                        "relation": "supports",
                                        "reasoning": "The source gives the month.",
                                        "quotes": [
                                            {"source_id": "first", "locator": "1", "text": _QUOTE},
                                            {
                                                "source_id": "first",
                                                "locator": "2",
                                                "text": "This quote is absent.",
                                            },
                                        ],
                                    },
                                    {
                                        "source_id": "second",
                                        "relation": "omits",
                                        "reasoning": "The supplied excerpt is incomplete.",
                                        "quotes": [],
                                    },
                                ],
                            }
                        )
                    }
                },
            )

        transport = httpx.MockTransport(respond)

        def make_client(
            *, timeout: httpx.Timeout, follow_redirects: bool, trust_env: bool
        ) -> httpx.AsyncClient:
            return client(
                transport=transport,
                timeout=timeout,
                follow_redirects=follow_redirects,
                trust_env=trust_env,
            )

        with patch(
            "quellenlot_agents.provider.httpx.AsyncClient",
            new=make_client,
        ):
            return await run_review(_CASE, _CONFIG)

    async def test_complete_review_accepts_any_order(self) -> None:
        """All findings may be reviewed once in either order."""
        report = await self._run()
        self.assertEqual(report.status, "complete")
        self.assertEqual(len(report.analyses), 5)
        self.assertEqual(len(report.reviews), 5)
        self.assertEqual([item.finding_index for item in report.reviews[0].findings], [1, 0])
        self.assertEqual(
            [quote.verified for quote in report.analyses[0].findings[0].quotes],
            [True, False],
        )
        self.assertEqual(report.analyses[0].findings[1].relation, "not_assessable")

    async def test_invalid_coverage_marks_report_partial(self) -> None:
        """Missing, duplicate, and out-of-range indexes fail only the affected review."""
        for indexes in ((0,), (0, 0), (0, 1, 1), (0, 1, 2)):
            with self.subTest(indexes=indexes):
                report = await self._run(indexes)
                self.assertEqual(report.status, "partial")
                self.assertEqual(report.reviews[0].status, "failed")
                self.assertEqual(len(report.reviews[0].findings), 0)
                self.assertEqual(report.reviews[0].error_code, "ProviderError")
                self.assertTrue(all(review.status == "succeeded" for review in report.reviews[1:]))

    async def test_provider_failures_leave_remaining_review_pairs(self) -> None:
        """Successful models form the review cycle even when one model fails."""
        report = await self._run(failed_models=("model_b",))
        self.assertEqual(report.status, "partial")
        self.assertEqual(report.analyses[1].status, "failed")
        self.assertEqual(
            [(review.reviewer_agent_id, review.reviewed_agent_id) for review in report.reviews],
            [
                ("model_a", "model_c"),
                ("model_c", "model_d"),
                ("model_d", "model_e"),
                ("model_e", "model_a"),
            ],
        )

    async def test_fewer_than_two_successful_analyses_skip_review(self) -> None:
        """One model gives a partial report and zero successful models give a failed report."""
        report = await self._run(failed_models=_MODEL_IDS[1:])
        self.assertEqual(report.status, "partial")
        self.assertEqual(report.reviews, [])
        report = await self._run(failed_models=_MODEL_IDS)
        self.assertEqual(report.status, "failed")
        self.assertEqual(report.reviews, [])
