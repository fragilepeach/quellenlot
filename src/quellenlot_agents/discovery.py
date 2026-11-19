"""Discover comparison URLs through the configured SearXNG instance."""

from __future__ import annotations

import asyncio
from typing import Final

import httpx
from pydantic import AnyHttpUrl, BaseModel, JsonValue, ValidationError

from quellenlot_agents.config import SearchConfig
from quellenlot_agents.models import (
    DiscoveredSource,
    SearchQuery,
    SourceDiscovery,
    SourceInput,
    SourceRetrieval,
)
from quellenlot_agents.source_capture import capture_source

_MAX_RESPONSE_BYTES: Final = 1024 * 1024
_RESULTS_PER_QUERY: Final = 20
_PRIORITY_DOMAINS: Final = ("bund.de", "bundestag.de", "destatis.de", "europa.eu", "gov", "gov.uk")
_TRACKING_PARAMETERS: Final = frozenset({"fbclid", "gclid", "msclkid"})


class _SearchError(RuntimeError):
    """A search request failed without returning usable results."""


class _SearchResponse(BaseModel):
    """The part of the response containing search result entries."""

    results: list[JsonValue]


class _SearchHit(BaseModel):
    """A result URL supplied by the search service."""

    url: AnyHttpUrl


def _queries(claims: list[str], question: str | None) -> list[str]:
    """Anchor an optional question to the article topic and search each claim."""
    normalized = [" ".join(claim.split()) for claim in claims]
    if question is not None and normalized:
        prefix = " ".join(question.split())[:120]
        normalized.insert(0, f"{prefix} {normalized[0]}")
    queries: dict[str, str] = {}
    for query in normalized:
        shortened = query[:300].strip()
        if shortened:
            queries.setdefault(shortened.casefold(), shortened)
    return list(queries.values())


def _result_url(item: JsonValue) -> AnyHttpUrl | None:
    try:
        url = _SearchHit.model_validate(item).url
        httpx.URL(str(url))
    except (ValidationError, httpx.InvalidURL):
        return None
    return url if url.username is None and url.password is None else None


async def _search(
    client: httpx.AsyncClient,
    config: SearchConfig,
    query: str,
) -> list[AnyHttpUrl]:
    """Download one bounded result page and discard malformed entries individually."""
    params = {"q": query, "language": config.language, "format": "json"}
    headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
    async with (
        asyncio.timeout(12),
        client.stream("GET", str(config.endpoint), params=params, headers=headers) as response,
    ):
        if not response.is_success:
            msg = f"Search endpoint returned HTTP {response.status_code}."
            raise _SearchError(msg)
        if response.headers.get("content-encoding", "identity").lower().strip() != "identity":
            msg = "Search endpoint returned an unsupported compressed response."
            raise _SearchError(msg)
        body = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=65536):
            if len(body) + len(chunk) > _MAX_RESPONSE_BYTES:
                msg = "Search response exceeded the size limit."
                raise _SearchError(msg)
            body.extend(chunk)
    try:
        entries = _SearchResponse.model_validate_json(body).results
    except ValidationError as exc:
        msg = "Search endpoint did not return valid result JSON."
        raise _SearchError(msg) from exc
    return [url for item in entries[:_RESULTS_PER_QUERY] if (url := _result_url(item)) is not None]


def _publisher_priority(url: AnyHttpUrl) -> bool:
    host = (url.host or "").lower().rstrip(".")
    return any(host == domain or host.endswith(f".{domain}") for domain in _PRIORITY_DOMAINS)


def _url_key(url: AnyHttpUrl) -> str:
    """Compare URLs without fragments or common tracking parameters."""
    parsed = httpx.URL(str(url))
    params = tuple(
        (key, value)
        for key, value in parsed.params.multi_items()
        if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_PARAMETERS
    )
    query = str(httpx.QueryParams(params)).encode("ascii") if params else None
    return str(parsed.copy_with(fragment=None, query=query))


async def _search_candidates(
    config: SearchConfig,
    queries: list[str],
) -> tuple[list[SearchQuery], list[AnyHttpUrl]]:
    attempts: list[SearchQuery] = []
    ranked: list[tuple[int, AnyHttpUrl]] = []
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(8.0, connect=4.0), follow_redirects=False, trust_env=False
    ) as client:
        for query in queries:
            detail: str | None = None
            try:
                urls = await _search(client, config, query)
            except _SearchError as exc:
                detail = str(exc)
            except TimeoutError:
                detail = "Search endpoint timed out."
            except (httpx.HTTPError, httpx.InvalidURL, OSError):
                detail = "Could not connect to or read from the search endpoint."
            else:
                attempts.append(
                    SearchQuery(query=query, status="completed", result_count=len(urls))
                )
                ranked.extend(enumerate(urls))
            if detail is not None:
                attempts.append(
                    SearchQuery(query=query, status="failed", result_count=0, detail=detail)
                )
    ranked.sort(key=lambda item: (not _publisher_priority(item[1]), item[0]))
    return attempts, [url for _, url in ranked]


async def discover_sources(
    *,
    original: SourceInput,
    requested_url: AnyHttpUrl,
    claims: list[str],
    question: str | None,
    config: SearchConfig,
) -> tuple[list[SourceInput], list[SourceRetrieval], SourceDiscovery]:
    """Find unique comparison snapshots with bounded search and retrieval.

    Args:
        original: Original article snapshot, used to reject duplicate content.
        requested_url: Original input URL, before redirects.
        claims: Ordered, verified claims extracted from the original article.
        question: Optional question to inform the first query.
        config: Trusted search endpoint and maximum comparison count.

    Returns:
        Included sources, their retrieval attempts, and the search audit trail.
    """
    queries, urls = await _search_candidates(config, _queries(claims, question))
    included_urls = {_url_key(requested_url)}
    if original.url is not None:
        included_urls.add(_url_key(original.url))
    attempted_urls = set(included_urls)
    hashes = {original.content_sha256}
    sources: list[SourceInput] = []
    retrievals: list[SourceRetrieval] = []
    candidates: list[DiscoveredSource] = []
    for url in urls:
        key = _url_key(url)
        if key in attempted_urls:
            continue
        attempted_urls.add(key)
        source_id = f"comparison-{len(retrievals) + 1}"
        source, retrieval = await capture_source(url, source_id)
        retrievals.append(retrieval)
        if source is None:
            status = "unavailable"
        else:
            final_key = _url_key(retrieval.final_url) if retrieval.final_url is not None else key
            digest = source.content_sha256
            if final_key in included_urls or digest in hashes:
                status = "duplicate"
            else:
                sources.append(source)
                hashes.add(digest)
                included_urls.add(final_key)
                status = "included"
            attempted_urls.add(final_key)
        candidates.append(
            DiscoveredSource(
                source_id=source_id,
                url=url,
                publisher_priority=_publisher_priority(url),
                status=status,
            )
        )
        if len(sources) >= config.max_sources or len(retrievals) >= 2 * config.max_sources:
            break

    return sources, retrievals, SourceDiscovery(queries=queries, candidates=candidates)
