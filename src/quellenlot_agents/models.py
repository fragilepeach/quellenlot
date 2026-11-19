"""Typed request and report contracts for a Quellenlot review."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, StringConstraints, model_validator


class ContractModel(BaseModel):
    """Base contract that rejects unknown fields and implicit Python coercions."""

    model_config = ConfigDict(extra="forbid", strict=True)


DateProvenance = Literal["json_ld", "open_graph", "html_time", "provided"]


class SourceDate(ContractModel):
    """A source's declared date or timestamp and the metadata that supplied it."""

    value: date | datetime
    provenance: DateProvenance = "provided"


class SourceInput(ContractModel):
    """An immutable source snapshot supplied to a review."""

    source_id: str = Field(min_length=1, max_length=120)
    version_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    url: AnyHttpUrl | None = None
    captured_at: datetime
    published_at: SourceDate | None = None
    updated_at: SourceDate | None = None
    publisher: str | None = Field(default=None, min_length=1, max_length=300)
    authors: list[str] = Field(default_factory=list[str], max_length=20)
    text: str = Field(min_length=1, max_length=200_000)
    text_is_complete: bool

    @property
    def content_sha256(self) -> str:
        """Identify the exact source text analyzed.

        Returns:
            Hexadecimal SHA-256 digest of the UTF-8 text.
        """
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


class CaseInput(ContractModel):
    """A claim and the source snapshots to evaluate against it."""

    case_id: str = Field(min_length=1, max_length=120)
    claim: str = Field(min_length=1, max_length=4_000)
    sources: list[SourceInput] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def require_unique_source_ids(self) -> CaseInput:
        """Reject ambiguous source references before any model is called.

        Returns:
            The validated case with unique source identifiers.

        Raises:
            ValueError: The same source ID occurs more than once.
        """
        _require_unique_source_ids(self.sources)
        return self


def _require_unique_source_ids(sources: list[SourceInput]) -> None:
    """Reject ambiguous source references."""
    source_ids = {source.source_id for source in sources}
    if len(source_ids) != len(sources):
        msg = "Source IDs must be unique within a case."
        raise ValueError(msg)


NonBlankStatement = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4_000)
]


class InterestUrlInput(ContractModel):
    """Identify a public evidence page for one source in a URL case."""

    target_source_id: str = Field(min_length=1, max_length=120)
    url: AnyHttpUrl


class InterestEvidenceInput(ContractModel):
    """Attach a supplied evidence snapshot to the source whose interests it describes."""

    target_source_id: str = Field(min_length=1, max_length=120)
    source: SourceInput


class ArticleCaseInput(ContractModel):
    """An original article, an optional question, and manually supplied comparisons."""

    case_id: str = Field(min_length=1, max_length=120)
    article: SourceInput
    question: NonBlankStatement | None = None
    comparison_sources: list[SourceInput] = Field(default_factory=list[SourceInput], max_length=19)
    interest_evidence: list[InterestEvidenceInput] = Field(
        default_factory=list[InterestEvidenceInput], max_length=40
    )

    @property
    def sources(self) -> list[SourceInput]:
        """Expose the sources in review order.

        Returns:
            The original article followed by the comparison snapshots.
        """
        return [self.article, *self.comparison_sources]

    @model_validator(mode="after")
    def require_unique_source_ids(self) -> ArticleCaseInput:
        """Reject shared IDs across the article and its comparisons.

        Returns:
            The validated article case with unique source identifiers.

        Raises:
            ValueError: The same source ID occurs more than once.
        """
        _require_unique_source_ids(self.sources)
        source_ids = {source.source_id for source in self.sources}
        evidence_ids = [item.source.source_id for item in self.interest_evidence]
        if len(evidence_ids) != len(set(evidence_ids)) or source_ids.intersection(evidence_ids):
            msg = "Interest evidence IDs must be unique and distinct from article source IDs."
            raise ValueError(msg)
        if any(item.target_source_id not in source_ids for item in self.interest_evidence):
            msg = "Interest evidence must target a source in the article case."
            raise ValueError(msg)
        return self


