"""Retrieve topic coverage and article leads from GDELT's public news index."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from threading import Lock
from time import monotonic, sleep
from typing import Annotated, Final, Literal

import httpx
from pydantic import AnyHttpUrl, BaseModel, Field, JsonValue, StringConstraints, ValidationError

from quellenlot_agents.models import ContractModel

_ENDPOINT: Final = "https://api.gdeltproject.org/api/v2/doc/doc"
_MAX_RESPONSE: Final = 512 * 1024
_GDELT_REQUEST_INTERVAL: Final = 5.0
_REQUEST_LOCK = Lock()
_last_request_start = -_GDELT_REQUEST_INTERVAL


class _TopicQuery(ContractModel):
    """Specify a literal topic and optionally restrict its source language."""

    topic: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
    language: Literal["german", "all"] = "german"


class TrendQuery(_TopicQuery):
    """Specify a daily coverage window."""

    days: Literal[30, 90] = 30


class TrendEventQuery(_TopicQuery):
    """Specify the day of a spike in measured attention."""

    peak_date: date


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


class _GdeltArticles(BaseModel):
    articles: list[JsonValue] = Field(default_factory=list[JsonValue], max_length=20)


class _GdeltArticle(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)]
    url: AnyHttpUrl
    seendate: str


class TrendArticle(ContractModel):
    """An indexed news article close to a spike day."""

    title: str
    url: AnyHttpUrl
    indexed_date: date


class TrendEvents(ContractModel):
    """Article leads and their UTC query window."""

    peak_date: date
    window_start: date
    window_end: date
    articles: list[TrendArticle]


class TrendUnavailable(RuntimeError):
    """GDELT could not supply a usable response."""


def _search_term(query: _TopicQuery) -> str:
    if '"' in query.topic or any(ord(char) < 32 for char in query.topic):
        msg = "Der Suchbegriff darf keine Anführungszeichen oder Zeilenumbrüche enthalten."
        raise ValueError(msg)
    term = f'"{query.topic}"'
    return term + " sourcelang:german" if query.language == "german" else term


def _gdelt_payload(params: dict[str, str]) -> bytearray:
    # The DOC API asks clients to space requests at least five seconds apart.
    global _last_request_start
    with _REQUEST_LOCK:
        wait = _GDELT_REQUEST_INTERVAL - (monotonic() - _last_request_start)
        if wait > 0:
            sleep(wait)
        _last_request_start = monotonic()
    with httpx.stream("GET", _ENDPOINT, params=params, timeout=12.0) as response:
        response.raise_for_status()
        body = bytearray()
        for chunk in response.iter_bytes(chunk_size=8192):
            body.extend(chunk)
            if len(body) > _MAX_RESPONSE:
                msg = "Der GDELT-Datensatz überschreitet die zulässige Größe."
                raise TrendUnavailable(msg)
    return body


def _gdelt_day(value: str) -> date:
    return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).date()


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
    params = {
        "query": _search_term(query),
        "mode": "TimelineVol",
        "format": "json",
        "timespan": f"{query.days}d",
    }
    try:
        payload = _GdeltResponse.model_validate_json(_gdelt_payload(params))
        values = [
            TrendPoint(date=_gdelt_day(point.date), value=point.value)
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


def fetch_trend_events(query: TrendEventQuery) -> TrendEvents:
    """Search a five-day window around a recent spike for article leads.

    Args:
        query: Literal topic, source language, and UTC spike date.

    Returns:
        Up to five distinct articles with GDELT index dates within the query window.

    Raises:
        TrendUnavailable: The provider failed or returned an unexpected response.
        ValueError: The topic or spike date is outside the supported range.
    """
    term = _search_term(query)
    now = datetime.now(UTC)
    earliest = now.date() - timedelta(days=89)
    if not earliest <= query.peak_date <= now.date():
        msg = "Ereignisvorschläge sind für Ausschläge der letzten 90 UTC-Tage verfügbar."
        raise ValueError(msg)
    start = max(earliest, query.peak_date - timedelta(days=2))
    end = min(now.date(), query.peak_date + timedelta(days=2))
    params = {
        "query": term,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": "20",
        "sort": "HybridRel",
        "startdatetime": datetime.combine(start, time.min, UTC).strftime("%Y%m%d%H%M%S"),
        "enddatetime": min(now, datetime.combine(end, time.max, UTC)).strftime("%Y%m%d%H%M%S"),
    }
    try:
        result = _GdeltArticles.model_validate_json(_gdelt_payload(params))
    except (httpx.HTTPError, ValidationError) as exc:
        msg = "GDELT liefert momentan keine auswertbaren Artikelvorschläge."
        raise TrendUnavailable(msg) from exc
    articles: dict[str, TrendArticle] = {}
    for item in result.articles:
        try:
            article = _GdeltArticle.model_validate(item)
            indexed = _gdelt_day(article.seendate)
        except ValueError:
            continue
        if (
            not start <= indexed <= end
            or article.url.username is not None
            or article.url.password is not None
        ):
            continue
        articles.setdefault(
            str(article.url),
            TrendArticle(title=article.title, url=article.url, indexed_date=indexed),
        )
        if len(articles) == 5:
            break
    return TrendEvents(
        peak_date=query.peak_date,
        window_start=start,
        window_end=end,
        articles=list(articles.values()),
    )
