"""Draw the benchmark overview as a standalone, printable SVG."""

import json
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Literal, TypedDict, cast

OUTPUT = Path("/results")
Phase = Literal["Analysis", "Peer review"]
Metric = Literal["wall_s", "generation_tokens_per_s", "peak_rss_gib", "status"]
PHASES: tuple[tuple[Phase, str], ...] = (("Analysis", "#137564"), ("Peer review", "#6540a4"))


class Row(TypedDict):
    """Request fields used by the chart."""

    model: str
    phase: Phase
    wall_s: float
    peak_rss_gib: float
    generation_tokens_per_s: float | None
    status: str


class Environment(TypedDict):
    """Execution information displayed above the plots."""

    cpu: str
    context_tokens: int
    repetitions: int
    model_order: list[str]


@dataclass(frozen=True)
class Series:
    """One plotted summary and the underlying sampled requests."""

    center: float | None
    samples: Sequence[float]


def series(rows: Sequence[Row], metric: Metric) -> Series:
    """Aggregate requests for one model and workflow phase.

    Args:
        rows: Attempted requests for a given model and phase.
        metric: Field displayed in the current panel.

    Returns:
        A plotted value and its underlying measurements, where applicable.
    """
    valid = [row for row in rows if row["status"] == "succeeded"]
    if metric == "status":
        return Series(float(len(valid)), ())
    if metric == "peak_rss_gib":
        ram = [row["peak_rss_gib"] for row in rows]
        return Series(max(ram, default=None), ram)
    if metric == "wall_s":
        values = [row["wall_s"] for row in valid]
    else:
        values = [speed for row in valid if (speed := row["generation_tokens_per_s"]) is not None]
    return Series(statistics.median(values) if values else None, values)


def panel(
    title: str,
    subtitle: str,
    metric: Metric,
    rows: list[Row],
    environment: Environment,
) -> str:
    """Draw a compact horizontal bar chart with direct labels.

    Args:
        title: Metric name.
        subtitle: Units and aggregation.
        metric: Request field to measure.
        rows: Recorded model calls across all repetitions.
        environment: Model order and planned sample count.

    Returns:
        SVG content for a single chart bound to its own coordinate system.
    """
    models = environment["model_order"]
    repeats = environment["repetitions"]
    grouped = {
        (model, phase): series(
            [r for r in rows if r["model"] == model and r["phase"] == phase], metric
        )
        for model in models
        for phase, _ in PHASES
    }
    maximum = max(
        (max([item.center or 0, *item.samples]) for item in grouped.values()),
        default=1,
    )
    limit = float(repeats) if metric == "status" else max(maximum, 0.1)
    xstart = 196
    scale = 345 / limit
    result = [
        '<rect width="638" height="316" rx="10" fill="#f7f9fb" stroke="#dbe2ea"/>',
        f'<text x="18" y="29" class="heading">{escape(title)}</text>',
        f'<text x="18" y="50" class="muted">{escape(subtitle)}</text>',
    ]
    ticks = repeats if metric == "status" else 4
    for tick in range(ticks + 1):
        value = tick * limit / ticks
        x = xstart + value * scale
        label = f"{value:.0f}" if metric == "status" else f"{value:.3g}"
        result.extend(
            (
                f'<path d="M{x:.2f} 61v223" stroke="#dce2e8"/>',
                f'<text x="{x:.2f}" y="302" text-anchor="middle" class="muted">{label}</text>',
            )
        )
    for index, model in enumerate(models):
        y = 78 + index * 44
        result.append(f'<text x="18" y="{y + 13}" class="model">{escape(model)}</text>')
        for phase_index, (phase, color) in enumerate(PHASES):
            item = grouped[(model, phase)]
            y_bar = y + phase_index * 16
            if item.center is None:
                result.append(f'<text x="{xstart + 4}" y="{y_bar + 10}" class="muted">—</text>')
                continue
            width = item.center * scale
            result.append(
                f'<rect x="{xstart}" y="{y_bar}" width="{width:.2f}" height="11" fill="{color}"/>'
            )
            for value in item.samples:
                x = xstart + value * scale
                result.append(
                    f'<circle cx="{x:.2f}" cy="{y_bar + 5.5}" r="3.4" '
                    f'fill="white" stroke="{color}"/>'
                )
            x = xstart + max([item.center, *item.samples]) * scale + 7
            label = f"{item.center:.0f}/{repeats}" if metric == "status" else f"{item.center:.1f}"
            result.append(f'<text x="{x:.2f}" y="{y_bar + 10}" class="value">{label}</text>')
    return "\n".join(result)


def render() -> None:
    """Write the four-panel performance and response-coverage figure."""
    rows = cast("list[Row]", json.loads((OUTPUT / "requests.json").read_text(encoding="utf-8")))
    info = cast(
        "Environment", json.loads((OUTPUT / "environment.json").read_text(encoding="utf-8"))
    )
    cpu = escape(info["cpu"])
    context = info["context_tokens"]
    repeats = info["repetitions"]
    panels: tuple[tuple[str, str, Metric], ...] = (
        ("Request latency", "Seconds · median of usable responses", "wall_s"),
        (
            "Generation throughput",
            "Tokens/s · median of usable responses",
            "generation_tokens_per_s",
        ),
        ("Peak Ollama RAM", "GiB · highest sampled process RSS across attempts", "peak_rss_gib"),
        (
            "Usable responses",
            f"Calls passing Quellenlot checks, out of {repeats} planned",
            "status",
        ),
    )
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1340" height="789" viewBox="0 0 1340 789">',
        "<title>Quellenlot CPU benchmark with the five configured Ollama models</title>",
        '<rect width="1340" height="789" fill="white"/>',
        '<style>text{font-family:"DejaVu Sans",sans-serif;fill:#192235}'
        ".heading{font-size:19px;font-weight:700}.muted{font-size:12px;fill:#475369}"
        ".model{font-size:13px;font-weight:600}.value{font-size:12px;font-weight:700}</style>",
        '<text x="24" y="40" font-size="29" font-weight="700">Quellenlot · CPU benchmark</text>',
        f'<text x="24" y="66" font-size="15">{cpu}  ·  Tankrabatt 2022  ·  '
        f"{context:,} context tokens  ·  {repeats} planned repetitions</text>",
    ]
    for index, (title, subtitle, metric) in enumerate(panels):
        x, y = 22 + (index % 2) * 658, 87 + (index // 2) * 329
        parts.extend(
            (
                f'<g transform="translate({x} {y})">',
                panel(title, subtitle, metric, rows, info),
                "</g>",
            )
        )
    parts.extend(
        (
            '<rect x="24" y="750" width="18" height="10" fill="#137564"/>',
            '<text x="49" y="760" class="model">Analysis</text>',
            '<rect x="130" y="750" width="18" height="10" fill="#6540a4"/>',
            '<text x="155" y="760" class="model">Peer review</text>',
            '<text x="279" y="760" class="muted">Dots show individual requests. '
            "Dashes mark missing measurements.</text>",
            "</svg>",
        )
    )
    (OUTPUT / "quellenlot-benchmark.svg").write_text("\n".join(parts), encoding="utf-8")


if __name__ == "__main__":
    render()