class ArticleUrlInput(ContractModel):
    """A public article URL and optional comparison URLs and question."""

    case_id: str = Field(min_length=1, max_length=120)
    article_url: AnyHttpUrl
    question: NonBlankStatement | None = None
    comparison_urls: list[AnyHttpUrl] = Field(default_factory=list[AnyHttpUrl], max_length=19)
    interest_urls: list[InterestUrlInput] = Field(
        default_factory=list[InterestUrlInput], max_length=40
    )

    @model_validator(mode="after")
    def require_requested_interest_targets(self) -> ArticleUrlInput:
        """Validate evidence targets against the requested URLs.

        Returns:
            The validated case with every evidence target present in the request.

        Raises:
            ValueError: Evidence targets neither the article nor a requested comparison.
        """
        source_ids = {"article", *(f"comparison-{i + 1}" for i in range(len(self.comparison_urls)))}
        if any(item.target_source_id not in source_ids for item in self.interest_urls):
            msg = "Interest evidence URLs must target the article or a requested comparison."
            raise ValueError(msg)
        return self


Relation = Literal["supports", "qualifies", "contradicts", "omits", "not_assessable"]
ReviewOutcome = Literal["agrees", "challenges", "unclear"]
RecordStatus = Literal["complete", "partial", "failed"]


class DraftQuote(ContractModel):
    """A model-proposed quote that will be verified against the supplied snapshot."""

    source_id: str = Field(min_length=1, max_length=120)
    locator: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=2_000)


class DraftArticleClaim(ContractModel):
    """A checkable claim and its anchor in the original article."""

    claim: NonBlankStatement
    quote: DraftQuote


class DraftArticleExtraction(ContractModel):
    """The checkable claims found in the original article."""

    claims: list[DraftArticleClaim] = Field(max_length=5)


class DraftFinding(ContractModel):
    """A model's assessment of the claim in one source."""

    source_id: str = Field(min_length=1, max_length=120)
    relation: Relation
    reasoning: str = Field(min_length=1, max_length=4_000)
    quotes: list[DraftQuote] = Field(max_length=8)


class DraftAnalysis(ContractModel):
    """Structured output from an independent analysis."""

    summary: str = Field(min_length=1, max_length=4_000)
    findings: list[DraftFinding] = Field(min_length=1, max_length=20)
    open_questions: list[str] = Field(max_length=20)


class VerifiedQuote(ContractModel):
    """A quote plus a mechanical exact-text check result."""

    source_id: str
    version_id: str | None
    locator: str
    text: str
    verified: bool


class Finding(ContractModel):
    """A source-level assessment with independently verified quote anchors."""

    source_id: str
    version_id: str | None
    relation: Relation
    reasoning: str
    evidence_status: Literal["verified", "unverified", "no_quote"]
    quotes: list[VerifiedQuote]


class AnalysisRecord(ContractModel):
    """One model's independent result or a recorded failure."""

    agent_id: str
    model: str
    status: Literal["succeeded", "failed"]
    summary: str | None
    findings: list[Finding]
    open_questions: list[str]
    error_code: str | None


class DraftReviewFinding(ContractModel):
    """A peer review of one finding from another model."""

    finding_index: int = Field(ge=0)
    outcome: ReviewOutcome
    reasoning: str = Field(min_length=1, max_length=4_000)
    quote: DraftQuote | None = None


class DraftReview(ContractModel):
    """Structured output from a model checking another model's findings."""

    reviewed_agent_id: str
    summary: str = Field(min_length=1, max_length=4_000)
    findings: list[DraftReviewFinding] = Field(min_length=1, max_length=20)


class ReviewFinding(ContractModel):
    """A peer-review result with an independently verified quote anchor."""

    finding_index: int
    outcome: ReviewOutcome
    reasoning: str
    quote: VerifiedQuote | None


class ReviewRecord(ContractModel):
    """One cross-review result or a recorded failure."""

    reviewer_agent_id: str
    reviewed_agent_id: str
    status: Literal["succeeded", "failed"]
    summary: str | None
    findings: list[ReviewFinding]
    error_code: str | None


class SourceSnapshot(ContractModel):
    """The source identity and text digest included in a final report."""

    source_id: str
    version_id: str
    title: str
    url: AnyHttpUrl | None
    captured_at: datetime
    published_at: SourceDate | None = None
    updated_at: SourceDate | None = None
    publisher: str | None = None
    authors: list[str] = Field(default_factory=list[str])
    content_sha256: str
    text_is_complete: bool

    @classmethod
    def from_source(cls, source: SourceInput) -> SourceSnapshot:
        """Identify the exact version of the supplied text.

        Args:
            source: Versioned snapshot passed to the model.

        Returns:
            Report metadata with the source's text digest.
        """
        return cls(
            source_id=source.source_id,
            version_id=source.version_id,
            title=source.title,
            url=source.url,
            captured_at=source.captured_at,
            published_at=source.published_at,
            updated_at=source.updated_at,
            publisher=source.publisher,
            authors=source.authors,
            content_sha256=source.content_sha256,
            text_is_complete=source.text_is_complete,
        )


