"""Exercise real loopback requests and persisted runs with controlled analysis stages."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

import httpx

from quellenlot_agents.article import ArticleProgress
from quellenlot_agents.config import ModelConfig, WorkflowConfig
from quellenlot_agents.local_ui import LocalServer
from quellenlot_agents.models import ArticleUrlInput, ArticleUrlReport, SourceRetrieval

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
