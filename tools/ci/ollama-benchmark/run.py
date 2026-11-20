"""Measure Quellenlot's serial claim review against a dedicated CPU-only Ollama server."""

import asyncio
import json
import os
import platform
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast
from unittest.mock import patch

import httpx

from quellenlot_agents.config import WorkflowConfig, load_config
from quellenlot_agents.models import CaseInput
from quellenlot_agents.workflow import run_review

ROOT = Path(__file__).resolve().parent
OUTPUT = Path("/results")
API = "http://127.0.0.1:11434/api"
GIB = 1024**3
POST = httpx.AsyncClient.post


class ChatPayload(TypedDict):
    """Provider payload fields used to identify the request."""

    model: str
    format: dict[str, str]


class ModelTag(TypedDict):
    """Ollama registry entry for local model weights."""

    name: str
    digest: str
    size: int
    details: dict[str, str]


class OllamaReply(TypedDict, total=False):
    """Ollama metadata present on a successful generation."""

    eval_count: int
    eval_duration: int
    prompt_eval_count: int
    load_duration: int
    done_reason: str


@dataclass
class Request:
    """Metrics for one attempted analysis or peer review."""

    repeat: int
    model: str
    phase: str
    wall_s: float
    peak_rss_gib: float
    status: str
    http_status: int | None
    generation_tokens: int | None
    generation_tokens_per_s: float | None
    prompt_tokens: int | None
    model_load_s: float | None
    done_reason: str | None


def ollama_rss() -> int:
    """Sample Ollama processes in the benchmark container.

    Returns:
        Combined resident memory in bytes.
    """
    rss = 0
    for child in Path("/proc").iterdir():
        if not child.name.isdecimal():
            continue
        try:
            status = (child / "status").read_text(encoding="utf-8").splitlines()
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
        if status and status[0].split()[-1].startswith(("ollama", "llama-server")):
            rss += next(
                (int(line.split()[1]) * 1024 for line in status if line.startswith("VmRSS:")), 0
            )
    return rss


class Meter:
    """Record real requests while leaving Quellenlot's provider and validation active."""

    def __init__(self) -> None:
        """Initialize the serial request records and repetition counter."""
        self.rows: list[Request] = []
        self.repeat = 0

    async def post(
        self, client: httpx.AsyncClient, url: str, *, json: ChatPayload
    ) -> httpx.Response:
        """Post the production payload and sample Ollama process memory until it returns.

        Args:
            client: HTTP client configured by the production provider.
            url: Local Ollama chat endpoint.
            json: Production prompt, schema and generation options.

        Returns:
            The original Ollama HTTP response for production validation.
        """
        model = json["model"]
        phase = {"DraftAnalysis": "Analysis", "DraftReview": "Peer review"}[json["format"]["title"]]
        start = time.perf_counter()
        rss_samples: list[int] = [ollama_rss()]
        response: httpx.Response | None = None

        async def sample() -> None:
            """Sample while awaiting the real response."""
            while True:
                await asyncio.sleep(0.2)
                rss_samples.append(ollama_rss())

        def record(response: httpx.Response | None) -> None:
            """Record one attempted request after its memory sampler shuts down.

            Args:
                response: Response envelope, when the HTTP request reached Ollama.
            """
            elapsed = time.perf_counter() - start
            rss_samples.append(ollama_rss())
            reply: OllamaReply = (
                cast("OllamaReply", response.json())
                if response is not None and response.is_success
                else {}
            )
            tokens, generation_ns = reply.get("eval_count"), reply.get("eval_duration")
            load_ns = reply.get("load_duration")
            self.rows.append(
                Request(
                    self.repeat,
                    model,
                    phase,
                    elapsed,
                    max(rss_samples) / GIB,
                    "failed",
                    response.status_code if response is not None else None,
                    tokens,
                    tokens * 1e9 / generation_ns
                    if tokens is not None and generation_ns is not None and generation_ns > 0
                    else None,
                    reply.get("prompt_eval_count"),
                    load_ns / 1e9 if load_ns is not None else None,
                    reply.get("done_reason"),
                )
            )
            sys.stdout.write(f"{self.repeat}: {model} / {phase} / {elapsed:.1f} s\n")
            sys.stdout.flush()

        sampler = asyncio.create_task(sample())
        try:
            response = await POST(client, url, json=json)
        except httpx.HTTPError:
            record(None)
            raise
        finally:
            sampler.cancel()
            await asyncio.gather(sampler, return_exceptions=True)
        record(response)
        return response


