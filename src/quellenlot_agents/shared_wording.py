"""Find overlapping wording and link matches to unchanged source excerpts."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import combinations, islice
from typing import Final

from rapidfuzz import fuzz

from quellenlot_agents.models import (
    SharedPassage,
    SharedWordingReport,
    SourceInput,
    SourcePassage,
)

_MIN_TOKENS: Final = 12
_MAX_WINDOW_TOKENS: Final = 120
_WINDOW_STRIDE: Final = 88
_MAX_WINDOWS: Final = 160
_MAX_CANDIDATES: Final = 8
_MAX_PER_PAIR: Final = 3
_MAX_MATCHES: Final = 60
_MIN_SCORE: Final = 90.0
_MIN_SHINGLES: Final = 3
_LINE: Final = re.compile(r"[^\r\n]+")
_SENTENCE_END: Final = re.compile(r"[.!?]+(?=\s|$)")
_QUOTE: Final = re.compile(r'„[^“”]+[“”]|«[^»]+»|»[^«]+«|“[^”]+”|"[^"]+"')
_TOKEN: Final = re.compile(r"\d+(?:[.,]\d+)*|[^\W_]+|[€%+\u2212-]")
type _Span = tuple[int, int]
type _Shingle = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class _Window:
    terms: tuple[str, ...]
    offsets: tuple[_Span, ...]
    shingles: frozenset[_Shingle]


@dataclass(frozen=True, slots=True)
class _Match:
    first: _Span
    second: _Span
    score: float
    length: int


def _candidate_spans(text: str) -> Iterator[_Span]:
    """Offer lines, sentences, and quotations as independently matchable passages."""
    for line in _LINE.finditer(text):
        yield line.span()
        for quote in _QUOTE.finditer(text, line.start(), line.end()):
            yield quote.span()
        start = line.start()
        for boundary in _SENTENCE_END.finditer(text, start, line.end()):
            yield start, boundary.end()
            start = boundary.end()
        if start < line.end():
            yield start, line.end()


def _windows(text: str) -> Iterator[_Window]:
    """Build bounded overlapping token windows while preserving original offsets."""
    seen: set[_Span] = set()
    for start, end in _candidate_spans(text):
        tokens = list(_TOKEN.finditer(text, start, end))
        for index in range(0, len(tokens), _WINDOW_STRIDE):
            clipped = tokens[index : index + _MAX_WINDOW_TOKENS]
            if len(clipped) < _MIN_TOKENS:
                break
            key = (clipped[0].start(), clipped[-1].end())
            if key not in seen:
                seen.add(key)
                terms = tuple(unicodedata.normalize("NFC", item[0]).casefold() for item in clipped)
                offsets = tuple(item.span() for item in clipped)
                shingles = frozenset(zip(terms, terms[1:], terms[2:], strict=False))
                yield _Window(terms=terms, offsets=offsets, shingles=shingles)
            if index + _MAX_WINDOW_TOKENS >= len(tokens):
                break


def _align(first: _Window, second: _Window) -> _Match | None:
    """Score ordered tokens and map the selected alignment back to both snapshots."""
    alignment = fuzz.partial_ratio_alignment(first.terms, second.terms, score_cutoff=_MIN_SCORE)
    if alignment is None:
        return None
    length = min(alignment.src_end - alignment.src_start, alignment.dest_end - alignment.dest_start)
    if length < _MIN_TOKENS:
        return None
    return _Match(
        first=(first.offsets[alignment.src_start][0], first.offsets[alignment.src_end - 1][1]),
        second=(second.offsets[alignment.dest_start][0], second.offsets[alignment.dest_end - 1][1]),
        score=alignment.score,
        length=length,
    )


def _intersects(first: _Span, second: _Span) -> bool:
    return first[0] < second[1] and second[0] < first[1]


def _pair_matches(first: list[_Window], second: list[_Window]) -> tuple[list[_Match], bool]:
    """Shortlist plausible pairs by shared three-token phrases and remove repeated alignments."""
    inverted: dict[_Shingle, list[int]] = {}
    for index, window in enumerate(second):
        for shingle in window.shingles:
            inverted.setdefault(shingle, []).append(index)

    ranked: list[_Match] = []
    limited = False
    for window in first:
        votes = Counter(index for shingle in window.shingles for index in inverted.get(shingle, []))
        candidates = sorted(
            (index for index, count in votes.items() if count >= _MIN_SHINGLES),
            key=lambda index: (-votes[index], index),
        )
        limited |= len(candidates) > _MAX_CANDIDATES
        for index in candidates[:_MAX_CANDIDATES]:
            hit = _align(window, second[index])
            if hit is not None:
                ranked.append(hit)

    ranked.sort(key=lambda hit: (-hit.length, -hit.score, hit.first, hit.second))
    selected: list[_Match] = []
    for hit in ranked:
        if any(
            _intersects(hit.first, item.first) and _intersects(hit.second, item.second)
            for item in selected
        ):
            continue
        if len(selected) == _MAX_PER_PAIR:
            return selected, True
        selected.append(hit)
    return selected, limited


def _excerpt(source: SourceInput, span: _Span) -> SourcePassage:
    start, end = span
    return SourcePassage(
        source_id=source.source_id,
        version_id=source.version_id,
        start=start,
        end=end,
        text=source.text[start:end],
    )


def find_shared_wording(sources: list[SourceInput]) -> SharedWordingReport:
    """Find passages with substantial wording overlap between supplied snapshots.

    Args:
        sources: Distinct, versioned snapshots included in the case.

    Returns:
        Exact excerpts on both sides, a similarity score, and an analysis limit flag.
    """
    if len(sources) < 2:
        return SharedWordingReport()
    windows = [list(islice(_windows(source.text), _MAX_WINDOWS + 1)) for source in sources]
    limited = any(len(items) > _MAX_WINDOWS for items in windows)
    matches: list[SharedPassage] = []
    for (first, left), (second, right) in combinations(zip(sources, windows, strict=True), 2):
        hits, pair_limited = _pair_matches(left[:_MAX_WINDOWS], right[:_MAX_WINDOWS])
        limited |= pair_limited
        for hit in hits:
            if len(matches) == _MAX_MATCHES:
                return SharedWordingReport(matches=matches, limited=True)
            matches.append(
                SharedPassage(
                    first=_excerpt(first, hit.first),
                    second=_excerpt(second, hit.second),
                    similarity=round(hit.score, 2),
                )
            )
    return SharedWordingReport(matches=matches, limited=limited)
