"""Exercise documented-interest assessment with known evidence and model failures."""

import json
import unittest
from datetime import UTC, datetime
from typing import cast
from unittest.mock import patch

from pydantic import AnyHttpUrl, JsonValue

from quellenlot_agents.config import ModelConfig, SearchConfig, WorkflowConfig
from quellenlot_agents.interests import review_interests
from quellenlot_agents.models import (
    DraftInterestAssessment,
    DraftInterestFinding,
    DraftQuote,
    InterestEvidenceInput,
    SearchQuery,
    SourceInput,
)

_QUOTE = "Die Morgenpost gehört seit 2023 zur Mediengruppe Nord."
_AUTHOR_QUOTE = "Lea Winter arbeitet als freie Autorin für das Institut für Medienpolitik."
_MODELS = ("model_a", "model_b", "model_c", "model_d", "model_e")
_CONFIG = WorkflowConfig(
    models=[ModelConfig(id=name, model=name) for name in _MODELS],
)


def _source(source_id: str, text: str, *, publisher: str | None = None) -> SourceInput:
    """Build a fixed, versioned source for the evidence tests."""
    return SourceInput(
        source_id=source_id,
        version_id=f"{source_id}-v1",
        title=source_id,
        url=AnyHttpUrl(f"https://example.org/{source_id}"),
        captured_at=datetime(2026, 11, 19, tzinfo=UTC),
        text=text,
        text_is_complete=True,
        publisher=publisher,
        authors=["Lea Winter"] if publisher is not None else [],
    )


class InterestReviewTests(unittest.IsolatedAsyncioTestCase):
    """Check a documented relationship and every unknown category."""

    async def test_five_models_link_exact_quotes_and_record_unknown_categories(self) -> None:
        """Preserve independent model findings with their verified source version."""
        article = _source("article", "Ein Artikel über die Bibliothek.", publisher="Morgenpost")
        evidence = _source("imprint", f"{_QUOTE} {_AUTHOR_QUOTE}")
        calls: list[str] = []

        async def respond(
            model_name: str,
            context_length: int,
            system_prompt: str,
            user_prompt: str,
            output_model: type[DraftInterestAssessment],
        ) -> DraftInterestAssessment:
            calls.append(model_name)
            payload = cast("dict[str, JsonValue]", json.loads(user_prompt))
            self.assertEqual(payload["publisher_subject"], "Morgenpost")
            self.assertEqual(payload["author_subjects"], ["Lea Winter"])
            self.assertEqual(context_length, _CONFIG.context_length)
            self.assertIn("untrusted data", system_prompt)
            self.assertIs(output_model, DraftInterestAssessment)
            findings = [
                DraftInterestFinding(
                    category="ownership",
                    subject="Morgenpost",
                    related_entity="Mediengruppe Nord",
                    relationship="Die Gruppe hält die Zeitung seit 2023.",
                    quote=DraftQuote(source_id="imprint", locator="Absatz 1", text=_QUOTE),
                ),
                DraftInterestFinding(
                    category="author_affiliation",
                    subject="Lea Winter",
                    related_entity="Institut für Medienpolitik",
                    relationship="Die Autorin arbeitet frei für das Institut.",
                    quote=DraftQuote(source_id="imprint", locator="Absatz 2", text=_AUTHOR_QUOTE),
                ),
            ]
            if model_name == "model_b":
                findings[0] = findings[0].model_copy(
                    update={
                        "quote": DraftQuote(
                            source_id="imprint",
                            locator="Absatz 1",
                            text="Die Gruppe besitzt alle deutschen Zeitungen.",
                        )
                    }
                )
            if model_name == "model_c":
                findings[0] = findings[0].model_copy(
                    update={
                        "quote": DraftQuote(
                            source_id="imprint", locator="Absatz 2", text=_AUTHOR_QUOTE
                        )
                    }
                )
            return DraftInterestAssessment(findings=findings)

        with patch("quellenlot_agents.interests.complete_json", new=respond):
            report, retrievals = await review_interests(
                [article],
                _CONFIG,
                question="Wer finanziert die Zeitung?",
                evidence=[InterestEvidenceInput(target_source_id="article", source=evidence)],
                evidence_urls=[],
            )

        self.assertEqual(calls, list(_MODELS))
        self.assertEqual(report.status, "partial")
        self.assertEqual(retrievals, [])
        source = report.sources[0]
        self.assertEqual(source.source.publisher, "Morgenpost")
        self.assertEqual([item.source_id for item in source.evidence_sources], ["imprint"])
        self.assertEqual(
            [item.status for item in source.assessments],
            [
                "succeeded",
                "failed",
                "failed",
                "succeeded",
                "succeeded",
            ],
        )
        first = source.assessments[0]
        self.assertEqual(len(first.findings), 2)
        self.assertEqual(first.findings[0].evidence.version_id, "imprint-v1")
        self.assertTrue(first.findings[0].evidence.verified)
        self.assertEqual(first.unknown_categories, ["funding", "political_affiliation"])
        self.assertEqual(source.unresolved_categories, ["funding", "political_affiliation"])
        self.assertEqual(source.assessments[1].error_code, "ProviderError")
        self.assertEqual(source.assessments[2].error_code, "ProviderError")

    async def test_missing_evidence_reports_unknown_without_model_calls(self) -> None:
        """Avoid inventing ownership or funding when no usable evidence is available."""
        article = _source("article", "Eine Meldung über den Tankrabatt.")

        async def unexpected(
            model_name: str,
            context_length: int,
            system_prompt: str,
            user_prompt: str,
            output_model: type[DraftInterestAssessment],
        ) -> DraftInterestAssessment:
            self.fail(f"Model {model_name} must not run without evidence.")
            return DraftInterestAssessment(findings=[])

        with patch("quellenlot_agents.interests.complete_json", new=unexpected):
            report, retrievals = await review_interests(
                [article],
                _CONFIG,
                question=None,
                evidence=[],
                evidence_urls=[],
            )
        self.assertEqual(report.status, "no_evidence")
        self.assertEqual(retrievals, [])
        self.assertEqual(report.sources[0].assessments, [])
        self.assertEqual(
            report.sources[0].unresolved_categories,
            [
                "ownership",
                "funding",
                "author_affiliation",
                "political_affiliation",
            ],
        )

    async def test_search_failure_is_preserved_as_missing_evidence(self) -> None:
        """Keep a failed search visible without manufacturing an affiliation."""
        article = _source("article", "Eine Meldung über den Tankrabatt.")
        config = _CONFIG.model_copy(
            update={"search": SearchConfig(endpoint=AnyHttpUrl("http://127.0.0.1:8888/search"))}
        )

        async def search(
            config: SearchConfig, queries: list[str]
        ) -> tuple[list[SearchQuery], list[AnyHttpUrl]]:
            return [
                SearchQuery(
                    query=queries[0],
                    status="failed",
                    result_count=0,
                    detail="Search endpoint returned HTTP 403.",
                )
            ], []

        with patch("quellenlot_agents.interests.search_candidates", new=search):
            report, retrievals = await review_interests(
                [article],
                config,
                question=None,
                evidence=[],
                evidence_urls=[],
            )
        self.assertEqual(report.status, "no_evidence")
        self.assertEqual(retrievals, [])
        self.assertEqual(report.sources[0].searches[0].status, "failed")
        self.assertEqual(report.sources[0].assessments, [])