def available_models() -> dict[str, ModelTag]:
    """Read metadata for locally available model weights.

    Returns:
        Model tags keyed by name with digests, sizes and quantization details.
    """
    response = httpx.get(f"{API}/tags", timeout=10, trust_env=False)
    response.raise_for_status()
    payload = cast("dict[str, list[ModelTag]]", response.json())
    return {item["name"]: item for item in payload["models"]}


def write_json(name: str, content: str) -> None:
    """Write auditable JSON alongside the readable charts.

    Args:
        name: Artifact filename relative to the results folder.
        content: Serialized JSON to write.
    """
    (OUTPUT / name).write_text(content + "\n", encoding="utf-8")


def record_environment(case: CaseInput, config: WorkflowConfig, repetitions: int) -> None:
    """Save information needed to reproduce the benchmark.

    Args:
        case: Fixed claim and source excerpts.
        config: Model order and context size used for inference.
        repetitions: Number of complete workflow runs requested.
    """
    cpu = next(
        (
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name")
        ),
        platform.machine(),
    )
    tags = available_models()
    metadata = {
        "started_at": datetime.now(UTC).isoformat(),
        "commit": os.environ.get("BENCHMARK_COMMIT"),
        "cpu": cpu,
        "cpu_threads_visible": len(os.sched_getaffinity(0)),
        "docker_memory_limit_bytes": os.environ.get("BENCHMARK_MEMORY_BYTES"),
        "case": case.case_id,
        "source_sha256": {source.source_id: source.content_sha256 for source in case.sources},
        "context_tokens": config.context_length,
        "repetitions": repetitions,
        "model_order": [model.model for model in config.models],
        "installed_models": tags,
        "ollama_version": httpx.get(f"{API}/version", timeout=10, trust_env=False).json(),
    }
    write_json("environment.json", json.dumps(metadata, indent=2))


async def benchmark(repetitions: int) -> int:
    """Run the fixed claim review end to end and persist its results.

    Args:
        repetitions: Number of serial workflow runs to attempt.

    Returns:
        Zero if any model response passed production validation, otherwise one.
    """
    config = load_config(ROOT.parent / "config.example.toml")
    case = CaseInput.model_validate_json(
        await asyncio.to_thread((ROOT / "tankrabatt.json").read_bytes)
    )
    models = {model.id: model.model for model in config.models}
    await asyncio.to_thread(record_environment, case, config, repetitions)
    meter = Meter()

    async def timed_post(
        client: httpx.AsyncClient, url: str, *, json: ChatPayload
    ) -> httpx.Response:
        """Forward calls to the current serial benchmark meter.

        Args:
            client: Production HTTP client making the call.
            url: Local Ollama API endpoint.
            json: Unmodified production request payload.

        Returns:
            Ollama HTTP response after collecting request metrics.
        """
        return await meter.post(client, url, json=json)

    durations: list[float] = []
    with patch.object(httpx.AsyncClient, "post", timed_post):
        for repeat in range(1, repetitions + 1):
            meter.repeat = repeat
            start = time.perf_counter()
            report = await run_review(case, config)
            durations.append(time.perf_counter() - start)
            analysis_statuses = {(item.model, "Analysis"): item.status for item in report.analyses}
            review_statuses = {
                (models[item.reviewer_agent_id], "Peer review"): item.status
                for item in report.reviews
            }
            statuses = analysis_statuses | review_statuses
            for row in meter.rows:
                if row.repeat == repeat:
                    row.status = statuses[(row.model, row.phase)]
            (OUTPUT / f"review-{repeat}.json").write_text(
                report.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
            write_json("requests.json", json.dumps([asdict(row) for row in meter.rows], indent=2))
            write_json(
                "workflow.json",
                json.dumps(
                    {"wall_s": durations, "median_wall_s": statistics.median(durations)}, indent=2
                ),
            )
    return int(not any(row.status == "succeeded" for row in meter.rows))


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    raise SystemExit(asyncio.run(benchmark(int(sys.argv[1]))))
