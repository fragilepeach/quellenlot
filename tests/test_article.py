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

type _Json = bool | int | float | str | list[_Json] | dict[str, _Json] | None

_FIRST_CLAIM = "Die Bibliothek öffnet am Montag."
_SECOND_CLAIM = "Der Eintritt ist frei."
_QUESTION = "Wann öffnet die Bibliothek?"
_ARTICLE: dict[str, _Json] = {
    "source_id": "article",
    "version_id": "original-v1",
    "title": "Neue Bibliothek",
    "url": "https://example.org/article",
    "captured_at": "2026-11-18T09:00:00Z",
    "text": f"{_FIRST_CLAIM} {_SECOND_CLAIM}",
    "text_is_complete": True,
}
_COMPARISON: dict[str, _Json] = {
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
    host: str,
    port: int,
    _family: int,
    _type: int,
    _proto: int,
    _flags: int,
) -> list[tuple[int, int, int, str, tuple[str, int]]]:
    ip = "127.0.0.1" if host == "internal.example.test" else _PUBLIC_IP
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))]


def _html_response(body: str) -> httpx.Response:
    return httpx.Response(200, text=body, headers={"Content-Type": "text/html; charset=utf-8"})


def _json_rows(value: _Json) -> list[dict[str, _Json]]:
    if not isinstance(value, list):
        msg = "Expected a list of JSON objects."
        raise TypeError(msg)
    rows: list[dict[str, _Json]] = []
    for row in value:
        if not isinstance(row, dict):
            msg = "Expected a JSON object in the list."
            raise TypeError(msg)
        rows.append(row)
    return rows


class _Chat(TypedDict):
    messages: list[dict[str, str]]


class _ReviewTask(TypedDict):
    claim: str
    sources: list[dict[str, _Json]]
    required_output: dict[str, str]


