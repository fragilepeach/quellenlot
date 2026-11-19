"""Exercise the installed article intake and comparison through the CLI."""

import json
import socket
import unittest
from collections.abc import Callable, Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypedDict, cast
from unittest.mock import patch

import httpx

from quellenlot_agents.cli import main
from quellenlot_agents.models import ArticleReport, ArticleUrlReport, RunReport

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
_ARTICLE_HTML = f"""<!doctype html>
<html><head><title>Neue Bibliothek</title></head><body>
<nav>Navigation is outside the article.</nav><main><article>
<p>Die Bibliothek öffnet <em>am Montag.</em></p><p>{_SECOND_CLAIM}</p>
</article></main></body></html>"""
_COMPARISON_HTML = """<!doctype html>
<html><head><title>Information der Stadt</title></head><body>
<article><p>Die Bibliothek öffnet am Dienstag.</p></article></body></html>"""
_PUBLIC_IP = "93.184.216.34"
_ARTICLE_URL = "https://news.example.test/link"
_COMPARISON_URL = "https://city.example.test/library"


def _fixture_dns(
    host: str, port: int, *_args: object, **_kwargs: object
) -> list[tuple[int, int, int, str, tuple[str, int]]]:
    ip = "127.0.0.1" if host == "internal.example.test" else _PUBLIC_IP
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))]


def _html_response(body: str) -> httpx.Response:
    return httpx.Response(200, text=body, headers={"Content-Type": "text/html; charset=utf-8"})


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
        self.article_texts: list[str] = []
        self.reviewed_claims: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        payload = cast("_Chat", json.loads(request.content))
        task = cast("dict[str, object]", json.loads(payload["messages"][1]["content"]))
        if "article" in task:
            self.questions.append(cast("str | None", task.get("question")))
            article = cast("dict[str, object]", task["article"])
            self.article_texts.append(cast("str", article["text"]))
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
        web: Callable[[httpx.Request], httpx.Response] | None = None,
    ) -> bytes:
        client = httpx.AsyncClient

        def respond(request: httpx.Request) -> httpx.Response:
            if request.url.host == "127.0.0.1" and request.url.path == "/api/chat":
                return replies(request)
            if web is None:
                msg = "Unexpected request outside the local Ollama client."
                raise AssertionError(msg)
            return web(request)

        transport = httpx.MockTransport(respond)

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
                patch("socket.getaddrinfo", new=_fixture_dns),
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

    def test_public_urls_produce_traceable_comparisons(self) -> None:
        """Fetched HTML reaches Ollama as readable snapshots with their final URLs."""
        replies = _OllamaReplies(claims=(_FIRST_CLAIM,))
        paths: list[str] = []

        def web(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.host, _PUBLIC_IP)
            self.assertEqual(request.extensions["sni_hostname"], request.headers["host"])
            paths.append(request.url.path)
            if request.url.path == "/link":
                self.assertEqual(request.headers["host"], "news.example.test")
                return httpx.Response(302, headers={"Location": "/archiv/neu"})
            if request.url.path == "/archiv/neu":
                return _html_response(_ARTICLE_HTML)
            self.assertEqual(request.headers["host"], "city.example.test")
            return _html_response(_COMPARISON_HTML)

        request_case = {
            "case_id": "url-library",
            "article_url": _ARTICLE_URL,
            "question": _QUESTION,
            "comparison_urls": [_COMPARISON_URL],
        }
        report = ArticleUrlReport.model_validate_json(self._run(request_case, replies, web=web))
        self.assertEqual(paths, ["/link", "/archiv/neu", "/library"])
        self.assertEqual(report.question, _QUESTION)
        self.assertEqual(report.status, "complete")
        self.assertEqual([item.status for item in report.retrievals], ["captured", "captured"])
        self.assertEqual(str(report.retrievals[0].requested_url), _ARTICLE_URL)
        final_url = "https://news.example.test/archiv/neu"
        self.assertEqual(str(report.retrievals[0].final_url), final_url)
        self.assertEqual(replies.article_texts[0], f"{_FIRST_CLAIM}\n{_SECOND_CLAIM}")
        self.assertIsNotNone(report.review)
        if report.review is None:
            return
        original, comparison = report.review.claims[0].source_comparison
        self.assertEqual(str(original.source.url), final_url)
        self.assertEqual(str(comparison.source.url), _COMPARISON_URL)
        self.assertEqual(comparison.source.version_id, comparison.source.captured_at.isoformat())
        citation = comparison.judgments[0].citations[0]
        self.assertEqual(citation.version_id, comparison.source.version_id)
        self.assertEqual(citation.text, "Die Bibliothek öffnet am Dienstag.")

    def test_failed_and_incomplete_comparisons_preserve_available_review(self) -> None:
        """Unavailable and restricted pages cannot yield false omission judgments."""
        replies = _OllamaReplies()

        def web(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/missing":
                return httpx.Response(403)
            if request.url.path == "/restricted":
                return _html_response(
                    '<script type="application/ld+json">{"isAccessibleForFree": false}</script>'
                    + _COMPARISON_HTML
                )
            return _html_response(_ARTICLE_HTML)

        case = {
            "case_id": "url-library",
            "article_url": _ARTICLE_URL,
            "comparison_urls": [
                "https://city.example.test/missing",
                "https://city.example.test/restricted",
            ],
        }
        report = ArticleUrlReport.model_validate_json(self._run(case, replies, web=web))
        self.assertEqual(report.status, "partial")
        self.assertEqual(
            [item.status for item in report.retrievals], ["captured", "failed", "partial"]
        )
        self.assertIn("HTTP 403", report.retrievals[1].detail)
        self.assertIn("restricted access", report.retrievals[2].detail)
        self.assertIsNotNone(report.review)
        if report.review is None:
            return
        source_rows = report.review.claims[1].source_comparison
        self.assertEqual([row.source.source_id for row in source_rows], ["article", "comparison-2"])
        self.assertFalse(source_rows[1].source.text_is_complete)
        self.assertEqual(source_rows[1].judgments[0].relation, "not_assessable")

    def test_unavailable_original_writes_failure_without_model_calls(self) -> None:
        """An inaccessible original is reported without starting extraction or review."""
        replies = _OllamaReplies()
        case = {"case_id": "url-library", "article_url": _ARTICLE_URL}
        report = ArticleUrlReport.model_validate_json(
            self._run(case, replies, expected_exit=2, web=lambda _request: httpx.Response(404))
        )
        self.assertEqual(report.status, "failed")
        self.assertEqual(report.retrievals[0].status, "failed")
        self.assertIn("HTTP 404", report.retrievals[0].detail)
        self.assertIsNone(report.review)
        self.assertEqual(replies.questions, [])

    def test_redirect_to_nonpublic_destination_is_blocked(self) -> None:
        """Reject a redirect after resolving its destination and before contacting it."""
        visited: list[str] = []

        def web(request: httpx.Request) -> httpx.Response:
            visited.append(request.headers["host"])
            return httpx.Response(302, headers={"Location": "https://internal.example.test/"})

        case = {"case_id": "url-library", "article_url": _ARTICLE_URL}
        report = ArticleUrlReport.model_validate_json(
            self._run(case, _OllamaReplies(), expected_exit=2, web=web)
        )
        self.assertEqual(visited, ["news.example.test"])
        self.assertEqual(report.retrievals[0].status, "failed")
        self.assertIn("public Internet addresses", report.retrievals[0].detail)
