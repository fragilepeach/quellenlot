"""Test the extraction of explicitly declared dates from article markup."""

import unittest
from datetime import date

from quellenlot_agents.article_html import extract_article
from quellenlot_agents.models import SourceDate


class ArticleDateTests(unittest.TestCase):
    """Check date precision, metadata precedence, and missing or disputed dates."""

    def test_json_ld_uses_article_entities_and_preserves_date_precision(self) -> None:
        """Prefer typed article metadata over irrelevant page dates and lower-priority tags."""
        html = b"""
        <head><meta property="article:published_time" content="2024-04-01">
        <script type="application/ld+json">
        {"@graph":[
          {"@type":"WebPage","datePublished":"2001-01-01"},
          {"@type":["Thing","https://schema.org/NewsArticle"],"datePublished":"2024-04-02"}
        ]}
        </script></head><article><p>Evidence.</p></article>
        """
        article = extract_article(html, None)
        self.assertEqual(
            article.published_at, SourceDate(value=date(2024, 4, 2), provenance="json_ld")
        )
        self.assertIsNone(article.updated_at)

    def test_invalid_json_ld_falls_back_to_explicit_time_markup(self) -> None:
        """Use a labeled article timestamp after invalid metadata and ignore unrelated dates."""
        html = b"""
        <head><script type="application/ld+json">{bad json}</script>
        <meta property="article:modified_time" content="2024-02-31"></head>
        <time itemprop="dateModified" datetime="2004-01-01">Unrelated</time>
        <article><time itemprop="dateModified" datetime="2024-04-03">Changed</time>
        <time datetime="2024-04-04">Event date</time><p>Evidence.</p></article>
        """
        article = extract_article(html, None)
        self.assertIsNone(article.published_at)
        self.assertEqual(
            article.updated_at, SourceDate(value=date(2024, 4, 3), provenance="html_time")
        )

    def test_conflicting_article_dates_are_unknown(self) -> None:
        """Keep a date unknown when the highest-priority channel gives conflicting values."""
        html = b"""
        <head><script type="application/ld+json">
        [{"@type":"NewsArticle","datePublished":"2024-04-01"},
         {"@type":"NewsArticle","datePublished":"2024-04-02"}]
        </script></head><article><p>Evidence.</p></article>
        """
        article = extract_article(html, None)
        self.assertIsNone(article.published_at)
        self.assertIsNone(article.updated_at)
