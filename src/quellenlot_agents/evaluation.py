"""Offline evaluation of saved model judgments against human-annotated sources."""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quellenlot_agents.models import ContractModel, Relation


class EvaluationLabel(ContractModel):
    """One annotated relationship for a claim and versioned comparison source."""

    case_id: str = Field(min_length=1)
    claim_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    expected_relation: Relation
    rationale: str = Field(min_length=1)
    reference_quote: str | None = None


class EvaluationDataset(ContractModel):
    """A bounded reference set without duplicated claim/source labels."""

    labels: list[EvaluationLabel] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_labels(self) -> EvaluationDataset:
        """Reject inconsistent duplicate labels.

        Returns:
            Dataset with one label per case, claim, and source.

        Raises:
            ValueError: The same annotation key is repeated.
        """
        keys = [(item.case_id, item.claim_id, item.source_id) for item in self.labels]
        if len(keys) != len(set(keys)):
            msg = "Duplicate case/claim/source labels are forbidden."
            raise ValueError(msg)
        return self


class _Evidence(BaseModel):
    """A saved quote and the existing exact-snapshot verification flag."""

    model_config = ConfigDict(extra="ignore", strict=True)
    source_id: str
    text: str
    verified: bool


class _Finding(BaseModel):
    """A source judgment from one independently generated analysis."""

    model_config = ConfigDict(extra="ignore", strict=True)
    source_id: str
    relation: Relation
    quotes: list[_Evidence] = Field(default_factory=list[_Evidence])


class _Analysis(BaseModel):
    """Success/failure and findings for one configured model."""

    model_config = ConfigDict(extra="ignore", strict=True)
    model: str
    status: str
    findings: list[_Finding] = Field(default_factory=list[_Finding])


class _Review(BaseModel):
    """Recorded independent analyses for an extracted claim."""

    model_config = ConfigDict(extra="ignore", strict=True)
    analyses: list[_Analysis] = Field(default_factory=list[_Analysis])


class _Claim(BaseModel):
    """One claim and its assessment records."""

    model_config = ConfigDict(extra="ignore", strict=True)
    claim_id: str
    review: _Review


class _Article(BaseModel):
    """Saved article review fields required by this evaluation."""

    model_config = ConfigDict(extra="ignore", strict=True)
    claims: list[_Claim] = Field(default_factory=list[_Claim])


class _Document(BaseModel):
    """Accept either a plain article or URL-wrapped report."""

    model_config = ConfigDict(extra="ignore", strict=True)
    case_id: str
    review: _Article | None = None
    claims: list[_Claim] = Field(default_factory=list[_Claim])

    @property
    def reviewed_claims(self) -> list[_Claim]:
        """Read the independent assessments in either report format.

        Returns:
            Available claim review records, or an empty list for failed runs.
        """
        return self.review.claims if self.review is not None else self.claims


class ModelEvaluation(ContractModel):
    """Per-model reference agreement, coverage, and quote verification."""

    model: str
    expected: int
    assessed: int
    correct: int
    missing: int
    verified_quotes: int
    reference_quote_matches: int
    reference_quote_checks: int
    accuracy_on_assessed: float | None
    correct_over_expected: float
    confusion: dict[str, dict[str, int]]


class EvaluationResult(ContractModel):
    """Reproducible evaluation summary, not a model truthfulness score."""

    label_count: int
    dataset_sha256: str
    report_sha256: dict[str, str]
    per_model: list[ModelEvaluation]
    missing_claims: list[str]
    disputed_pairs: int


