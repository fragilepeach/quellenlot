"""Verify daily coverage parsing and error handling with controlled provider responses."""

from __future__ import annotations

import unittest
from contextlib import nullcontext
from datetime import date
from unittest.mock import patch

import httpx

from quellenlot_agents.trends import TrendQuery, TrendUnavailable, fetch_news_trend


class NewsTrendTests(unittest.TestCase):
    """Check the GDELT adapter without relying on the live service."""

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
