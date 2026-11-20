"""Trace explicit links between captured articles and their upstream sources."""

from __future__ import annotations

import asyncio
from typing import Final

from pydantic import AnyHttpUrl

from quellenlot_agents.models import SourceCitation, SourceProvenance, SourceRetrieval
from quellenlot_agents.source_capture import capture_source, url_key

_MAX_DEPTH: Final = 2
_MAX_FETCHES: Final = 8


def _index_retrievals(retrievals: list[SourceRetrieval]) -> dict[str, SourceRetrieval]:
    """Resolve requested and redirected URLs to a single record per destination."""
    destinations: dict[str, SourceRetrieval] = {}
    for retrieval in retrievals:
        if retrieval.final_url is not None:
            key = url_key(retrieval.final_url)
            existing = destinations.setdefault(key, retrieval)
            if existing.snapshot is None and retrieval.snapshot is not None:
                destinations[key] = retrieval
    indexed = dict(destinations)
    for retrieval in retrievals:
        key = url_key(retrieval.requested_url)
        if retrieval.final_url is not None:
            indexed[key] = destinations[url_key(retrieval.final_url)]
        else:
            indexed.setdefault(key, retrieval)
    return indexed


def _citations(
    visited: dict[str, SourceRetrieval], indexed: dict[str, SourceRetrieval]
) -> list[SourceCitation]:
    citations: list[SourceCitation] = []
    for retrieval in visited.values():
        snapshot = retrieval.snapshot
        if snapshot is None:
            continue
        for link in retrieval.links:
            target = indexed.get(url_key(link.url))
            if target is not None and target.source_id != snapshot.source_id:
                citations.append(
                    SourceCitation(
                        citing_source_id=snapshot.source_id,
                        citing_version_id=snapshot.version_id,
                        cited_source_id=target.source_id,
                        link=link,
                    )
                )
    return citations


async def trace_sources(
    retrievals: list[SourceRetrieval],
) -> tuple[list[SourceRetrieval], SourceProvenance]:
    """Follow visible links with the same public-source retrieval used by article intake.

    Args:
        retrievals: Original and comparison retrievals, including redirect aliases and failures.

    Returns:
        New upstream retrievals and evidence of captured hyperlinks, including failed targets.
    """
    upstream: list[SourceRetrieval] = []
    indexed = _index_retrievals(retrievals)
    frontier: dict[str, SourceRetrieval] = {
        item.source_id: item for item in indexed.values() if item.snapshot is not None
    }
    visited: dict[str, SourceRetrieval] = {}
    limited = False
    for depth in range(_MAX_DEPTH + 1):
        if not frontier:
            break
        visited.update(frontier)
        targets: dict[str, tuple[AnyHttpUrl, set[str]]] = {}
        for retrieval in frontier.values():
            limited |= retrieval.links_limited
            for link in retrieval.links:
                _, incoming = targets.setdefault(url_key(link.url), (link.url, set()))
                incoming.add(retrieval.source_id)
        unknown = [
            (url, len(incoming)) for key, (url, incoming) in targets.items() if key not in indexed
        ]
        unknown.sort(key=lambda item: -item[1])
        budget = _MAX_FETCHES - len(upstream) if depth < _MAX_DEPTH else 0
        limited |= len(unknown) > budget
        if unknown and budget:
            captured = await asyncio.gather(
                *(
                    capture_source(url, f"citation-{index}")
                    for index, (url, _) in enumerate(unknown[:budget], len(upstream) + 1)
                )
            )
            upstream.extend(retrieval for _, retrieval in captured)
            indexed = _index_retrievals([*retrievals, *upstream])
        frontier = {
            target.source_id: target
            for key in targets
            if (target := indexed.get(key)) is not None
            and target.snapshot is not None
            and target.source_id not in visited
        }
    return upstream, SourceProvenance(citations=_citations(visited, indexed), limited=limited)