class RelationCount(ContractModel):
    """Count of model assessments by relation, without weighting them as truth."""

    relation: Relation
    count: int


class SourcePassage(ContractModel):
    """Link an exact excerpt to character offsets in a supplied source version."""

    source_id: str
    version_id: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)


class SharedPassage(ContractModel):
    """Report similar wording and the original excerpts on both sides."""

    first: SourcePassage
    second: SourcePassage
    similarity: float = Field(ge=0, le=100)


class SharedWordingReport(ContractModel):
    """Record bounded passage comparisons between sources in a case."""

    matches: list[SharedPassage] = Field(default_factory=list[SharedPassage])
    limited: bool = False


class DiffCitation(ContractModel):
    """Locate cited wording in one source version and link overlapping passages."""

    source_id: str
    version_id: str
    locators: list[str]
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, gt=0)
    shared_wording_match_indexes: list[int]


class DiffEvidence(ContractModel):
    """Store one exact cited excerpt and the source versions that cite it."""

    evidence_id: str
    kind: Literal["shared_wording", "source_specific"]
    text: str
    citations: list[DiffCitation]


class DiffJudgment(ContractModel):
    """Show one model's conclusion and references to its verified evidence."""

    agent_id: str
    relation: Relation
    reasoning: str
    evidence_ids: list[str]


class DiffSource(ContractModel):
    """Show a versioned source and the independent judgments it received."""

    source: SourceSnapshot
    judgments: list[DiffJudgment]


class ClaimSourceDiff(ContractModel):
    """Show sources side by side and consolidate repeated cited evidence."""

    sources: list[DiffSource] = Field(default_factory=list[DiffSource])
    evidence: list[DiffEvidence] = Field(default_factory=list[DiffEvidence])


class RunReport(ContractModel):
    """Auditable output of the independent and peer-review phases."""

    case_id: str
    claim: str
    status: RecordStatus
    limitation: str
    sources: list[SourceSnapshot]
    analyses: list[AnalysisRecord]
    reviews: list[ReviewRecord]
    relation_counts: list[RelationCount]
    unresolved_dissent: list[str]
    shared_wording: SharedWordingReport | None = None
    source_diff: ClaimSourceDiff = Field(default_factory=ClaimSourceDiff)


class ExtractionAttempt(ContractModel):
    """The outcome of asking one configured model to extract article claims."""

    agent_id: str
    model: str
    status: Literal["succeeded", "failed"]
    error_code: str | None = None


class SourceJudgment(ContractModel):
    """One model's interpretation and exact-match citations for a source."""

    agent_id: str
    relation: Relation
    reasoning: str
    citations: list[VerifiedQuote]


class SourceComparison(ContractModel):
    """All available judgments for one source, in model order."""

    source: SourceSnapshot
    judgments: list[SourceJudgment]


class ClaimComparison(ContractModel):
    """One extracted claim, its evidence across sources, and all review details."""

    claim_id: str
    article_quote: VerifiedQuote
    source_comparison: list[SourceComparison]
    review: RunReport


InterestCategory = Literal[
    "ownership",
    "funding",
    "author_affiliation",
    "political_affiliation",
]


class DraftInterestFinding(ContractModel):
    """A model-proposed relationship backed by one exact evidence quotation."""

    category: InterestCategory
    subject: str = Field(min_length=1, max_length=300)
    related_entity: str = Field(min_length=1, max_length=300)
    relationship: str = Field(min_length=1, max_length=2_000)
    quote: DraftQuote


class DraftInterestAssessment(ContractModel):
    """Independent model findings about a source's documented interests."""

    findings: list[DraftInterestFinding] = Field(max_length=12)


class InterestFinding(ContractModel):
    """An identified relationship and the exact source quote supporting it."""

    category: InterestCategory
    subject: str
    related_entity: str
    relationship: str
    evidence: VerifiedQuote


class InterestAssessment(ContractModel):
    """Retain one independent model's conclusions or failure."""

    agent_id: str
    model: str
    status: Literal["succeeded", "failed"]
    findings: list[InterestFinding]
    unknown_categories: list[InterestCategory]
    error_code: str | None = None


