"""Exercise real loopback requests and persisted runs with controlled analysis stages."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from hashlib import sha256
from pathlib import Path
from threading import Event, Thread
from unittest.mock import AsyncMock, patch

import httpx

from quellenlot_agents.article import ArticleProgress
from quellenlot_agents.config import ModelConfig, WorkflowConfig
from quellenlot_agents.local_ui import LocalServer
from quellenlot_agents.models import ArticleUrlInput, ArticleUrlReport, SourceRetrieval
from quellenlot_agents.studies import ClaimStudyReport

_CONFIG = WorkflowConfig(
    models=[ModelConfig(id=f"local-{i}", model=f"model-{i}") for i in range(5)]
)
_CASE = {
    "case_id": "browser-form",
    "article_url": "https://example.org/article",
    "question": "Welche Frage beantwortet der Artikel?",
}


class LocalUiTests(unittest.TestCase):
    """Verify the private browser API and storage across server instances."""

    def test_authenticated_https_proxy_origin_is_restricted(self) -> None:
        """An external HTTPS origin works without weakening loopback protections."""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            assets = Path("web")
            for invalid in (
                "http://example.org",
                "https://localhost",
                "https://example.org/path",
                "https://user:pass@example.org",
                "https://example.org?query=1",
            ):
                with self.subTest(origin=invalid), self.assertRaises(ValueError):
                    LocalServer(0, assets, directory, _CONFIG, public_origin=invalid)
            with (
                LocalServer(
                    0, assets, directory, _CONFIG, public_origin="https://facts.example.org"
                ) as server,
                httpx.Client(base_url=server.origin, timeout=4, trust_env=False) as client,
            ):
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    trusted = {"Host": "facts.example.org", "Origin": "https://facts.example.org"}
                    self.assertEqual(client.get("/", headers=trusted).status_code, 200)
                    self.assertEqual(client.get("/api/runs", headers=trusted).status_code, 200)
                    self.assertEqual(
                        client.post("/api/runs", json={}, headers=trusted).status_code, 400
                    )
                    self.assertEqual(
                        client.post(
                            "/api/runs",
                            json=_CASE,
                            headers={**trusted, "Origin": "https://evil.example.org"},
                        ).status_code,
                        403,
                    )
                    self.assertEqual(
                        client.post(
                            "/api/runs",
                            json=_CASE,
                            headers={**trusted, "Sec-Fetch-Site": "cross-site"},
                        ).status_code,
                        403,
                    )
                    self.assertEqual(
                        client.post(
                            "/api/runs",
                            json=_CASE,
                            headers={"Host": "facts.example.org"},
                        ).status_code,
                        403,
                    )
                    self.assertEqual(
                        client.get("/api/runs", headers={"Host": "evil.example.org"}).status_code,
                        403,
                    )
                    self.assertEqual(client.get("/api/runs").status_code, 200)
                finally:
                    server.shutdown()
                    thread.join(timeout=4)

    def test_running_and_reopened_reports_use_the_same_saved_case(self) -> None:
        """Start one job, persist partial results, and reopen them after server restart."""
        checkpoint = Event()
        finish = Event()

        async def stage(
            case: ArticleUrlInput,
            _config: WorkflowConfig,
            *,
            on_progress: ArticleProgress,
        ) -> ArticleUrlReport:
            issue = SourceRetrieval(
                source_id="comparison-1",
                requested_url=case.article_url,
                status="failed",
                detail="Controlled source failure",
            )
            report = ArticleUrlReport(
                case_id=case.case_id,
                question=case.question,
                status="partial",
                retrievals=[issue],
                review=None,
            )
            on_progress("comparison", report)
            checkpoint.set()
            finish.wait(timeout=5)
            return report

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            assets = Path("web")
            with (
                patch("quellenlot_agents.local_ui.run_article_url_comparison", new=stage),
                LocalServer(0, assets, directory, _CONFIG) as server,
                httpx.Client(base_url=server.origin, trust_env=False, timeout=4) as client,
            ):
                worker = Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    response = client.get("/")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["X-Frame-Options"], "DENY")
                    for asset in ("parliament.html", "parliament.js", "parliament-data.js"):
                        self.assertEqual(client.get("/" + asset).status_code, 200)
                    self.assertEqual(client.get("/parliament.css").status_code, 200)
                    blocked_host = client.get("/api/runs", headers={"Host": "example.org"})
                    self.assertEqual(blocked_host.status_code, 403)
                    for headers in ({}, {"Origin": "https://example.org"}):
                        unauthorized = client.post("/api/runs", json=_CASE, headers=headers)
                        self.assertEqual(unauthorized.status_code, 403)
                    headers = {"Origin": server.origin}
                    invalid = client.post("/api/runs", json={"unknown": True}, headers=headers)
                    self.assertEqual(invalid.status_code, 400)
                    started = client.post("/api/runs", json=_CASE, headers=headers)
                    self.assertEqual(started.status_code, 202)
                    run_id = started.json()["run_id"]
                    if not isinstance(run_id, str):
                        self.fail("The start response did not identify the saved run.")
                    url = "/api/runs/" + run_id
                    self.assertTrue(checkpoint.wait(timeout=4))
                    self.assertEqual(client.get(url).json()["stage"], "comparison")
                    duplicate = client.post("/api/runs", json=_CASE, headers=headers)
                    self.assertEqual(duplicate.status_code, 409)
                    report = client.get(url + "/report")
                    self.assertEqual(report.status_code, 200)
                    self.assertEqual(
                        report.json()["retrievals"][0]["detail"], "Controlled source failure"
                    )

                    finish.set()
                    deadline = time.monotonic() + 4
                    completed = client.get(url).json()
                    while completed["status"] == "running" and time.monotonic() < deadline:
                        time.sleep(0.01)
                        completed = client.get(url).json()
                    self.assertEqual(completed["status"], "partial")
                    run_dir = directory / run_id
                    saved = ArticleUrlInput.model_validate_json(
                        (run_dir / "case.json").read_bytes()
                    )
                    self.assertEqual(saved.case_id, run_id)
                    with LocalServer(0, assets, directory, _CONFIG) as reopened:
                        restored = reopened.runs.history()
                        self.assertEqual([run.run_id for run in restored], [run_id])
                        self.assertTrue(restored[0].has_report)
                finally:
                    finish.set()
                    server.shutdown()
                    worker.join(timeout=4)

    def test_interrupted_run_recovers_existing_checkpoint(self) -> None:
        """Expose the last saved checkpoint if a process stopped before recording a result."""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            run_id = "ab" * 16
            folder = directory / run_id
            folder.mkdir()
            record = {
                "run_id": run_id,
                "article_url": _CASE["article_url"],
                "started_at": "2026-11-20T08:00:00Z",
                "stage": "editorial",
                "status": "running",
            }
            (folder / "status.json").write_text(json.dumps(record), encoding="utf-8")
            (folder / "report.json").write_text("{}", encoding="utf-8")
            with LocalServer(0, Path("web"), directory, _CONFIG) as reopened:
                run = reopened.runs.read(folder)
                self.assertEqual(run.status, "interrupted")
                self.assertEqual(run.stage, "editorial")
                self.assertTrue(run.has_report)

    def test_editorial_draft_requires_current_report_and_saved_text(self) -> None:
        """Persist and reopen private edits, rejecting stale versions and incomplete reviews."""
        run_id = "ac" * 16
        draft_url = f"/api/runs/{run_id}/editorial-draft"
        studies_url = f"/api/runs/{run_id}/claims/claim-1/studies"
        claim_text = "Der Zeitraum bleibt offen."
        run_data = {
            "run_id": run_id,
            "article_url": _CASE["article_url"],
            "started_at": "2026-11-20T08:00:00Z",
            "status": "partial",
        }
        finding = {
            "finding_id": "finding-1",
            "source_id": "comparison-1",
            "agent_id": "model-1",
            "relation": "qualifies",
            "evidence_ids": ["quote-1"],
            "reasoning": "Earlier estimate.",
        }
        coverage = {
            "claim_id": "claim-1",
            "review_status": "complete",
            "comparison_evidence_ids": ["quote-1"],
            "evidence_shown_to_models": ["quote-1"],
            "comparison_sources_without_quotes": [],
            "unresolved_dissent_count": 1,
            "unresolved_finding_ids": ["finding-1"],
            "assigned_findings": [finding],
        }
        note = {
            "claim_id": "claim-1",
            "evidence_ids": ["quote-1"],
            "assessment": "Offen.",
            "next_check": None,
            "findings": [
                {"finding_id": "finding-1", "outcome": "unclear", "reasoning": "Zeitpunkt offen."}
            ],
        }
        report = ArticleUrlReport.model_validate_json(
            json.dumps(
                {
                    "case_id": run_id,
                    "question": None,
                    "status": "partial",
                    "retrievals": [],
                    "review": {
                        "case_id": run_id,
                        "question": None,
                        "article_source_id": "article",
                        "sources": [],
                        "status": "partial",
                        "extraction_attempts": [],
                        "claims": [
                            {
                                "claim_id": "claim-1",
                                "article_quote": {
                                    "source_id": "article",
                                    "version_id": "v1",
                                    "locator": "article",
                                    "text": claim_text,
                                    "verified": True,
                                },
                                "source_comparison": [],
                                "review": {
                                    "case_id": run_id,
                                    "claim": claim_text,
                                    "status": "complete",
                                    "limitation": "Fixture",
                                    "sources": [],
                                    "analyses": [],
                                    "reviews": [],
                                    "relation_counts": [],
                                    "unresolved_dissent": [],
                                },
                            },
                        ],
                        "editorial": {
                            "status": "partial",
                            "claims": [coverage],
                            "incomplete_source_ids": [],
                            "retrieval_gaps": [],
                            "discovery_incomplete": False,
                            "interest_status": None,
                            "interest_sources_with_findings": [],
                            "assessments": [
                                {
                                    "agent_id": "model-2",
                                    "model": "second",
                                    "status": "succeeded",
                                    "claims": [note],
                                },
                            ],
                        },
                    },
                }
            )
        )
        original = report.model_dump_json().encode()
        digest = sha256(original).hexdigest()
        change = {
            "review_sha256": digest,
            "revision": 0,
            "text": "Eine Angabe bleibt offen.",
            "action": "save",
        }
        approve = {
            **change,
            "revision": 1,
            "action": "approve",
            "sources_checked": True,
            "open_findings_addressed": True,
        }
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            folder = directory / run_id
            folder.mkdir()
            (folder / "status.json").write_text(json.dumps(run_data), encoding="utf-8")
            report_path = folder / "report.json"
            report_path.write_bytes(original)
            with (
                LocalServer(0, Path("web"), directory, _CONFIG) as server,
                httpx.Client(base_url=server.origin, trust_env=False, timeout=4) as client,
            ):
                worker = Thread(target=server.serve_forever, daemon=True)
                worker.start()
                headers = {"Origin": server.origin}
                try:
                    self.assertIsNone(client.get(draft_url).json())
                    self.assertEqual(client.post(draft_url, json=change).status_code, 403)
                    saved = client.post(draft_url, json=change, headers=headers)
                    self.assertEqual(saved.status_code, 200)
                    self.assertEqual(saved.json()["revision"], 1)
                    self.assertIsNone(saved.json()["approved_at"])
                    self.assertEqual(client.get(draft_url).json(), saved.json())
                    with LocalServer(0, Path("web"), directory, _CONFIG) as reopened:
                        self.assertIsNotNone(reopened.runs.editorial_draft(run_id))
                    stale = client.post(draft_url, json=change, headers=headers)
                    self.assertEqual(stale.status_code, 409)
                    for override in (
                        {"open_findings_addressed": False},
                        {"text": "Ungespeichert."},
                    ):
                        denied = client.post(draft_url, json=approve | override, headers=headers)
                        self.assertEqual(denied.status_code, 409)

                    approved = client.post(draft_url, json=approve, headers=headers)
                    self.assertEqual(approved.status_code, 200)
                    self.assertEqual(approved.json()["review_sha256"], digest)
                    self.assertIsNotNone(approved.json()["approved_at"])
                    self.assertEqual(approved.json()["revision"], 2)

                    result = ClaimStudyReport(
                        claim_id="claim-1",
                        claim=claim_text,
                        queries=[claim_text],
                        status="complete",
                        papers=[],
                    )
                    search = AsyncMock(return_value=result)
                    with patch("quellenlot_agents.local_ui.find_claim_studies", new=search):
                        self.assertIsNone(client.get(studies_url).json())
                        self.assertEqual(client.post(studies_url).status_code, 403)
                        search.assert_not_awaited()
                        studies = client.post(studies_url, headers=headers)
                        self.assertEqual(studies.status_code, 200)
                        search.assert_awaited_once_with("claim-1", claim_text, _CONFIG)
                        self.assertEqual(client.get(studies_url).json(), studies.json())
                    self.assertEqual(report_path.read_bytes(), original)
                    self.assertEqual(client.get(draft_url).json(), approved.json())

                    # A replacement report cannot inherit the previous version's approval.
                    report_path.write_bytes(original + b"\n")
                    self.assertIsNone(client.get(draft_url).json())
                    self.assertEqual(
                        client.post(draft_url, json=approve, headers=headers).status_code, 409
                    )
                    report_path.write_bytes(original)
                    self.assertEqual(client.get(draft_url).json(), approved.json())
                    revised = client.post(
                        draft_url,
                        json=change | {"revision": 2, "text": "Neue Korrektur."},
                        headers=headers,
                    )
                    self.assertEqual(revised.status_code, 200)
                    self.assertIsNone(revised.json()["approved_at"])
                    self.assertEqual(revised.json()["revision"], 3)

                    if report.review is None or report.review.editorial is None:
                        self.fail("Expected a final assessment.")
                    report.review.editorial.assessments[0].claims[0].findings.clear()
                    report_path.write_bytes(report.model_dump_json().encode())
                    self.assertEqual(client.get(draft_url).status_code, 409)
                finally:
                    server.shutdown()
                    worker.join(timeout=4)
