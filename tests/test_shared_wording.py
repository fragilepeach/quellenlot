"""Verify shared wording on synthetic news and press-release excerpts."""

import unittest
from datetime import UTC, datetime

from quellenlot_agents.models import SharedWordingReport, SourceInput
from quellenlot_agents.shared_wording import find_shared_wording

_WIRE = (
    "Die Bibliothek am Marktplatz wird nach einer sechsmonatigen Sanierung am kommenden Montag "
    "wieder für Besucherinnen und Besucher aus dem gesamten Landkreis geöffnet."
)
_RELEASE = (
    "Wir werden die Öffnungszeiten im kommenden Frühjahr gemeinsam mit den Mitarbeitenden "
    "und mit den ehrenamtlichen Helferinnen und Helfern neu abstimmen"
)


def _source(source_id: str, text: str) -> SourceInput:
    return SourceInput(
        source_id=source_id,
        version_id=f"{source_id}-v1",
        title=f"Quelle {source_id}",
        captured_at=datetime(2026, 11, 19, tzinfo=UTC),
        text=text,
        text_is_complete=True,
    )


class SharedWordingTests(unittest.TestCase):
    """Exercise near copies, attributed quotations, and distinct reports."""

    def test_lightly_edited_wire_copy_keeps_every_pair_and_original_text(self) -> None:
        """Link three separately edited copies without rewriting the matched excerpts."""
        articles = [
            _source("a", f"{_WIRE}\nIn der Eingangshalle werden Gemälde gezeigt."),
            _source("b", f"{_WIRE.replace('kommenden', 'nächsten')}\nEin Café ist geplant."),
            _source(
                "c", f"{_WIRE.replace('Marktplatz', 'Rathausplatz')}\nDer Stadtrat tagt später."
            ),
        ]
        report = find_shared_wording(articles)
        self.assertEqual(len(report.source_similarities), 3)
        for score in report.source_similarities:
            self.assertIsNotNone(score.score)
            self.assertEqual(score.first.version_id, f"{score.first.source_id}-v1")
            self.assertEqual(score.second.version_id, f"{score.second.source_id}-v1")
        self.assertEqual(
            {(item.first.source_id, item.second.source_id) for item in report.matches},
            {("a", "b"), ("a", "c"), ("b", "c")},
        )
        by_id = {source.source_id: source for source in articles}
        for pair in report.matches:
            self.assertLess(pair.similarity, 100.0)
            for excerpt in (pair.first, pair.second):
                source = by_id[excerpt.source_id]
                self.assertEqual(excerpt.version_id, source.version_id)
                self.assertEqual(excerpt.text, source.text[excerpt.start : excerpt.end])
                self.assertNotIn("\n", excerpt.text)

    def test_shared_release_quote_is_located_inside_distinct_paragraphs(self) -> None:
        """Find a common statement inside two otherwise different paragraphs."""
        first = _source(
            "a",
            f"Die Gewerkschaft fordert längere Schichten am Wochenende. „{_RELEASE}“, "
            "teilte die Bibliothek auf Nachfrage mit.",
        )
        second = _source(
            "b",
            f"Der Bauausschuss debattiert über die Kosten für den Eingangsbereich. «{_RELEASE}», "
            "heißt es in der veröffentlichten Mitteilung.",
        )
        report = find_shared_wording([first, second])
        self.assertEqual(len(report.matches), 1)
        pair = report.matches[0]
        self.assertEqual(pair.first.text, _RELEASE)
        self.assertEqual(pair.second.text, _RELEASE)
        self.assertEqual(pair.similarity, 100.0)
        score = report.source_similarities[0].score
        if score is None:
            self.fail("Both sources have enough text to score.")
        self.assertGreater(score, 0)
        self.assertLess(score, pair.similarity)

    def test_same_topic_and_short_common_phrases_do_not_trigger_matches(self) -> None:
        """Leave independent text about the same event unflagged."""
        original = _source("original", _WIRE)
        independent = _source(
            "other",
            "Am kommenden Montag beginnt am Marktplatz ein neues Kapitel: Die Türen der "
            "Stadtbücherei gehen auf, während der Leihbetrieb zunächst eingeschränkt bleibt.",
        )
        report = find_shared_wording([original, independent])
        self.assertEqual(report.matches, [])
        self.assertEqual(report.source_similarities[0].score, 0.0)

    def test_candidate_limits_are_visible(self) -> None:
        """Record that lengthy repeated sources exceed the bounded matcher."""
        text = "\n".join(_WIRE for _ in range(170))
        report = find_shared_wording([_source("a", text), _source("b", text)])
        self.assertTrue(report.limited)
        self.assertGreater(len(report.matches), 0)
        self.assertEqual(report.source_similarities[0].score, 100.0)

    def test_source_similarity_measures_unique_phrases_across_whole_snapshots(self) -> None:
        """Score the shared wording once and mark very short captures as unavailable."""
        words = "eins zwei drei vier fünf sechs sieben acht neun zehn elf zwölf"
        report = find_shared_wording(
            [
                _source("base", words),
                _source("copy", words.replace("fünf", "fu\u0308nf").upper()),
                _source("longer", f"{words} dreizehn vierzehn fünfzehn sechzehn"),
                _source("short", "Kein auswertbarer Artikel"),
            ]
        )
        scores = {
            (pair.first.source_id, pair.second.source_id): pair.score
            for pair in report.source_similarities
        }
        self.assertEqual(len(scores), 6)
        self.assertEqual(scores["base", "copy"], 100.0)
        self.assertEqual(scores["base", "longer"], 100.0 * 8 / 12)
        self.assertIsNone(scores["base", "short"])

    def test_legacy_shared_wording_report_still_loads(self) -> None:
        """Leave pair scores absent when an old report only contains passage matches."""
        report = SharedWordingReport.model_validate_json('{"matches":[],"limited":false}')
        self.assertEqual(report.source_similarities, [])
