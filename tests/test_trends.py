"""Verify daily coverage parsing and error handling with controlled provider responses."""

from __future__ import annotations

import unittest
from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta
from typing import override
from unittest.mock import patch

import httpx

from quellenlot_agents.trends import (
    TrendEventQuery,
    TrendQuery,
    TrendUnavailable,
    fetch_news_trend,
    fetch_trend_events,
)


class NewsTrendTests(unittest.TestCase):
    """Check the GDELT adapter without relying on the live service."""

    @override
    def setUp(self) -> None:
        """Disable the provider's request interval for mocked HTTP requests."""
        interval = patch("quellenlot_agents.trends._GDELT_REQUEST_INTERVAL", 0)
        interval.start()
        self.addCleanup(interval.stop)

    def test_source_and_missing_days_are_retained(self) -> None:
        """Return sorted provider values while preserving gaps and genuine zeroes."""
        response = httpx.Response(
            200,
            request=httpx.Request("GET", "https://api.gdeltproject.org/"),
            json={
                "timeline": [
                    {
                        "series": "Volume Intensity",
                        "data": [
                            {"date": "20261106T000000Z", "value": 0.21},
                            {"date": "20261104T000000Z", "value": 0},
                        ],
                    }
                ]
            },
        )
        with patch("httpx.stream", return_value=nullcontext(response)) as stream:
            report = fetch_news_trend(TrendQuery(topic="Tankrabatt", days=90))
        self.assertEqual(
            [(point.date, point.value) for point in report.points],
            [(date(2026, 11, 4), 0.0), (date(2026, 11, 6), 0.21)],
        )
        self.assertEqual(
            stream.call_args.kwargs["params"]["query"], '"Tankrabatt" sourcelang:german'
        )
        source_params = httpx.URL(report.source_url).params
        self.assertEqual(source_params["format"], "html")
        self.assertEqual(source_params["timespan"], "90d")

    def test_unavailable_provider_does_not_create_zeroes(self) -> None:
        """Reject upstream errors and malformed values without fabricating measurements."""
        request = httpx.Request("GET", "https://api.gdeltproject.org/")
        for response in (
            httpx.Response(429, request=request),
            httpx.Response(200, request=request, content=b"Unrecognized response"),
        ):
            with (
                self.subTest(response=response),
                patch("httpx.stream", return_value=nullcontext(response)),
                self.assertRaises(TrendUnavailable),
            ):
                fetch_news_trend(TrendQuery(topic="Tankrabatt"))

    def test_event_leads_preserve_index_dates_and_filter_invalid_articles(self) -> None:
        """Request a short UTC window and keep distinct, source-linked leads."""
        peak = datetime.now(UTC).date() - timedelta(days=5)
        indexed = peak + timedelta(days=1)
        article = {
            "title": "Beispielbericht",
            "url": "https://example.org/nachrichten",
            "seendate": indexed.strftime("%Y%m%dT125600Z"),
        }
        response = httpx.Response(
            200,
            request=httpx.Request("GET", "https://api.gdeltproject.org/"),
            json={
                "articles": [
                    article,
                    article,
                    {**article, "url": "https://user@example.org/"},
                    {**article, "url": "file:///tmp/file"},
                    {**article, "url": "https://example.org/old", "seendate": "20010101T000000Z"},
                    {**article, "url": "https://example.org/bad", "seendate": "invalid"},
                    None,
                ]
            },
        )
        with patch("httpx.stream", return_value=nullcontext(response)) as stream:
            report = fetch_trend_events(
                TrendEventQuery(
                    topic="Tankrabatt",
                    language="all",
                    peak_date=peak,
                )
            )
        self.assertEqual(report.window_start, peak - timedelta(days=2))
        self.assertEqual(report.window_end, peak + timedelta(days=2))
        self.assertEqual(report.peak_date, peak)
        self.assertEqual(
            [(entry.title, str(entry.url), entry.indexed_date) for entry in report.articles],
            [("Beispielbericht", article["url"], indexed)],
        )
        self.assertEqual(
            stream.call_args.kwargs["params"],
            {
                "query": '"Tankrabatt"',
                "mode": "ArtList",
                "format": "json",
                "maxrecords": "20",
                "sort": "HybridRel",
                "startdatetime": report.window_start.strftime("%Y%m%d000000"),
                "enddatetime": report.window_end.strftime("%Y%m%d235959"),
            },
        )

    def test_events_reject_dates_outside_archive_before_request(self) -> None:
        """Historical chart dates must never yield fabricated article matches."""
        with (
            patch("httpx.stream") as stream,
            self.assertRaisesRegex(ValueError, "90 UTC-Tage"),
        ):
            fetch_trend_events(TrendEventQuery(topic="Tankrabatt", peak_date=date(2022, 6, 1)))
        stream.assert_not_called()