class _OllamaReplies:
    def __init__(
        self,
        claims: tuple[str, ...] = (_FIRST_CLAIM, _SECOND_CLAIM),
        *,
        bad_extraction: bool = False,
        failed_claim: str | None = None,
        peer_challenge: bool = False,
    ) -> None:
        self.claims = claims
        self.bad_extraction = bad_extraction
        self.failed_claim = failed_claim
        self.peer_challenge = peer_challenge
        self.questions: list[str | None] = []
        self.article_texts: list[str] = []
        self.extraction_sources: list[dict[str, _Json]] = []
        self.assessment_sources: list[list[dict[str, _Json]]] = []
        self.peer_review_sources: list[list[dict[str, _Json]]] = []
        self.reviewed_claims: list[str] = []
        self.interest_subjects: list[str] = []
        self.editorial_tasks: list[dict[str, _Json]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        payload = cast("_Chat", json.loads(request.content))
        task = cast("dict[str, _Json]", json.loads(payload["messages"][1]["content"]))
        if "editorial_claims" in task:
            self.editorial_tasks.append(task)
            document = self.editorial_reply(task)
        elif "publisher_subject" in task:
            subject = cast("str", task["publisher_subject"])
            self.interest_subjects.append(subject)
            evidence = task["evidence"]
            if not isinstance(evidence, list):
                msg = "Interest evidence must be a list."
                raise ValueError(msg)
            first_evidence = evidence[0]
            if not isinstance(first_evidence, dict):
                msg = "Interest evidence must contain a source object."
                raise ValueError(msg)
            evidence_id = first_evidence["source_id"]
            if not isinstance(evidence_id, str):
                msg = "Interest evidence source ID must be text."
                raise ValueError(msg)
            document = {
                "findings": [
                    {
                        "category": "ownership",
                        "subject": subject,
                        "related_entity": "Mediengruppe Nord",
                        "relationship": "Die Zeitung gehört zur Mediengruppe.",
                        "quote": {
                            "source_id": evidence_id,
                            "locator": "Absatz 1",
                            "text": "Die Morgenpost gehört zur Mediengruppe Nord.",
                        },
                    }
                ]
            }
        elif "article" in task:
            self.questions.append(cast("str | None", task.get("question")))
            article = cast("dict[str, _Json]", task["article"])
            self.article_texts.append(cast("str", article["text"]))
            self.extraction_sources.append(article)
            anchor_is_valid = not self.bad_extraction and len(self.questions) > 1
            document: dict[str, _Json] = {
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
            if target is None:
                self.assessment_sources.append(review_task["sources"])
            else:
                self.peer_review_sources.append(review_task["sources"])
            document = (
                self._assess(claim, review_task["sources"])
                if target is None
                else {
                    "reviewed_agent_id": target,
                    "summary": "Abgeglichen.",
                    "findings": [
                        {
                            "finding_index": index,
                            "outcome": "challenges" if self.peer_challenge else "agrees",
                            "reasoning": "Zeitraum prüfen." if self.peer_challenge else "Belegt.",
                        }
                        for index in range(len(review_task["sources"]))
                    ],
                }
            )
        return httpx.Response(200, json={"message": {"content": json.dumps(document)}})

    @staticmethod
    def editorial_reply(task: dict[str, _Json]) -> dict[str, _Json]:
        """Generate an editorial reply for the selected claim passages.

        Args:
            task: Editorial prompt sent to the test provider.

        Returns:
            Model notes citing comparison evidence for each assigned claim.
        """
        claims = _json_rows(task["editorial_claims"])
        notes: list[_Json] = []
        for claim in claims:
            evidence = _json_rows(claim["comparison_evidence"])
            notes.append(
                {
                    "claim_id": claim["claim_id"],
                    "evidence_ids": [evidence[0]["evidence_id"]],
                    "assessment": "Die Angaben zur Öffnung weichen voneinander ab.",
                    "next_check": "Den aktuellen Öffnungstermin bei der Stadt bestätigen.",
                }
            )
        return {"claims": notes}

    @staticmethod
    def _assess(claim: str, sources: list[dict[str, _Json]]) -> dict[str, _Json]:
        findings: list[_Json] = []
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
        case: Mapping[str, _Json],
        replies: _OllamaReplies,
        *,
        expected_exit: int | None = None,
        web: Callable[[httpx.Request], httpx.Response] | None = None,
        search_enabled: bool = False,
        interests_enabled: bool = False,
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

        def make_client(
            *, timeout: httpx.Timeout, follow_redirects: bool, trust_env: bool
        ) -> httpx.AsyncClient:
            return client(
                transport=transport,
                timeout=timeout,
                follow_redirects=follow_redirects,
                trust_env=trust_env,
            )

        with TemporaryDirectory() as directory:
            input_path = Path(directory) / "case.json"
            output_path = Path(directory) / "report.json"
            input_path.write_text(json.dumps(dict(case)), encoding="utf-8")
            config_path = _CONFIG
            if search_enabled or interests_enabled:
                config_path = Path(directory) / "config.toml"
                content = _CONFIG.read_text(encoding="utf-8")
                if interests_enabled:
                    content = content.replace("check_interests = false", "check_interests = true")
                config_path.write_text(
                    content
                    + (
                        '\n[search]\nendpoint = "http://127.0.0.1:8888/search"\nmax_sources = 2\n'
                        if search_enabled
                        else ""
                    ),
                    encoding="utf-8",
                )
            args = [
                "quellenlot-agents",
                "--config",
                str(config_path),
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
        replies = _OllamaReplies(peer_challenge=True)
        case: dict[str, _Json] = {
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
        editorial = report.editorial
        if editorial is None:
            self.fail("Article review must include editorial coverage.")
        self.assertEqual(editorial.status, "partial")
        self.assertEqual(len(replies.editorial_tasks), 5)
        self.assertEqual(replies.editorial_tasks[0]["question"], _QUESTION)
        first_coverage, second_coverage = editorial.claims
        self.assertEqual(first_coverage.unresolved_dissent_count, 10)
        self.assertEqual(second_coverage.comparison_evidence_ids, [])
        self.assertEqual(second_coverage.comparison_sources_without_quotes, ["comparison"])
        tasks = _json_rows(replies.editorial_tasks[0]["editorial_claims"])
        self.assertEqual(tasks[0]["dissent_count"], 10)
        self.assertIn("Zeitraum prüfen.", str(tasks[0]["dissent_examples"]))
        for assessment in editorial.assessments:
            self.assertEqual(assessment.status, "succeeded")
            self.assertEqual([note.claim_id for note in assessment.claims], ["claim-1"])
            self.assertEqual(
                assessment.claims[0].evidence_ids, first_coverage.evidence_shown_to_models
            )

    def test_editorial_rejects_duplicate_claims_and_citations_outside_assignment(self) -> None:
        """Reject incomplete model coverage and claim-local citation errors in the final stage."""
        replies = _OllamaReplies()
        case: dict[str, _Json] = {
            "case_id": "invalid-editorial",
            "article": _ARTICLE,
            "comparison_sources": [_COMPARISON],
        }

        def editorial(task: dict[str, _Json]) -> dict[str, _Json]:
            document = _OllamaReplies.editorial_reply(task)
            notes = _json_rows(document["claims"])
            note = notes[0]
            match len(replies.editorial_tasks):
                case 1:
                    return {"claims": []}
                case 2:
                    return {"claims": [note, note]}
                case 3:
                    note["evidence_ids"] = ["evidence-1"]
                case 4:
                    note["claim_id"] = "claim-2"
                case 5:
                    note["evidence_ids"] = ["evidence-999"]
                case _:
                    self.fail("Only the five configured models should be called.")
            return document

        with patch.object(replies, "editorial_reply", new=editorial):
            report = ArticleReport.model_validate_json(self._run(case, replies))
        self.assertEqual(report.status, "complete")
        editorial_report = report.editorial
        if editorial_report is None:
            self.fail("Model failures must still yield an editorial report.")
        self.assertEqual(editorial_report.status, "failed")
        self.assertEqual([item.status for item in editorial_report.assessments], ["failed"] * 5)
        self.assertEqual([item.claims for item in editorial_report.assessments], [[]] * 5)
        self.assertEqual(editorial_report.claims[0].comparison_evidence_ids, ["evidence-2"])

    def test_article_only(self) -> None:
        """An article alone gets reviewed with no question or comparison sources."""
        replies = _OllamaReplies(claims=(_FIRST_CLAIM,))
        case: dict[str, _Json] = {"case_id": "library", "article": _ARTICLE}
        report = ArticleReport.model_validate_json(self._run(case, replies))
        self.assertEqual(report.status, "complete")
        self.assertIsNone(report.question)
        self.assertEqual(replies.questions, [None, None])
        self.assertEqual(len(report.claims[0].source_comparison), 1)
        self.assertEqual(replies.editorial_tasks, [])
        if report.editorial is not None:
            self.assertEqual(report.editorial.status, "no_comparison_evidence")

    def test_no_claims_and_extraction_failure_are_distinct(self) -> None:
        """An empty valid response skips review, while bad anchors exhaust the model pool."""
        case: dict[str, _Json] = {"case_id": "library", "article": _ARTICLE}
        empty = _OllamaReplies(claims=())
        empty_report = ArticleReport.model_validate_json(self._run(case, empty))
        self.assertEqual(empty_report.status, "no_claims")
        self.assertEqual(empty.reviewed_claims, [])
        if empty_report.editorial is not None:
            self.assertEqual(empty_report.editorial.status, "no_claims")
        bad = _OllamaReplies(bad_extraction=True)
        bad_report = ArticleReport.model_validate_json(self._run(case, bad, expected_exit=2))
        self.assertEqual(bad_report.status, "failed")
        self.assertEqual(
            [attempt.status for attempt in bad_report.extraction_attempts], ["failed"] * 5
        )
        self.assertEqual(bad.reviewed_claims, [])
        if bad_report.editorial is not None:
            self.assertEqual(bad_report.editorial.status, "failed")

    def test_one_failed_claim_keeps_the_other_comparison(self) -> None:
        """A failed claim review yields a partial report with both claim records."""
        replies = _OllamaReplies(failed_claim=_SECOND_CLAIM)
        case: dict[str, _Json] = {"case_id": "library", "article": _ARTICLE}
        report = ArticleReport.model_validate_json(self._run(case, replies))
        self.assertEqual(report.status, "partial")
        self.assertEqual([claim.review.status for claim in report.claims], ["complete", "failed"])
        self.assertEqual(report.claims[1].source_comparison[0].judgments, [])

    def test_explicit_claim_keeps_legacy_report(self) -> None:
        """The original claim-input JSON continues to use the original workflow."""
        replies = _OllamaReplies()
        case: dict[str, _Json] = {
            "case_id": "library",
            "claim": _FIRST_CLAIM,
            "sources": [_ARTICLE],
        }
        report = RunReport.model_validate_json(self._run(case, replies))
        self.assertEqual(report.status, "complete")
        self.assertEqual(report.claim, _FIRST_CLAIM)
        self.assertEqual(replies.questions, [])
        self.assertEqual(replies.reviewed_claims, [_FIRST_CLAIM] * 10)
        self.assertEqual(replies.editorial_tasks, [])

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

        request_case: dict[str, _Json] = {
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
        if report.review.editorial is None:
            self.fail("URL review must include an editorial assessment.")
        self.assertEqual(report.review.editorial.status, "complete")

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

        case: dict[str, _Json] = {
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
        if report.review.editorial is None:
            self.fail("Editorial coverage must retain URL retrieval gaps.")
        self.assertEqual(report.review.editorial.retrieval_gaps, report.retrievals[1:])
        self.assertEqual(report.review.editorial.incomplete_source_ids, ["article", "comparison-2"])

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

    def test_automatic_discovery_prioritizes_and_deduplicates_comparisons(self) -> None:
        """Search from accepted claims, use source retrieval, and retain selection decisions."""
        requested_paths: list[str] = []
        queries: list[str] = []
        replies = _OllamaReplies(claims=(_FIRST_CLAIM,))

        def web(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/search":
                self.assertEqual(request.url.port, 8888)
                self.assertEqual(request.url.params["language"], "de-DE")
                self.assertEqual(request.url.params["format"], "json")
                queries.append(request.url.params["q"])
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {"url": "https://news.example.test/link?utm_source=search#body"},
                            {"url": "https://media.example.test/general"},
                            {"url": "https://stats.bund.de/blocked"},
                            {"url": "https://stats.bund.de/official"},
                            {"url": "https://stats.bund.de/official?utm_campaign=duplicate"},
                            {"url": "https://stats.bund.de/mirror"},
                            {"url": "file:///etc/passwd"},
                        ]
                    },
                )
            requested_paths.append(request.url.path)
            if request.url.path == "/link":
                return _html_response(_ARTICLE_HTML)
            if request.url.path == "/blocked":
                return httpx.Response(403)
            if request.url.path in {"/official", "/mirror"}:
                return _html_response(_COMPARISON_HTML)
            return _html_response("<article><p>Die Bibliothek öffnet am Mittwoch.</p></article>")

        case = {"case_id": "find-library", "article_url": _ARTICLE_URL, "question": _QUESTION}
        report = ArticleUrlReport.model_validate_json(
            self._run(case, replies, web=web, search_enabled=True)
        )
        self.assertEqual(queries, [f"{_QUESTION} {_FIRST_CLAIM}", _FIRST_CLAIM])
        self.assertEqual(replies.questions, [_QUESTION, _QUESTION])
        self.assertEqual(requested_paths, ["/link", "/blocked", "/official", "/mirror", "/general"])
        self.assertEqual(report.status, "partial")
        if report.discovery is None or report.review is None:
            self.fail("The report must include discovery and claim comparison.")
        self.assertEqual([record.query for record in report.discovery.queries], queries)
        self.assertEqual(
            [candidate.status for candidate in report.discovery.candidates],
            ["unavailable", "included", "duplicate", "included"],
        )
        self.assertEqual(
            [item.source_id for item in report.retrievals],
            [
                "article",
                "comparison-1",
                "comparison-2",
                "comparison-3",
                "comparison-4",
            ],
        )
        comparison = report.review.claims[0].source_comparison
        self.assertEqual(
            [entry.source.source_id for entry in comparison],
            ["article", "comparison-2", "comparison-4"],
        )
        self.assertEqual(
            comparison[1].judgments[0].citations[0].text, "Die Bibliothek öffnet am Dienstag."
        )

    def test_search_failure_preserves_article_review(self) -> None:
        """Report an inaccessible search service while reviewing the original snapshot."""
        replies = _OllamaReplies(claims=(_FIRST_CLAIM,))

        def web(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/search":
                return httpx.Response(403)
            return _html_response(_ARTICLE_HTML)

        case = {"case_id": "find-library", "article_url": _ARTICLE_URL}
        report = ArticleUrlReport.model_validate_json(
            self._run(case, replies, web=web, search_enabled=True)
        )
        self.assertEqual(report.status, "partial")
        if report.discovery is None or report.review is None:
            self.fail("The report must include the search failure and the original review.")
        self.assertEqual(report.discovery.queries[0].status, "failed")
        self.assertEqual(report.discovery.queries[0].detail, "Search endpoint returned HTTP 403.")
        self.assertEqual(report.discovery.candidates, [])
        self.assertEqual(len(report.review.sources), 1)
        self.assertEqual(report.review.status, "complete")
        if report.review.editorial is not None:
            self.assertTrue(report.review.editorial.discovery_incomplete)

    def test_shared_wording_is_reported_in_both_cli_modes(self) -> None:
        """Expose one shared-wording report while preserving distinct source findings."""
        shared = (
            "Nach einer sechsmonatigen Sanierung kann die Bibliothek wieder Besucherinnen "
            "und Besucher aus dem gesamten Landkreis zu den üblichen Zeiten empfangen."
        )
        original = {**_ARTICLE, "text": f"{_FIRST_CLAIM}\n{shared}"}
        comparison = {
            **_COMPARISON,
            "text": (
                f"{shared.replace('üblichen', 'regulären')}\n"
                "Für Kinder wird am Dienstag eine Führung angeboten."
            ),
        }
        article_case: dict[str, _Json] = {
            "case_id": "library-wording",
            "article": original,
            "comparison_sources": [comparison],
        }
        article = ArticleReport.model_validate_json(
            self._run(article_case, _OllamaReplies(claims=(_FIRST_CLAIM,)))
        )
        self.assertEqual(len(article.shared_wording.matches), 1)
        self.assertIsNone(article.claims[0].review.shared_wording)
        self.assertEqual(len(article.claims[0].source_comparison), 2)

        claim_case: dict[str, _Json] = {
            "case_id": "library-wording",
            "claim": _FIRST_CLAIM,
            "sources": [original, comparison],
        }
        claim = RunReport.model_validate_json(self._run(claim_case, _OllamaReplies()))
        self.assertEqual(claim.shared_wording, article.shared_wording)
        self.assertEqual(claim.source_diff, article.claims[0].review.source_diff)

    def test_manual_interest_evidence_runs_five_models(self) -> None:
        """Expose verified ownership evidence and unknown fields in the article report."""
        article: dict[str, _Json] = {
            **_ARTICLE,
            "publisher": "Morgenpost",
            "authors": ["Lea Winter"],
        }
        imprint = {
            **_ARTICLE,
            "source_id": "imprint",
            "version_id": "imprint-v1",
            "text": "Die Morgenpost gehört zur Mediengruppe Nord.",
        }
        case: dict[str, _Json] = {
            "case_id": "library-interests",
            "article": article,
            "interest_evidence": [{"target_source_id": "article", "source": imprint}],
        }
        replies = _OllamaReplies(claims=(_FIRST_CLAIM,))
        report = ArticleReport.model_validate_json(self._run(case, replies))
        self.assertEqual(replies.interest_subjects, ["Morgenpost"] * 5)
        self.assertIsNotNone(report.interests)
        if report.interests is None:
            return
        self.assertEqual(report.interests.status, "complete")
        source = report.interests.sources[0]
        self.assertEqual(len(source.assessments), 5)
        finding = source.assessments[0].findings[0]
        self.assertEqual(finding.category, "ownership")
        self.assertEqual(finding.evidence.source_id, "imprint")
        self.assertTrue(finding.evidence.verified)
        self.assertIn("funding", source.unresolved_categories)
        if report.editorial is not None:
            self.assertEqual(report.editorial.interest_status, "complete")
            self.assertEqual(report.editorial.interest_sources_with_findings, ["article"])

    def test_interest_search_fetches_evidence_for_original_article(self) -> None:
        """Discover affiliation evidence, retain its query, and report unavailable categories."""
        article_html = _ARTICLE_HTML.replace(
            "</head>",
            '<meta property="og:site_name" content="Morgenpost">'
            '<meta name="author" content="Lea Winter"></head>',
        )
        queries: list[str] = []
        replies = _OllamaReplies(claims=(_FIRST_CLAIM,))

        def web(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/link":
                return _html_response(article_html)
            if request.url.path == "/search":
                query = request.url.params["q"]
                queries.append(query)
                if "Morgenpost" in query:
                    return httpx.Response(
                        200,
                        json={"results": [{"url": "https://news.example.test/imprint"}]},
                    )
                return httpx.Response(200, json={"results": []})
            if request.url.path == "/imprint":
                return _html_response(
                    "<article>Die Morgenpost gehört zur Mediengruppe Nord.</article>"
                )
            self.fail(f"Unexpected path {request.url.path}")
            return httpx.Response(500)

        case: dict[str, _Json] = {
            "case_id": "library-interests",
            "article_url": _ARTICLE_URL,
        }
        report = ArticleUrlReport.model_validate_json(
            self._run(
                case,
                replies,
                web=web,
                search_enabled=True,
                interests_enabled=True,
            )
        )
        self.assertEqual(len(queries), 3)
        self.assertIn('"Morgenpost" Eigentümer Finanzierung Impressum', queries)
        self.assertIn('"Lea Winter" Arbeitgeber Verbindung', queries)
        self.assertEqual(replies.interest_subjects, ["Morgenpost"] * 5)
        self.assertEqual(
            [item.source_id for item in report.retrievals],
            [
                "article",
                "interest-evidence-1",
            ],
        )
        self.assertIsNotNone(report.review)
        if report.review is None or report.review.interests is None:
            return
        interest = report.review.interests
        self.assertEqual(interest.sources[0].source.publisher, "Morgenpost")
        self.assertEqual(interest.sources[0].source.authors, ["Lea Winter"])
        self.assertEqual(len(interest.sources[0].searches), 2)
        self.assertEqual(len(interest.sources[0].retrievals), 1)
        self.assertEqual(
            interest.sources[0].assessments[0].findings[0].evidence.source_id, "interest-evidence-1"
        )

    def test_explicit_interest_url_runs_without_automatic_search(self) -> None:
        """Keep evidence for an available source when a requested comparison fails."""
        article_html = _ARTICLE_HTML.replace(
            "</head>", '<meta property="og:site_name" content="Morgenpost"></head>'
        )
        replies = _OllamaReplies(claims=(_FIRST_CLAIM,))

        def web(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/link":
                return _html_response(article_html)
            if request.url.path == "/unavailable":
                return httpx.Response(503)
            if request.url.path == "/imprint":
                return _html_response(
                    "<article>Die Morgenpost gehört zur Mediengruppe Nord.</article>"
                )
            self.fail(f"Unexpected path {request.url.path}")
            return httpx.Response(500)

        url = "https://news.example.test/imprint"
        case: dict[str, _Json] = {
            "case_id": "explicit-interest",
            "article_url": _ARTICLE_URL,
            "comparison_urls": ["https://news.example.test/unavailable"],
            "interest_urls": [
                {"target_source_id": "article", "url": url},
                {"target_source_id": "comparison-1", "url": "https://news.example.test/not-used"},
            ],
        }
        report = ArticleUrlReport.model_validate_json(self._run(case, replies, web=web))
        self.assertEqual(report.status, "partial")
        self.assertEqual(report.retrievals[1].status, "failed")
        self.assertEqual(replies.interest_subjects, ["Morgenpost"] * 5)
        self.assertEqual(str(report.retrievals[-1].requested_url), url)
        interests = report.review.interests if report.review is not None else None
        self.assertIsNotNone(interests)
        if interests is not None:
            self.assertEqual(interests.status, "complete")
            self.assertEqual(interests.sources[0].searches, [])
            self.assertEqual(str(interests.sources[0].evidence_sources[0].url), url)

    def test_source_diff_separates_shared_and_distinct_cited_evidence(self) -> None:
        """Group a repeated release and show original reporting, qualification, and gaps."""
        release = (
            "Nach einer sechsmonatigen Sanierung kann die Bibliothek wieder Besucherinnen "
            "und Besucher aus dem gesamten Landkreis zu den üblichen Zeiten empfangen."
        )
        reporting = "Eine Reporterin beobachtete bei der Eröffnung eine lange Schlange."
        qualification = "Die Kinderabteilung bleibt wegen eines Wasserschadens noch geschlossen."
        variant = release.replace("üblichen", "verkürzten")
        mixed_quote = f"{release}\n{reporting}"
        findings: dict[str, tuple[str, str, list[str]]] = {
            "article": ("supports", "Die Mitteilung kündigt die Wiedereröffnung an.", [release]),
            "comparison": (
                "supports",
                "Die Reporterin beobachtete die Eröffnung selbst.",
                [release, reporting, mixed_quote, "Ein erfundenes Zitat."],
            ),
            "third": (
                "qualifies",
                "Die Öffnung gilt nur für Teile der Bibliothek und für kürzere Zeiten.",
                [variant, qualification],
            ),
            "excerpt": ("omits", "Der kurze Auszug enthält keine Angaben zur Öffnung.", []),
        }

        def assess(claim: str, sources: list[dict[str, _Json]]) -> dict[str, _Json]:
            result: list[_Json] = []
            for source in sources:
                source_id = cast("str", source["source_id"])
                row: tuple[str, str, list[str]] = findings[source_id]
                if claim == _SECOND_CLAIM:
                    row = (
                        ("supports", "Der Artikel bestätigt den freien Eintritt.", [_SECOND_CLAIM])
                        if source_id == "article"
                        else ("not_assessable", "Keine Aussage zum Eintritt.", [])
                    )
                relation, reasoning, quotes = row
                result.append(
                    {
                        "source_id": source_id,
                        "relation": relation,
                        "reasoning": reasoning,
                        "quotes": [
                            {"source_id": source_id, "locator": "Absatz", "text": text}
                            for text in quotes
                        ],
                    }
                )
            return {"summary": "Geprüft.", "open_questions": [], "findings": result}

        original = {
            **_ARTICLE,
            "text": f"{_FIRST_CLAIM}\n{release}\n{_SECOND_CLAIM}\n{_SECOND_CLAIM}",
        }
        second: dict[str, _Json] = {
            **_COMPARISON,
            "text": mixed_quote,
            "published_at": {"value": "2024-03-04"},
            "updated_at": {"value": "2024-03-05"},
        }
        third = {**_COMPARISON, "source_id": "third", "text": f"{variant}\n{qualification}"}
        excerpt = {
            **_COMPARISON,
            "source_id": "excerpt",
            "text": "Auszug mit dem Namen der Bibliothek.",
            "text_is_complete": False,
        }
        case: dict[str, _Json] = {
            "case_id": "library-diff",
            "article": original,
            "comparison_sources": [second, third, excerpt],
        }
        replies = _OllamaReplies()
        with patch.object(_OllamaReplies, "_assess", new=staticmethod(assess)):
            report = ArticleReport.model_validate_json(self._run(case, replies))
        comparison = report.claims[0].review.source_diff
        first_row, second_row, third_row, excerpt_row = comparison.sources
        self.assertIsNotNone(second_row.source.published_at)
        self.assertIsNotNone(second_row.source.updated_at)
        self.assertEqual(len(first_row.judgments), 5)
        self.assertEqual(third_row.judgments[0].relation, "qualifies")
        self.assertEqual(excerpt_row.judgments[0].relation, "not_assessable")
        self.assertEqual(excerpt_row.judgments[0].evidence_ids, [])

        evidence = {item.text: item for item in comparison.evidence}
        self.assertEqual(set(evidence), {release, reporting, mixed_quote, variant, qualification})
        repeated = evidence[release]
        self.assertEqual(repeated.kind, "shared_wording")
        self.assertEqual([item.source_id for item in repeated.citations], ["article", "comparison"])
        self.assertEqual(first_row.judgments[0].evidence_ids, [repeated.evidence_id])
        self.assertEqual(
            second_row.judgments[0].evidence_ids,
            [
                repeated.evidence_id,
                evidence[reporting].evidence_id,
                evidence[mixed_quote].evidence_id,
            ],
        )
        self.assertEqual(
            third_row.judgments[0].evidence_ids,
            [evidence[variant].evidence_id, evidence[qualification].evidence_id],
        )
        self.assertEqual(evidence[variant].kind, "source_specific")
        self.assertTrue(evidence[variant].citations[0].shared_wording_match_indexes)
        self.assertEqual(evidence[mixed_quote].kind, "source_specific")
        self.assertTrue(evidence[mixed_quote].citations[0].shared_wording_match_indexes)
        self.assertEqual(evidence[reporting].citations[0].shared_wording_match_indexes, [])

        second_claim = report.claims[1].review.source_diff
        self.assertEqual([item.text for item in second_claim.evidence], [_SECOND_CLAIM])
        repeated_in_article = second_claim.evidence[0].citations[0]
        self.assertIsNone(repeated_in_article.start)
        self.assertIsNone(repeated_in_article.end)
        self.assertEqual(repeated_in_article.shared_wording_match_indexes, [])
        if report.editorial is None:
            self.fail("The editorial report must identify which passages models received.")
        self.assertEqual(len(report.editorial.claims[0].comparison_evidence_ids), 5)
        self.assertEqual(len(report.editorial.claims[0].evidence_shown_to_models), 3)
        tasks = _json_rows(replies.editorial_tasks[0]["editorial_claims"])
        passages = _json_rows(tasks[0]["comparison_evidence"])
        by_id = {cast("str", passage["evidence_id"]): passage for passage in passages}
        self.assertTrue(by_id[repeated.evidence_id]["shared_wording"])
        self.assertFalse(by_id[evidence[reporting].evidence_id]["shared_wording"])

    def test_declared_dates_reach_models_and_report(self) -> None:
        """Keep publisher dates and capture time distinct across the full comparison."""
        replies = _OllamaReplies(claims=(_FIRST_CLAIM,))
        publication = {"value": "2024-03-04", "provenance": "json_ld"}
        update = {"value": "2024-03-07T10:30:00+01:00", "provenance": "open_graph"}

        def web(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/link":
                metadata = (
                    '<script type="application/ld+json">'
                    '{"@type":"NewsArticle","datePublished":"2024-03-04"}'
                    "</script>"
                )
                return _html_response(_ARTICLE_HTML.replace("</head>", metadata + "</head>"))
            metadata = '<meta property="article:modified_time" content="2024-03-07T10:30:00+01:00">'
            return _html_response(_COMPARISON_HTML.replace("</head>", metadata + "</head>"))

        case: dict[str, _Json] = {
            "case_id": "library-dates",
            "article_url": _ARTICLE_URL,
            "comparison_urls": [_COMPARISON_URL],
        }
        report = ArticleUrlReport.model_validate_json(self._run(case, replies, web=web))
        if report.review is None:
            self.fail("The fixture must produce a review.")
        original, comparison = report.review.sources
        self.assertIsNotNone(original.published_at)
        self.assertIsNotNone(comparison.updated_at)
        if original.published_at is not None and comparison.updated_at is not None:
            self.assertEqual(original.published_at.model_dump(mode="json"), publication)
            self.assertEqual(comparison.updated_at.model_dump(mode="json"), update)
            self.assertNotEqual(original.captured_at.date().isoformat(), publication["value"])
        self.assertIsNone(original.updated_at)
        self.assertIsNone(comparison.published_at)
        self.assertEqual(replies.extraction_sources[0]["published_at"], publication)
        self.assertEqual(len(replies.assessment_sources), 5)
        self.assertEqual(len(replies.peer_review_sources), 5)
        for sources in [*replies.assessment_sources, *replies.peer_review_sources]:
            self.assertEqual(sources[0]["published_at"], publication)
            self.assertEqual(sources[1]["updated_at"], update)
        task = replies.editorial_tasks[0]
        self.assertEqual(task["original_published_at"], publication["value"])
        entries = _json_rows(task["editorial_claims"])
        evidence = _json_rows(entries[0]["comparison_evidence"])
        citations = _json_rows(evidence[0]["citations"])
        self.assertEqual(citations[0]["updated_at"], update["value"])

    def test_manual_urls_take_precedence_over_configured_discovery(self) -> None:
        """Review explicitly selected sources without sending search queries."""
        replies = _OllamaReplies(claims=(_FIRST_CLAIM,))

        def web(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/link":
                return _html_response(_ARTICLE_HTML)
            self.assertEqual(request.url.path, "/library")
            return _html_response(_COMPARISON_HTML)

        case: dict[str, _Json] = {
            "case_id": "manual-library",
            "article_url": _ARTICLE_URL,
            "comparison_urls": [_COMPARISON_URL],
        }
        output = self._run(case, replies, web=web, search_enabled=True)
        self.assertNotIn(b'"discovery"', output)
        report = ArticleUrlReport.model_validate_json(output)
        self.assertEqual(report.status, "complete")
        self.assertEqual(len(report.retrievals), 2)

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
