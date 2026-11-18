"""Exercise the installed article intake and comparison through the CLI."""

import json
import unittest
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypedDict, cast
from unittest.mock import patch

import httpx

from quellenlot_agents.cli import main
from quellenlot_agents.models import ArticleReport, RunReport

_FIRST_CLAIM = "Die Bibliothek öffnet am Montag."
_SECOND_CLAIM = "Der Eintritt ist frei."
_QUESTION = "Wann öffnet die Bibliothek?"
_ARTICLE = {
    "source_id": "article",
    "version_id": "original-v1",
    "title": "Neue Bibliothek",
    "url": "https://example.org/article",
    "captured_at": "2026-11-18T09:00:00Z",
    "text": f"{_FIRST_CLAIM} {_SECOND_CLAIM}",
    "text_is_complete": True,
}
_COMPARISON = {
    **_ARTICLE,
    "source_id": "comparison",
    "version_id": "comparison-v1",
    "title": "Information der Stadt",
    "url": "https://example.org/comparison",
    "text": "Die Bibliothek öffnet am Dienstag.",
}
_CONFIG = Path(__file__).resolve().parents[1] / "config.example.toml"


class _Chat(TypedDict):
    messages: list[dict[str, str]]


class _ReviewTask(TypedDict):
    claim: str
    sources: list[dict[str, object]]
    required_output: dict[str, str]


class _OllamaReplies:
    def __init__(
        self,
        claims: tuple[str, ...] = (_FIRST_CLAIM, _SECOND_CLAIM),
        *,
        bad_extraction: bool = False,
        failed_claim: str | None = None,
    ) -> None:
        self.claims = claims
        self.bad_extraction = bad_extraction
        self.failed_claim = failed_claim
        self.questions: list[str | None] = []
        self.reviewed_claims: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        payload = cast("_Chat", json.loads(request.content))
        task = cast("dict[str, object]", json.loads(payload["messages"][1]["content"]))
        if "article" in task:
            self.questions.append(cast("str | None", task.get("question")))
            anchor_is_valid = not self.bad_extraction and len(self.questions) > 1
            document: dict[str, object] = {
                "claims": [
                    {
                        "claim": claim,
                        "quote": {
                            "source_id": "article",
                            "locator": "Absatz 1",
                            "text": claim if anchor_is_valid else "Erfundenes Zitat.",
                        },
                    }
                    for claim in self.claims
                ]
            }
        else:
            review_task = cast("_ReviewTask", task)
            claim = review_task["claim"]
            self.reviewed_claims.append(claim)
            if claim == self.failed_claim:
                return httpx.Response(503)
            target = review_task["required_output"].get("reviewed_agent_id")
            document = (
                self._assess(claim, review_task["sources"])
                if target is None
                else {
                    "reviewed_agent_id": target,
                    "summary": "Abgeglichen.",
                    "findings": [
                        {"finding_index": index, "outcome": "agrees", "reasoning": "Belegt."}
                        for index in range(len(review_task["sources"]))
                    ],
                }
            )
        return httpx.Response(200, json={"message": {"content": json.dumps(document)}})

    @staticmethod
    def _assess(claim: str, sources: list[dict[str, object]]) -> dict[str, object]:
        findings: list[dict[str, object]] = []
        for source in reversed(sources):
            source_id = source["source_id"]
            if source_id == "article":
                relation = "supports"
                text = claim
            elif claim == _FIRST_CLAIM:
                relation = "contradicts"
                text = "Die Bibliothek öffnet am Dienstag."
            else:
                relation = "omits"
                text = "Ein nicht im Dokument enthaltenes Zitat."
            findings.append(
                {
                    "source_id": source_id,
                    "relation": relation,
                    "reasoning": "Text der Quelle verglichen.",
                    "quotes": [{"source_id": source_id, "locator": "Absatz 1", "text": text}],
                }
            )
        return {"summary": "Geprüft.", "open_questions": [], "findings": findings}


