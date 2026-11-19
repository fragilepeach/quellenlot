"""Typed request and report contracts for a Quellenlot review."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, StringConstraints, model_validator


class ContractModel(BaseModel):
    """Base contract that rejects unknown fields and implicit Python coercions."""

    model_config = ConfigDict(extra="forbid", strict=True)


class SourceInput(ContractModel):
    """An immutable source snapshot supplied to a review."""

    source_id: str = Field(min_length=1, max_length=120)
    version_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    url: AnyHttpUrl | None = None
    captured_at: datetime
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


class ArticleCaseInput(ContractModel):
    """An original article, an optional question, and manually supplied comparisons."""

    case_id: str = Field(min_length=1, max_length=120)
    article: SourceInput
    question: NonBlankStatement | None = None
    comparison_sources: list[SourceInput] = Field(default_factory=list[SourceInput], max_length=19)

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
        return self


class ArticleUrlInput(ContractModel):
    """A public article URL and optional comparison URLs and question."""

    case_id: str = Field(min_length=1, max_length=120)
    article_url: AnyHttpUrl
    question: NonBlankStatement | None = None
    comparison_urls: list[AnyHttpUrl] = Field(default_factory=list[AnyHttpUrl], max_length=19)


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
            content_sha256=source.content_sha256,
            text_is_complete=source.text_is_complete,
        )


class RelationCount(ContractModel):
    """Count of model assessments by relation, without weighting them as truth."""

    relation: Relation
    count: int


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


class ArticleReport(ContractModel):
    """The claim-by-claim comparison of an original article and supplied sources."""

    case_id: str
    question: str | None
    article_source_id: str
    sources: list[SourceSnapshot]
    status: RecordStatus | Literal["no_claims"]
    extraction_attempts: list[ExtractionAttempt]
    claims: list[ClaimComparison]


class SourceRetrieval(ContractModel):
    """The result of retrieving a URL and extracting article text."""

    source_id: str
    requested_url: AnyHttpUrl
    final_url: AnyHttpUrl | None = None
    status: Literal["captured", "partial", "failed"]
    detail: str


class ArticleUrlReport(ContractModel):
    """Retrieval outcomes and the comparison based on available snapshots."""

    case_id: str
    question: str | None
    status: RecordStatus | Literal["no_claims"]
    retrievals: list[SourceRetrieval]
    review: ArticleReport | None
