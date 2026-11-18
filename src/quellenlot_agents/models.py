"""Typed request and report contracts for a Quellenlot review."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


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
        """Return the digest identifying the exact source text analyzed."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


class CaseInput(ContractModel):
    """A claim and the source snapshots to evaluate against it."""

    case_id: str = Field(min_length=1, max_length=120)
    claim: str = Field(min_length=1, max_length=4_000)
    sources: list[SourceInput] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def require_unique_source_ids(self) -> CaseInput:
        """Reject ambiguous source references before any model is called."""
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            msg = "Source IDs must be unique within a case."
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
