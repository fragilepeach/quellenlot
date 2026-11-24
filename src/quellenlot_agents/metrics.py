"""Per-run observation of local Ollama calls without global persisted state."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from quellenlot_agents.models import ModelCallMetric

_CURRENT: ContextVar[list[ModelCallMetric] | None] = ContextVar("model_calls", default=None)


@contextmanager
def collect_model_calls() -> Iterator[list[ModelCallMetric]]:
    """Capture provider calls made in the current execution context.

    Yields:
        The ordered mutable list of completed call observations.
    """
    records: list[ModelCallMetric] = []
    token = _CURRENT.set(records)
    try:
        yield records
    finally:
        _CURRENT.reset(token)


def record_model_call(record: ModelCallMetric) -> None:
    """Append one observation only when a collection is active.

    Args:
        record: Provider timing, response counters, and failure status.
    """
    records = _CURRENT.get()
    if records is not None:
        records.append(record)