def evaluate_reports(dataset_bytes: bytes, report_bytes: list[bytes]) -> EvaluationResult:
    """Compare saved reports against independent labels, without model calls.

    Args:
        dataset_bytes: Exactly the bytes of the reviewer label set.
        report_bytes: Raw bytes of one or more JSON article or URL reports.

    Returns:
        Per-model source relationship, missing, and verified quote metrics.

    Raises:
        ValueError: Annotation case is absent or a report/assessment is duplicated.
    """
    dataset = EvaluationDataset.model_validate_json(dataset_bytes)
    documents = [_Document.model_validate_json(item) for item in report_bytes]
    reports = {item.case_id: item for item in documents}
    if len(reports) != len(documents):
        msg = "Duplicate report case IDs."
        raise ValueError(msg)
    model_names = {
        key: {analysis.model for claim in report.reviewed_claims for analysis in claim.review.analyses}
        for key, report in reports.items()
    }
    all_models = {name for names in model_names.values() for name in names}
    tallies: dict[str, Counter[str]] = {model: Counter() for model in all_models}
    confusion: dict[str, dict[str, Counter[str]]] = {model: {} for model in all_models}
    missing_claims: set[str] = set()
    disagreement: set[tuple[str, str, str]] = set()
    for label in dataset.labels:
        report = reports.get(label.case_id)
        if report is None:
            msg = f"Missing report for annotated case: {label.case_id}"
            raise ValueError(msg)
        matching = [claim for claim in report.reviewed_claims if claim.claim_id == label.claim_id]
        if len(matching) != 1:
            missing_claims.add(f"{label.case_id}/{label.claim_id}")
        analyses = matching[0].review.analyses if len(matching) == 1 else []
        by_model = {item.model: item for item in analyses}
        if len(analyses) != len(by_model):
            msg = f"Duplicate model analyses for {label.case_id}/{label.claim_id}"
            raise ValueError(msg)
        relations: set[str] = set()
        for model in model_names[label.case_id]:
            row = tallies[model]
            row["expected"] += 1
            analysis = by_model.get(model)
            findings = (
                [item for item in analysis.findings if item.source_id == label.source_id]
                if analysis is not None and analysis.status == "succeeded" else []
            )
            if len(findings) != 1:
                row["missing"] += 1
                continue
            finding = findings[0]
            relations.add(finding.relation)
            row["assessed"] += 1
            row["correct"] += int(finding.relation == label.expected_relation)
            row["verified"] += int(any(
                quote.verified and quote.source_id == label.source_id
                for quote in finding.quotes
            ))
            if label.reference_quote is not None:
                row["quote_checks"] += 1
                row["quote_matches"] += int(any(
                    quote.verified and quote.source_id == label.source_id
                    and label.reference_quote in quote.text
                    for quote in finding.quotes
                ))
            confusion[model].setdefault(label.expected_relation, Counter())[finding.relation] += 1
        if len(relations) > 1:
            disagreement.add((label.case_id, label.claim_id, label.source_id))

    return EvaluationResult(
        label_count=len(dataset.labels),
        dataset_sha256=hashlib.sha256(dataset_bytes).hexdigest(),
        report_sha256={
            report.case_id: hashlib.sha256(raw).hexdigest()
            for report, raw in zip(documents, report_bytes, strict=True)
        },
        per_model=[
            ModelEvaluation(
                model=model, expected=tallies[model]["expected"],
                assessed=tallies[model]["assessed"], correct=tallies[model]["correct"],
                missing=tallies[model]["missing"], verified_quotes=tallies[model]["verified"],
                reference_quote_matches=tallies[model]["quote_matches"],
                reference_quote_checks=tallies[model]["quote_checks"],
                accuracy_on_assessed=(
                    tallies[model]["correct"] / tallies[model]["assessed"]
                    if tallies[model]["assessed"] else None
                ),
                correct_over_expected=(
                    tallies[model]["correct"] / tallies[model]["expected"]
                    if tallies[model]["expected"] else 0.0
                ),
                confusion={expected: dict(outcomes) for expected, outcomes
                           in sorted(confusion[model].items())},
            )
            for model in sorted(all_models)
        ],
        missing_claims=sorted(missing_claims),
        disputed_pairs=len(disagreement),
    )


def _parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Evaluate saved Quellenlot reports against independent labels."
    )
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--report", required=True, action="append", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> None:
    """Write deterministic JSON metrics and an accessible textual comparison."""
    parser = _parser()
    args = parser.parse_args()
    try:
        labels = args.labels.read_bytes()
        reports = [path.read_bytes() for path in args.report]
        results = evaluate_reports(labels, reports)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(results.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    sys.stdout.write("Model | Assessed | Correct | Missing | Verified | Label agreement\n")
    for item in results.per_model:
        agreement = (
            f"{item.accuracy_on_assessed:.1%}"
            if item.accuracy_on_assessed is not None else "n/a"
        )
        sys.stdout.write(
            f"{item.model} | {item.assessed}/{item.expected} | {item.correct} | "
            f"{item.missing} | {item.verified_quotes} | {agreement}\n"
        )


if __name__ == "__main__":
    main()
