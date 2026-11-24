"""Validate bounded selection and source-anchored targeted follow-ups."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from quellenlot_agents.config import ModelConfig, WorkflowConfig
from quellenlot_agents.models import (
    AnalysisRecord,
    CaseInput,
    DraftTargetedRecheck,
    ReviewFinding,
    ReviewRecord,
    SourceInput,
)
from quellenlot_agents import workflow


def _analysis(agent: str, relation: str) -> AnalysisRecord:
    """Construct a typed successful synthetic agent finding."""
    return AnalysisRecord.model_validate(
        {
            "agent_id": agent,
            "model": agent,
            "status": "succeeded",
            "summary": "",
            "findings": [
                {
                    "source_id": "source-a",
                    "version_id": "v1",
                    "relation": relation,
                    "reasoning": "Example.",
                    "evidence_status": "no_quote",
                    "quotes": [],
                }
            ],
            "open_questions": [],
            "error_code": None,
        }
    )


class TargetedChecksTests(unittest.TestCase):
    """Selection should be predictable and require a disputed source."""

    def test_only_one_disputed_source_is_scheduled(self) -> None:
        """Prioritize review objections, cap calls, and skip disabled follow-ups."""
        analyses = [_analysis("agent-a", "supports"), _analysis("agent-b", "contradicts")]
        review = ReviewRecord(
            reviewer_agent_id="agent-b",
            reviewed_agent_id="agent-a",
            status="succeeded",
            summary=None,
            error_code=None,
            findings=[
                ReviewFinding(
                    finding_index=0,
                    outcome="challenges",
                    reasoning="Different time range.",
                    quote=None,
                )
            ],
        )
        self.assertEqual(workflow._targeted_sources(analyses, [review], 0), [])
        self.assertEqual(
            _targeted_sources(analyses, [review], 1), [("source-a", "agent-a", "agent-b")]
        )


class TargetedProviderTests(unittest.IsolatedAsyncioTestCase):
    """Validate the added request without contacting Ollama."""

    async def test_followup_verifies_quote_without_rewriting_original(self) -> None:
        """Keep a snapshot-bound quote and the independent original relations."""
        source = SourceInput(
            source_id="source-a",
            version_id="v1",
            title="Example",
            captured_at=datetime(2026, 11, 20, tzinfo=UTC),
            text="Die Quelle nennt den August.",
            text_is_complete=True,
        )
        case = CaseInput(case_id="example", claim="Die Aussage gilt immer.", sources=[source])
        config = WorkflowConfig(
            models=[ModelConfig(id=f"agent-{i}", model=f"model-{i}") for i in range(5)],
            targeted_rechecks=1,
        )
        draft = DraftTargetedRecheck.model_validate(
            {
                "source_id": "source-a",
                "relation": "qualifies",
                "reasoning": "Only August.",
                "quote": {
                    "source_id": "source-a",
                    "locator": "Satz 1",
                    "text": "Die Quelle nennt den August.",
                },
            }
        )
        response = AsyncMock(return_value=draft)
        with patch("quellenlot_agents.workflow.complete_json", new=response):
            result = await workflow._targeted_recheck(
                case, config, "source-a", "agent-0", "agent-1", [_analysis("agent-0", "supports")]
            )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.rechecking_agent_id, "agent-2")
        self.assertEqual(result.relation, "qualifies")
        self.assertTrue(result.quote is not None and result.quote.verified)


if __name__ == "__main__":
    unittest.main()
