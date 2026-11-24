"""Serve a private browser interface for one local Quellenlot run at a time."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
from collections import Counter
from contextlib import suppress
from datetime import UTC, datetime
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import Annotated, Final, Literal, cast
from uuid import uuid4

from pydantic import Field, StringConstraints, ValidationError

from quellenlot_agents.article import ArticleStage, run_article_url_comparison
from quellenlot_agents.config import WorkflowConfig, load_config
from quellenlot_agents.metrics import collect_model_calls
from quellenlot_agents.models import (
    ArticleUrlInput,
    ArticleUrlReport,
    ContractModel,
    EditorialReport,
)
from quellenlot_agents.studies import ClaimStudyReport, find_claim_studies
from quellenlot_agents.trends import (
    TrendEventQuery,
    TrendQuery,
    TrendUnavailable,
    fetch_news_trend,
    fetch_trend_events,
)

_LOG = logging.getLogger(__name__)
_LOOPBACK: Final = "127.0.0.1"
_JSON: Final = "application/json; charset=utf-8"
_MAX_CASE_BYTES: Final = 256 * 1024
_RUN_PATH: Final = re.compile(r"/api/runs/([0-9a-f]{32})(/report|/editorial-draft)?")
_STUDIES_PATH: Final = re.compile(r"/api/runs/([0-9a-f]{32})/claims/(claim-[1-5])/studies")
_ASSETS: Final = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/parliament.html": ("parliament.html", "text/html; charset=utf-8"),
    "/parliament.js": ("parliament.js", "text/javascript; charset=utf-8"),
    "/parliament-data.js": ("parliament-data.js", "text/javascript; charset=utf-8"),
    "/parliament.css": ("parliament.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/graph.js": ("graph.js", "text/javascript; charset=utf-8"),
    "/trends.js": ("trends.js", "text/javascript; charset=utf-8"),
    "/theme.js": ("theme.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/fonts/IBMPlexMono-Regular.woff2": ("fonts/IBMPlexMono-Regular.woff2", "font/woff2"),
    "/fonts/IBMPlexMono-SemiBold.woff2": ("fonts/IBMPlexMono-SemiBold.woff2", "font/woff2"),
}


class _RunStatus(ContractModel):
    run_id: str
    article_url: str
    started_at: datetime
    status: Literal["running", "complete", "partial", "failed", "no_claims", "interrupted"]
    stage: ArticleStage = "capture"
    has_report: bool = False
    error: str | None = None


_ReportDigest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_EditorialText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]


class _EditorialUpdate(ContractModel):
    review_sha256: _ReportDigest
    revision: int = Field(ge=0)
    text: _EditorialText
    action: Literal["save", "approve"]
    sources_checked: bool = False
    open_findings_addressed: bool = False


class _EditorialDraft(ContractModel):
    review_sha256: _ReportDigest
    revision: int = Field(ge=1)
    text: _EditorialText
    saved_at: datetime
    approved_at: datetime | None = None


class _DraftConflict(ValueError):
    """Reject changes made against a different draft or report."""


class _StudiesBusy(RuntimeError):
    """A local analysis or study search already holds the model slot."""


def _can_review(editorial: EditorialReport | None) -> bool:
    if editorial is None or editorial.status not in {"complete", "partial"}:
        return False
    coverage = [claim for claim in editorial.claims if claim.assigned_findings]
    assigned = {
        claim.claim_id: Counter(finding.finding_id for finding in claim.assigned_findings)
        for claim in coverage
    }
    if not assigned or len(coverage) != len(assigned):
        return False
    if any(count != 1 for findings in assigned.values() for count in findings.values()):
        return False
    reviewers = [item for item in editorial.assessments if item.status == "succeeded"]
    claims = Counter(assigned.keys())
    return bool(reviewers) and all(
        Counter(note.claim_id for note in reviewer.claims) == claims
        and all(
            Counter(finding.finding_id for finding in note.findings) == assigned[note.claim_id]
            for note in reviewer.claims
        )
        for reviewer in reviewers
    )


def _save(path: Path, model: ContractModel) -> None:
    """Replace the previous JSON only after writing the new document."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class _LocalRuns:
    """Keep private result files and enforce one active run in this server."""

    def __init__(self, directory: Path, config: WorkflowConfig) -> None:
        self.directory = directory
        self.config = config
        self._lock = Lock()
        self._active: str | None = None
        self._researching = False

    def start(self, case: ArticleUrlInput) -> _RunStatus | None:
        """Save a new case and start its background analysis."""
        with self._lock:
            if self._active is not None or self._researching:
                return None
            run_id = uuid4().hex
            folder = self.directory / run_id
            folder.mkdir(mode=0o700)
            case = case.model_copy(update={"case_id": run_id})
            status = _RunStatus(
                run_id=run_id,
                article_url=str(case.article_url),
                started_at=datetime.now(UTC),
                status="running",
            )
            _save(folder / "case.json", case)
            _save(folder / "status.json", status)
            self._active = run_id
            try:
                Thread(target=self._run, args=(case, status.model_copy()), daemon=True).start()
            except RuntimeError:
                self._active = None
                raise
            return status

    def _run(self, case: ArticleUrlInput, status: _RunStatus) -> None:
        folder = self.directory / status.run_id

        def progress(stage: ArticleStage, report: ArticleUrlReport | None) -> None:
            if report is not None:
                _save(folder / "report.json", report)
                status.has_report = True
            status.stage = stage
            _save(folder / "status.json", status)

        try:
            with collect_model_calls() as model_calls:
                report = asyncio.run(
                    run_article_url_comparison(case, self.config, on_progress=progress)
                )
            report.model_calls = model_calls
            _save(folder / "report.json", report)
            status.has_report = True
            status.status = report.status
            if (
                report.status == "complete"
                and report.review is not None
                and report.review.editorial is not None
                and report.review.editorial.status
                in {"partial", "failed", "no_comparison_evidence"}
            ):
                status.status = "partial"
        except Exception:
            status.status = "failed"
            status.error = "Die Analyse wurde abgebrochen. Details stehen im Serverprotokoll."
            raise
        finally:
            with self._lock:
                self._active = None
                _save(folder / "status.json", status)

    def read(self, folder: Path) -> _RunStatus:
        """Recover a persisted run, including any checkpoint left after shutdown."""
        with self._lock:
            status = _RunStatus.model_validate_json((folder / "status.json").read_bytes())
            if status.status == "running" and status.run_id != self._active:
                status.status = "interrupted"
            status.has_report = (folder / "report.json").is_file()
            return status

    def editorial_draft(
        self, run_id: str, update: _EditorialUpdate | None = None
    ) -> _EditorialDraft | None:
        """Read or change the draft for the finalized report's exact bytes.

        Args:
            run_id: Identifier of the saved analysis.
            update: Draft save or approval, or None for a read.

        Returns:
            The current draft, or None when that report has no saved draft.

        Raises:
            _DraftConflict: The report or draft changed, or approval conditions are unmet.
        """
        folder = self.directory / run_id
        with self._lock:
            status = _RunStatus.model_validate_json((folder / "status.json").read_bytes())
            if status.status not in {"complete", "partial"}:
                msg = "Für diesen Lauf liegt noch kein abgeschlossener Prüfbericht vor."
                raise _DraftConflict(msg)
            report_bytes = (folder / "report.json").read_bytes()
            digest = sha256(report_bytes).hexdigest()
            if update is not None and digest != update.review_sha256:
                msg = "Der Prüfbericht hat sich geändert. Öffne ihn erneut."
                raise _DraftConflict(msg)
            report = ArticleUrlReport.model_validate_json(report_bytes)
            if (
                report.case_id != run_id
                or report.review is None
                or not _can_review(report.review.editorial)
            ):
                msg = "Der Bericht enthält keine auswertbare Schlussprüfung."
                raise _DraftConflict(msg)
            path = folder / f"editorial-{digest}.json"
            draft = (
                _EditorialDraft.model_validate_json(path.read_bytes()) if path.exists() else None
            )
            if update is None:
                return draft
            if update.revision != (draft.revision if draft else 0):
                msg = (
                    "Der Entwurf wurde in einem anderen Fenster geändert. Öffne den Bericht erneut."
                )
                raise _DraftConflict(msg)
            approval = update.action == "approve"
            if approval and (
                draft is None
                or update.text != draft.text
                or not update.sources_checked
                or not update.open_findings_addressed
            ):
                msg = "Speichere den Entwurf und bestätige beide Prüfpunkte."
                raise _DraftConflict(msg)
            if (
                draft is not None
                and update.text == draft.text
                and (not approval or draft.approved_at)
            ):
                return draft
            now = datetime.now(UTC)
            saved = _EditorialDraft(
                review_sha256=digest,
                revision=update.revision + 1,
                text=update.text,
                saved_at=draft.saved_at if approval and draft is not None else now,
                approved_at=now if approval else None,
            )
            _save(path, saved)
            return saved

    def history(self) -> list[_RunStatus]:
        """List persisted local runs, skipping records without valid metadata."""
        runs: list[_RunStatus] = []
        for folder in self.directory.iterdir():
            if _RUN_PATH.fullmatch(f"/api/runs/{folder.name}") is None or not folder.is_dir():
                continue
            try:
                runs.append(self.read(folder))
            except (OSError, ValidationError):
                continue
        return sorted(runs, key=lambda run: run.started_at, reverse=True)

    def studies(self, run_id: str, claim_id: str, *, start: bool) -> ClaimStudyReport | None:
        """Read or run a separate research assessment for a saved claim."""
        folder = self.directory / run_id
        path = folder / f"studies-{claim_id}.json"
        if not start:
            return (
                ClaimStudyReport.model_validate_json(path.read_bytes()) if path.exists() else None
            )
        with self._lock:
            if self._active is not None or self._researching:
                msg = "Es läuft bereits eine Analyse oder Studiensuche."
                raise _StudiesBusy(msg)
            report = ArticleUrlReport.model_validate_json((folder / "report.json").read_bytes())
            claims = report.review.claims if report.review and report.case_id == run_id else []
            claim = next((item for item in claims if item.claim_id == claim_id), None)
            if claim is None:
                msg = "Die Aussage wurde im gespeicherten Bericht nicht gefunden."
                raise FileNotFoundError(msg)
            self._researching = True
        try:
            studies = asyncio.run(find_claim_studies(claim_id, claim.review.claim, self.config))
            _save(path, studies)
            return studies
        finally:
            with self._lock:
                self._researching = False


