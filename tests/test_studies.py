"""Verify claim study discovery, text access and evidence validation with fixed responses."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import httpx

from quellenlot_agents.config import ModelConfig, WorkflowConfig
from quellenlot_agents.studies import find_claim_studies

_CONFIG = WorkflowConfig(
    models=[ModelConfig(id=f"local-{i}", model=f"model-{i}") for i in range(5)]
)
_CLAIM = "Die Steuersenkung wurde vollständig weitergegeben."
_ABSTRACT = "The study measured pump prices during June 2022."
_BODY = (
    "We measured pump prices at 300 German filling stations from June to August 2022. "
    "The comparison found a partial pass-through."
)


class ClaimStudiesTests(unittest.IsolatedAsyncioTestCase):
    """Exercise the same endpoints and local model adapter used by the study panel."""

    async def test_studies_distinguish_full_text_abstract_and_metadata(self) -> None:
        """Check access labels and drop model descriptions without matching excerpts."""
        searches: list[str] = []
        assessed: list[str] = []

        def reply(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/api/chat":
                task = json.loads(request.content)
                prompt = task["messages"][-1]["content"]
                evidence = json.loads(prompt)
                if "text" not in evidence:
                    return httpx.Response(
                        200,
                        json={"message": {"content": '{"query":"German fuel tax pass-through"}'}},
                    )
                assessed.append(evidence["access"])
                known = _BODY if evidence["access"] == "full_text" else _ABSTRACT
                self.assertIn(known, evidence["text"])
                draft = {
                    "relevant": True,
                    "measured": {"value": "Zapfsäulenpreise", "quote": "measured pump prices"},
                    "population": {
                        "value": "300 Tankstellen",
                        "quote": "300 German filling stations",
                    },
                    "period": {"value": "Mai 2022", "quote": "May 2022 never appears"},
                    "finding": {
                        "value": "Teilweise weitergegeben",
                        "quote": "partial pass-through",
                    },
                    "rationale": {"value": "Nur teilweise.", "quote": "partial pass-through"},
                    "relation": "qualifies",
                }
                return httpx.Response(200, json={"message": {"content": json.dumps(draft)}})
            if path == "/works":
                searches.append(request.url.params["query.bibliographic"])
                items = [
                    {"DOI": "10.1234/full", "title": ["Complete paper"], "type": "journal-article"},
                    {
                        "DOI": "10.1234/abstract",
                        "title": ["Abstract paper"],
                        "type": "journal-article",
                        "abstract": "<jats:p>" + _ABSTRACT + "</jats:p>",
                    },
                    {"DOI": "10.1234/metadata", "title": ["Indexed only"], "type": "report"},
                ]
                return httpx.Response(200, json={"message": {"items": items}})
            if path.endswith("/search"):
                doi = request.url.params["query"]
                item = {"doi": "10.1234/full", "pmcid": "PMC123", "isOpenAccess": "Y"}
                return httpx.Response(
                    200, json={"resultList": {"result": [item] if "10.1234/full" in doi else []}}
                )
            if path.endswith("/PMC123/fullTextXML"):
                return httpx.Response(
                    200, text=f"<article><body><sec><p>{_BODY}</p></sec></body></article>"
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(reply)
        client_class = httpx.AsyncClient

        def client_factory(
            *, timeout: httpx.Timeout | float, follow_redirects: bool, trust_env: bool
        ) -> httpx.AsyncClient:
            return client_class(
                transport=transport,
                timeout=timeout,
                follow_redirects=follow_redirects,
                trust_env=trust_env,
            )

        with patch("quellenlot_agents.studies.httpx.AsyncClient", new=client_factory):
            result = await find_claim_studies("claim-1", _CLAIM, _CONFIG)
        self.assertEqual(result.status, "complete")
        self.assertEqual(searches, [_CLAIM, "German fuel tax pass-through"])
        self.assertEqual(assessed, ["full_text", "abstract"])
        self.assertEqual(
            [paper.access for paper in result.papers], ["full_text", "abstract", "metadata"]
        )
        full, abstract, metadata = result.papers
        self.assertEqual(str(full.url), "https://doi.org/10.1234/full")
        self.assertIsNotNone(full.material_url)
        if full.assessment is None or abstract.assessment is None:
            self.fail("Available study text must produce a structured assessment.")
        self.assertEqual(full.assessment.relation, "qualifies")
        self.assertIsNotNone(full.assessment.population)
        self.assertIsNone(full.assessment.period)
        self.assertEqual(abstract.assessment.relation, "unclear")
        self.assertIsNone(abstract.assessment.finding)
        self.assertIsNone(metadata.assessment)