class InterestSearch(ContractModel):
    """Document a search query issued for a source's affiliations."""

    query: str
    status: Literal["completed", "failed"]
    result_count: int = Field(ge=0)
    detail: str | None = None


class SourceRetrieval(ContractModel):
    """The result of retrieving a URL and extracting article text."""

    source_id: str
    requested_url: AnyHttpUrl
    final_url: AnyHttpUrl | None = None
    status: Literal["captured", "partial", "failed"]
    detail: str


class InterestSourceReview(ContractModel):
    """Document evidence availability and independent assessments for one source."""

    source: SourceSnapshot
    evidence_sources: list[SourceSnapshot]
    searches: list[InterestSearch]
    retrievals: list[SourceRetrieval]
    assessments: list[InterestAssessment]
    unresolved_categories: list[InterestCategory]


class InterestReport(ContractModel):
    """Keep all source-interest investigations and missing-evidence outcomes."""

    status: Literal["complete", "partial", "no_evidence"]
    sources: list[InterestSourceReview]
    limitation: str = (
        "Reported relationships are model interpretations of supplied evidence. "
        "Exact quotes confirm text occurrence only. Editorial verification is required."
    )


class EditorialClaimCoverage(ContractModel):
    """Show available comparison evidence and unresolved issues for one claim."""

    claim_id: str
    review_status: RecordStatus
    comparison_evidence_ids: list[str]
    evidence_shown_to_models: list[str]
    comparison_sources_without_quotes: list[str]
    unresolved_dissent_count: int


class EditorialClaimNote(ContractModel):
    """One model's editorial reading of a claim and the passages it uses."""

    claim_id: str
    evidence_ids: list[str] = Field(min_length=1, max_length=3)
    assessment: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=650)
    ]
    next_check: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
        | None
    )


class DraftEditorialAssessment(ContractModel):
    """A model's structured response for the claims assigned to it."""

    claims: list[EditorialClaimNote] = Field(min_length=1, max_length=5)


class EditorialAssessment(ContractModel):
    """One local model's final notes or its recorded failure."""

    agent_id: str
    model: str
    status: Literal["succeeded", "failed"]
    claims: list[EditorialClaimNote]
    error_code: str | None = None


class EditorialReport(ContractModel):
    """An evidence inventory and independent notes for human review."""

    status: RecordStatus | Literal["no_claims", "no_comparison_evidence"]
    claims: list[EditorialClaimCoverage]
    incomplete_source_ids: list[str]
    retrieval_gaps: list[SourceRetrieval]
    discovery_incomplete: bool
    interest_status: Literal["complete", "partial", "no_evidence"] | None
    interest_sources_with_findings: list[str]
    assessments: list[EditorialAssessment]
    limitation: str = (
        "The notes use selected excerpts from the available source versions. "
        "Quote matching verifies text occurrence only. A human editor must verify "
        "the interpretation, source independence, and any publication decision."
    )


class ArticleReport(ContractModel):
    """The claim-by-claim comparison of an original article and supplied sources."""

    case_id: str
    question: str | None
    article_source_id: str
    sources: list[SourceSnapshot]
    status: RecordStatus | Literal["no_claims"]
    extraction_attempts: list[ExtractionAttempt]
    claims: list[ClaimComparison]
    shared_wording: SharedWordingReport = Field(default_factory=SharedWordingReport)
    interests: InterestReport | None = None
    editorial: EditorialReport | None = None


class SearchQuery(ContractModel):
    """Record a search query and its outcome independently of source retrieval."""

    query: str
    status: Literal["completed", "failed"]
    result_count: int
    detail: str | None = None


class DiscoveredSource(ContractModel):
    """Link an attempted search result to its retrieval and selection outcome."""

    source_id: str
    url: AnyHttpUrl
    publisher_priority: bool
    status: Literal["included", "duplicate", "unavailable"]


class SourceDiscovery(ContractModel):
    """Keep the search queries and retrieval decisions for an article case."""

    queries: list[SearchQuery]
    candidates: list[DiscoveredSource]


class ArticleUrlReport(ContractModel):
    """Retrieval outcomes and the comparison based on available snapshots."""

    case_id: str
    question: str | None
    status: RecordStatus | Literal["no_claims"]
    retrievals: list[SourceRetrieval]
    review: ArticleReport | None
    discovery: SourceDiscovery | None = None
