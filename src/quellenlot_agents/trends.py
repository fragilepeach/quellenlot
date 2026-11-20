"""Retrieve daily topic coverage from GDELT's public news index."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Final, Literal

import httpx
from pydantic import BaseModel, Field, StringConstraints, ValidationError

from quellenlot_agents.models import ContractModel

_ENDPOINT: Final = "https://api.gdeltproject.org/api/v2/doc/doc"
_MAX_RESPONSE: Final = 512 * 1024


class TrendQuery(ContractModel):
    """Specify a literal topic and a daily coverage window."""

    topic: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
    days: Literal[30, 90] = 30
    language: Literal["german", "all"] = "german"


class _GdeltPoint(BaseModel):
    date: str
    value: float = Field(ge=0, le=100, allow_inf_nan=False)


class _GdeltSeries(BaseModel):
    data: list[_GdeltPoint] = Field(max_length=100)


class _GdeltResponse(BaseModel):
    timeline: list[_GdeltSeries] = Field(min_length=1, max_length=1)


class TrendPoint(ContractModel):
    """A UTC day and its share of coverage monitored by GDELT."""

    date: date
    value: float


class NewsTrend(ContractModel):
    """A source-linked daily series for the browser."""

    label: str
    source_url: str
    points: list[TrendPoint]


class TrendUnavailable(RuntimeError):
    """GDELT could not supply a usable coverage series."""


def fetch_news_trend(query: TrendQuery) -> NewsTrend:
    """Fetch a daily share of monitored news coverage for a topic.

    Args:
        query: User-selected literal topic, range, and publication language.

    Returns:
        The daily percentage series and the corresponding GDELT source link.

    Raises:
        TrendUnavailable: The provider failed or returned an unexpected series.
        ValueError: The topic contains quotation or control characters.
    """
    if '"' in query.topic or any(ord(char) < 32 for char in query.topic):
        msg = "Der Suchbegriff darf keine Anführungszeichen oder Zeilenumbrüche enthalten."
        raise ValueError(msg)
    term = f'"{query.topic}"'
    if query.language == "german":
        term += " sourcelang:german"
    params = {
        "query": term,
        "mode": "TimelineVol",
        "format": "json",
        "timespan": f"{query.days}d",
    }
    try:
        with httpx.stream("GET", _ENDPOINT, params=params, timeout=12.0) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes(chunk_size=8192):
                body.extend(chunk)
                if len(body) > _MAX_RESPONSE:
                    msg = "Der GDELT-Datensatz überschreitet die zulässige Größe."
                    raise TrendUnavailable(msg)
        payload = _GdeltResponse.model_validate_json(body)
        values = [
            TrendPoint(
                date=datetime.strptime(point.date, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).date(),
                value=point.value,
            )
            for point in payload.timeline[0].data
        ]
    except (httpx.HTTPError, ValidationError, ValueError) as exc:
        msg = "GDELT liefert momentan keine auswertbare Zeitreihe."
        raise TrendUnavailable(msg) from exc
    if len({point.date for point in values}) != len(values):
        msg = "GDELT hat keine täglichen Werte geliefert."
        raise TrendUnavailable(msg)
    return NewsTrend(
        label=query.topic,
        source_url=str(httpx.URL(_ENDPOINT, params={**params, "format": "html"})),
        points=sorted(values, key=lambda point: point.date),
    )