class ArticleCliTests(unittest.TestCase):
    """Verify article and legacy reports without model weights or network access."""

    def _run(
        self,
        case: Mapping[str, object],
        replies: _OllamaReplies,
        *,
        expected_exit: int | None = None,
    ) -> bytes:
        client = httpx.AsyncClient
        transport = httpx.MockTransport(replies)

        def make_client(**_kwargs: object) -> httpx.AsyncClient:
            return client(transport=transport)

        with TemporaryDirectory() as directory:
            input_path = Path(directory) / "case.json"
            output_path = Path(directory) / "report.json"
            input_path.write_text(json.dumps(dict(case)), encoding="utf-8")
            args = [
                "quellenlot-agents",
                "--config",
                str(_CONFIG),
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ]
            with (
                patch("sys.argv", args),
                patch("quellenlot_agents.provider.httpx.AsyncClient", new=make_client),
            ):
                if expected_exit is None:
                    main()
                else:
                    with self.assertRaises(SystemExit) as error:
                        main()
                    self.assertEqual(error.exception.code, expected_exit)
            return output_path.read_bytes()

    def test_question_and_each_claim_get_a_source_comparison(self) -> None:
        """Exact citations remain linked to source versions and follow the input source order."""
        replies = _OllamaReplies()
        case = {
            "case_id": "library",
            "article": _ARTICLE,
            "question": _QUESTION,
            "comparison_sources": [_COMPARISON],
        }
        report = ArticleReport.model_validate_json(self._run(case, replies))
        self.assertEqual(report.status, "complete")
        self.assertEqual(report.question, _QUESTION)
        self.assertEqual(replies.questions, [_QUESTION, _QUESTION])
        self.assertEqual(
            [attempt.status for attempt in report.extraction_attempts], ["failed", "succeeded"]
        )
        self.assertEqual(replies.reviewed_claims, [_FIRST_CLAIM] * 10 + [_SECOND_CLAIM] * 10)
        first, second = report.claims
        self.assertEqual(first.article_quote.version_id, "original-v1")
        self.assertTrue(first.article_quote.verified)
        self.assertEqual(
            [row.source.source_id for row in first.source_comparison], ["article", "comparison"]
        )
        comparison = first.source_comparison[1]
        self.assertEqual(str(comparison.source.url), _COMPARISON["url"])
        self.assertEqual(len(comparison.judgments), 5)
        judgment = comparison.judgments[0]
        self.assertEqual(judgment.relation, "contradicts")
        self.assertEqual(judgment.citations[0].version_id, "comparison-v1")
        self.assertEqual(judgment.citations[0].locator, "Absatz 1")
        omitted = second.source_comparison[1].judgments[0]
        self.assertEqual(omitted.relation, "omits")
        self.assertEqual(omitted.citations, [])

    def test_article_only(self) -> None:
        """An article alone gets reviewed with no question or comparison sources."""
        replies = _OllamaReplies(claims=(_FIRST_CLAIM,))
        case = {"case_id": "library", "article": _ARTICLE}
        report = ArticleReport.model_validate_json(self._run(case, replies))
        self.assertEqual(report.status, "complete")
        self.assertIsNone(report.question)
        self.assertEqual(replies.questions, [None, None])
        self.assertEqual(len(report.claims[0].source_comparison), 1)

    def test_no_claims_and_extraction_failure_are_distinct(self) -> None:
        """An empty valid response skips review, while bad anchors exhaust the model pool."""
        case = {"case_id": "library", "article": _ARTICLE}
        empty = _OllamaReplies(claims=())
        empty_report = ArticleReport.model_validate_json(self._run(case, empty))
        self.assertEqual(empty_report.status, "no_claims")
        self.assertEqual(empty.reviewed_claims, [])
        bad = _OllamaReplies(bad_extraction=True)
        bad_report = ArticleReport.model_validate_json(self._run(case, bad, expected_exit=2))
        self.assertEqual(bad_report.status, "failed")
        self.assertEqual(
            [attempt.status for attempt in bad_report.extraction_attempts], ["failed"] * 5
        )
        self.assertEqual(bad.reviewed_claims, [])

    def test_one_failed_claim_keeps_the_other_comparison(self) -> None:
        """A failed claim review yields a partial report with both claim records."""
        replies = _OllamaReplies(failed_claim=_SECOND_CLAIM)
        case = {"case_id": "library", "article": _ARTICLE}
        report = ArticleReport.model_validate_json(self._run(case, replies))
        self.assertEqual(report.status, "partial")
        self.assertEqual([claim.review.status for claim in report.claims], ["complete", "failed"])
        self.assertEqual(report.claims[1].source_comparison[0].judgments, [])

    def test_explicit_claim_keeps_legacy_report(self) -> None:
        """The original claim-input JSON continues to use the original workflow."""
        replies = _OllamaReplies()
        case = {"case_id": "library", "claim": _FIRST_CLAIM, "sources": [_ARTICLE]}
        report = RunReport.model_validate_json(self._run(case, replies))
        self.assertEqual(report.status, "complete")
        self.assertEqual(report.claim, _FIRST_CLAIM)
        self.assertEqual(replies.questions, [])
        self.assertEqual(replies.reviewed_claims, [_FIRST_CLAIM] * 10)
