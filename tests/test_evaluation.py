"""Verify offline annotated evaluation without running any local models."""

from __future__ import annotations

import json
import unittest

from pydantic import ValidationError

from quellenlot_agents.evaluation import EvaluationDataset, evaluate_reports


def _labels() -> bytes:
    """Return an independently labelled synthetic source relation."""
    return json.dumps({"labels": [{
        "case_id": "library", "claim_id": "claim-1", "source_id": "city",
        "expected_relation": "contradicts", "rationale": "Tuesday differs from Monday.",
        "reference_quote": "Dienstag statt Montag.",
    }]}).encode()


def _report() -> bytes:
    """Return one synthetic report with two disagreements and a model failure."""
    return json.dumps({
        "case_id": "library",
        "claims": [{"claim_id": "claim-1", "review": {"analyses": [
            {"model": "model-a", "status": "succeeded", "findings": [{
                "source_id": "city", "relation": "contradicts",
                "quotes": [{"source_id": "city", "text": "Dienstag statt Montag.", "verified": True}],
            }]},
            {"model": "model-b", "status": "succeeded",
             "findings": [{"source_id": "city", "relation": "supports", "quotes": []}]},
            {"model": "model-c", "status": "failed", "findings": []},
        ]}}],
    }).encode()


class EvaluationTests(unittest.TestCase):
    """Test coverage, confusion, missing data and stable digests."""

    def test_model_accuracy_and_missing_failures(self) -> None:
        """Keep disagreement and failed attempts separate from reference correctness."""
        result = evaluate_reports(_labels(), [_report()])
        self.assertEqual(result.label_count, 1)
        self.assertEqual(result.disputed_pairs, 1)
        self.assertEqual([item.model for item in result.per_model], ["model-a", "model-b", "model-c"])
        a, b, c = result.per_model
        self.assertEqual(a.correct, 1)
        self.assertEqual(a.verified_quotes, 1)
        self.assertEqual(a.reference_quote_matches, 1)
        self.assertEqual(a.confusion["contradicts"]["contradicts"], 1)
        self.assertEqual(b.correct, 0)
        self.assertEqual(c.missing, 1)
        self.assertIsNone(c.accuracy_on_assessed)
        self.assertEqual(result, evaluate_reports(_labels(), [_report()]))

    def test_duplicate_and_missing_annotations(self) -> None:
        """Reject duplicates and unreferenced case IDs rather than hiding gaps."""
        label = json.loads(_labels())["labels"][0]
        with self.assertRaises(ValidationError):
            EvaluationDataset.model_validate({"labels": [label, label]})
        with self.assertRaisesRegex(ValueError, "Missing report"):
            evaluate_reports(json.dumps({"labels": [{**label, "case_id": "absent"}]}).encode(),
                             [_report()])


if __name__ == "__main__":
    unittest.main()