class LocalServer(ThreadingHTTPServer):
    """Serve the browser client and its local review data over loopback."""

    def __init__(self, port: int, assets: Path, directory: Path, config: WorkflowConfig) -> None:
        """Bind a local server to the selected port.

        Args:
            port: Loopback TCP port, or zero to request an available port.
            assets: Directory holding the browser interface files.
            directory: Existing directory for private run records.
            config: Model and search settings used by the article workflow.
        """
        self.assets = assets
        self.runs = _LocalRuns(directory, config)
        super().__init__((_LOOPBACK, port), _LocalHandler)

    @property
    def origin(self) -> str:
        """Return the only host and port that can reach the local browser API.

        Returns:
            The browser origin of this loopback server.
        """
        return f"http://{_LOOPBACK}:{self.server_port}"


class _LocalHandler(BaseHTTPRequestHandler):
    def _send(self, status: HTTPStatus, body: bytes, content_type: str = _JSON) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._send(status, json.dumps({"error": message}).encode("utf-8"))

    def _authorized(self, *, mutation: bool = False) -> bool:
        origin = cast("LocalServer", self.server).origin
        request_origin = self.headers.get("Origin")
        if (
            self.headers.get("Host") == origin.removeprefix("http://")
            and (request_origin == origin or (not mutation and request_origin is None))
            and self.headers.get("Sec-Fetch-Site") != "cross-site"
        ):
            return True
        self._error(HTTPStatus.FORBIDDEN, "Diese Anfrage muss von der lokalen Oberfläche kommen.")
        return False

    def do_GET(self) -> None:
        """Serve the interface or a local run resource."""
        if not self._authorized():
            return
        server = cast("LocalServer", self.server)
        path = self.path.split("?", 1)[0]
        asset = _ASSETS.get(path)
        run_path = _RUN_PATH.fullmatch(path)
        studies_path = _STUDIES_PATH.fullmatch(path)
        if studies_path is not None:
            self._serve_studies(studies_path[1], studies_path[2], start=False)
            return
        try:
            if asset is not None:
                filename, content_type = asset
                self._send(HTTPStatus.OK, (server.assets / filename).read_bytes(), content_type)
            elif path == "/api/runs":
                body = [status.model_dump(mode="json") for status in server.runs.history()]
                self._send(HTTPStatus.OK, json.dumps(body).encode("utf-8"))
            elif run_path is not None:
                run_id, resource = run_path.groups()
                folder = server.runs.directory / run_id
                if resource == "/editorial-draft":
                    self._send_draft(server.runs.editorial_draft(run_id))
                elif resource == "/report":
                    self._send(HTTPStatus.OK, (folder / "report.json").read_bytes())
                else:
                    self._send(HTTPStatus.OK, server.runs.read(folder).model_dump_json().encode())
            else:
                self._error(HTTPStatus.NOT_FOUND, "Eintrag nicht gefunden.")
        except _DraftConflict as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except FileNotFoundError:
            self._error(HTTPStatus.NOT_FOUND, "Eintrag nicht gefunden.")
        except (OSError, ValidationError):
            _LOG.exception("Could not read local resource")
            self._error(
                HTTPStatus.INTERNAL_SERVER_ERROR, "Der lokale Eintrag konnte nicht gelesen werden."
            )

    def _send_draft(self, draft: _EditorialDraft | None) -> None:
        body = draft.model_dump_json().encode("utf-8") if draft is not None else b"null"
        self._send(HTTPStatus.OK, body)

    def do_POST(self) -> None:
        """Handle an analysis, study lookup, editorial draft, or coverage request."""
        if not self._authorized(mutation=True):
            return
        studies_path = _STUDIES_PATH.fullmatch(self.path)
        if studies_path is not None:
            self._serve_studies(studies_path[1], studies_path[2], start=True)
            return
        run_path = _RUN_PATH.fullmatch(self.path)
        draft_run_id = (
            run_path.group(1)
            if run_path is not None and run_path.group(2) == "/editorial-draft"
            else None
        )
        if (
            self.path not in {"/api/runs", "/api/news-trend", "/api/trend-events"}
            and draft_run_id is None
        ):
            self._error(HTTPStatus.NOT_FOUND, "Eintrag nicht gefunden.")
            return
        if self.headers.get_content_type() != "application/json":
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Die Anfrage muss JSON enthalten.")
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if not 0 < size <= _MAX_CASE_BYTES:
            self._error(HTTPStatus.BAD_REQUEST, "Die Anfrage ist leer oder zu groß.")
            return
        body = self.rfile.read(size)
        if self.path == "/api/news-trend":
            self._news_trend(body)
        elif self.path == "/api/trend-events":
            self._trend_events(body)
        elif draft_run_id is not None:
            self._update_editorial_draft(draft_run_id, body)
        else:
            self._start_run(body)

    def _news_trend(self, body: bytes) -> None:
        try:
            query = TrendQuery.model_validate_json(body)
        except ValidationError:
            self._error(HTTPStatus.BAD_REQUEST, "Gib einen Suchbegriff mit 3 bis 120 Zeichen ein.")
            return
        try:
            trend = fetch_news_trend(query)
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except TrendUnavailable as exc:
            self._error(HTTPStatus.BAD_GATEWAY, str(exc))
        else:
            self._send(HTTPStatus.OK, trend.model_dump_json().encode("utf-8"))

    def _trend_events(self, body: bytes) -> None:
        try:
            query = TrendEventQuery.model_validate_json(body)
        except ValidationError:
            self._error(HTTPStatus.BAD_REQUEST, "Gib einen Suchbegriff und ein gültiges Datum ein.")
            return
        try:
            events = fetch_trend_events(query)
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except TrendUnavailable as exc:
            self._error(HTTPStatus.BAD_GATEWAY, str(exc))
        else:
            self._send(HTTPStatus.OK, events.model_dump_json().encode("utf-8"))

    def _update_editorial_draft(self, run_id: str, body: bytes) -> None:
        try:
            update = _EditorialUpdate.model_validate_json(body)
        except ValidationError:
            self._error(HTTPStatus.BAD_REQUEST, "Der Entwurf enthält ungültige Eingaben.")
            return
        try:
            self._send_draft(cast("LocalServer", self.server).runs.editorial_draft(run_id, update))
        except _DraftConflict as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except FileNotFoundError:
            self._error(HTTPStatus.NOT_FOUND, "Eintrag nicht gefunden.")
        except (OSError, ValidationError):
            _LOG.exception("Could not save editorial draft")
            self._error(
                HTTPStatus.INTERNAL_SERVER_ERROR, "Der Entwurf konnte nicht gespeichert werden."
            )

    def _serve_studies(self, run_id: str, claim_id: str, *, start: bool) -> None:
        try:
            report = cast("LocalServer", self.server).runs.studies(run_id, claim_id, start=start)
        except _StudiesBusy as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except FileNotFoundError:
            self._error(HTTPStatus.NOT_FOUND, "Die gespeicherte Aussage wurde nicht gefunden.")
        except (OSError, ValidationError):
            _LOG.exception("Could not access claim studies")
            self._error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "Die Studiensuche konnte nicht gespeichert werden.",
            )
        else:
            self._send(HTTPStatus.OK, report.model_dump_json().encode() if report else b"null")

    def _start_run(self, body: bytes) -> None:
        try:
            case = ArticleUrlInput.model_validate_json(body)
        except ValidationError:
            self._error(HTTPStatus.BAD_REQUEST, "Die Anfrage enthält ungültige Eingaben.")
            return
        try:
            status = cast("LocalServer", self.server).runs.start(case)
        except (OSError, RuntimeError):
            _LOG.exception("Could not start local run")
            self._error(
                HTTPStatus.INTERNAL_SERVER_ERROR, "Die Analyse konnte nicht gestartet werden."
            )
            return
        if status is None:
            self._error(HTTPStatus.CONFLICT, "Es läuft bereits eine Analyse oder Studiensuche.")
            return
        self._send(HTTPStatus.ACCEPTED, status.model_dump_json().encode("utf-8"))


def main() -> None:
    """Start the local browser server with a model configuration and run directory."""
    parser = argparse.ArgumentParser(description="Serve Quellenlot on the local machine.")
    parser.add_argument("--config", type=Path, required=True, help="TOML file with five models.")
    parser.add_argument(
        "--web-dir", type=Path, default=Path("web"), help="Checkout's web directory."
    )
    parser.add_argument("--port", type=int, default=8765, help="Local browser port.")
    data_home = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local/share"))
    parser.add_argument("--runs-dir", type=Path, default=data_home / "quellenlot/runs")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        assets = cast("Path", args.web_dir).resolve()
        directory = cast("Path", args.runs_dir).resolve()
        if not (assets / "index.html").is_file():
            parser.error("Pass --web-dir or start from the Quellenlot checkout.")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        server = LocalServer(args.port, assets, directory, config)
    except (OSError, ValueError, OverflowError) as exc:
        parser.error(str(exc))
    with server:
        _LOG.warning("Open %s in your browser. Runs are saved under %s.", server.origin, directory)
        with suppress(KeyboardInterrupt):
            server.serve_forever()


if __name__ == "__main__":
    main()
