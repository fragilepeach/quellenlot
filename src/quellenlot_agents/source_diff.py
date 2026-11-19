"""Build a claim-level source comparison from verified quotations."""

from __future__ import annotations

from dataclasses import dataclass, field

from quellenlot_agents.models import (
    AnalysisRecord,
    ClaimSourceDiff,
    DiffCitation,
    DiffEvidence,
    DiffJudgment,
    DiffSource,
    SharedWordingReport,
    SourceInput,
    SourcePassage,
    SourceSnapshot,
)

type _CitationKey = tuple[str, str]
type _SourceCitations = dict[str, dict[str, _Citation]]


@dataclass(slots=True)
class _Citation:
    source: SourceInput
    start: int | None
    end: int | None
    locators: list[str] = field(default_factory=list[str])
    overlaps: list[int] = field(default_factory=list[int])


def _collect_citations(
    sources: list[SourceInput], analyses: list[AnalysisRecord]
) -> _SourceCitations:
    """Index exact quotes and locate each when the snapshot occurrence is unique."""
    sources_by_id = {source.source_id: source for source in sources}
    citations: _SourceCitations = {source.source_id: {} for source in sources}
    for analysis in analyses:
        if analysis.status != "succeeded":
            continue
        for finding in analysis.findings:
            source = sources_by_id[finding.source_id]
            found = citations[source.source_id]
            for quote in finding.quotes:
                if (
                    not quote.verified
                    or quote.source_id != source.source_id
                    or quote.version_id != source.version_id
                    or not quote.text.strip()
                ):
                    continue
                citation = found.get(quote.text)
                if citation is None:
                    start = source.text.find(quote.text)
                    if start == -1:
                        continue
                    unique = source.text.find(quote.text, start + 1) == -1
                    citation = _Citation(
                        source=source,
                        start=start if unique else None,
                        end=start + len(quote.text) if unique else None,
                    )
                    found[quote.text] = citation
                if quote.locator not in citation.locators:
                    citation.locators.append(quote.locator)
    return citations


def _mark_overlaps(
    passage: SourcePassage, citations: dict[str, _Citation], match_index: int
) -> set[str]:
    """Link intersecting quotes and identify quotes with no separate wording outside the span."""
    contained: set[str] = set()
    for quote, citation in citations.items():
        start, end = citation.start, citation.end
        if start is None or end is None or citation.source.version_id != passage.version_id:
            continue
        inside_start, inside_end = max(start, passage.start), min(end, passage.end)
        if inside_start >= inside_end:
            continue
        text = citation.source.text
        if not any(char.isalnum() for char in text[inside_start:inside_end]):
            continue
        citation.overlaps.append(match_index)
        outside = text[start:inside_start] + text[inside_end:end]
        if not any(char.isalnum() or char in "%€+-\u2212" for char in outside):
            contained.add(quote)
    return contained


def _link_shared_citations(
    citations: _SourceCitations, wording: SharedWordingReport
) -> dict[_CitationKey, set[_CitationKey]]:
    """Connect identical quotes only when both occurrences are entirely within a shared passage."""
    links: dict[_CitationKey, set[_CitationKey]] = {}
    for index, match in enumerate(wording.matches):
        left, right = match.first.source_id, match.second.source_id
        if left == right:
            continue
        first = _mark_overlaps(match.first, citations.get(left, {}), index)
        second = _mark_overlaps(match.second, citations.get(right, {}), index)
        for quote in first & second:
            first_key = (left, quote)
            second_key = (right, quote)
            links.setdefault(first_key, set()).add(second_key)
            links.setdefault(second_key, set()).add(first_key)
    return links


def _connected(
    origin: _CitationKey, links: dict[_CitationKey, set[_CitationKey]]
) -> set[_CitationKey]:
    visited: set[_CitationKey] = set()
    pending = [origin]
    while pending:
        key = pending.pop()
        if key not in visited:
            visited.add(key)
            pending.extend(links.get(key, set()) - visited)
    return visited


def _evidence_table(
    citations: _SourceCitations, wording: SharedWordingReport
) -> tuple[list[DiffEvidence], dict[_CitationKey, str]]:
    links = _link_shared_citations(citations, wording)
    evidence: list[DiffEvidence] = []
    references: dict[_CitationKey, str] = {}
    source_order = {source_id: index for index, source_id in enumerate(citations)}
    for source_id, quotes in citations.items():
        for quote in quotes:
            key = (source_id, quote)
            if key in references:
                continue
            group = sorted(_connected(key, links), key=lambda item: source_order[item[0]])
            evidence_id = f"evidence-{len(evidence) + 1}"
            occurrences: list[DiffCitation] = []
            for member_id, text in group:
                item = citations[member_id][text]
                references[(member_id, text)] = evidence_id
                occurrences.append(
                    DiffCitation(
                        source_id=member_id,
                        version_id=item.source.version_id,
                        locators=item.locators,
                        start=item.start,
                        end=item.end,
                        shared_wording_match_indexes=item.overlaps,
                    )
                )
            evidence.append(
                DiffEvidence(
                    evidence_id=evidence_id,
                    kind="shared_wording" if len(group) > 1 else "source_specific",
                    text=quote,
                    citations=occurrences,
                )
            )
    return evidence, references


def _judgments(
    sources: list[SourceSnapshot],
    analyses: list[AnalysisRecord],
    references: dict[_CitationKey, str],
) -> list[DiffSource]:
    grouped: dict[str, list[DiffJudgment]] = {source.source_id: [] for source in sources}
    for analysis in analyses:
        if analysis.status != "succeeded":
            continue
        for finding in analysis.findings:
            evidence_ids = dict.fromkeys(
                references[key]
                for quote in finding.quotes
                if quote.verified
                and quote.source_id == finding.source_id
                and quote.version_id == finding.version_id
                and (key := (finding.source_id, quote.text)) in references
            )
            grouped[finding.source_id].append(
                DiffJudgment(
                    agent_id=analysis.agent_id,
                    relation=finding.relation,
                    reasoning=finding.reasoning,
                    evidence_ids=list(evidence_ids),
                )
            )
    return [DiffSource(source=source, judgments=grouped[source.source_id]) for source in sources]


def build_source_diff(
    sources: list[SourceInput],
    snapshots: list[SourceSnapshot],
    analyses: list[AnalysisRecord],
    wording: SharedWordingReport,
) -> ClaimSourceDiff:
    """Show each source's claim judgments and group corroborated wording overlaps.

    Args:
        sources: Supplied source texts used to verify citations and locate them.
        snapshots: Report metadata for the same source versions in input order.
        analyses: Validated independent analyses with source-grounded findings.
        wording: Passage matches computed for these source versions.

    Returns:
        Source rows with evidence references and exactly quoted evidence entries.
    """
    evidence, references = _evidence_table(_collect_citations(sources, analyses), wording)
    return ClaimSourceDiff(sources=_judgments(snapshots, analyses, references), evidence=evidence)
