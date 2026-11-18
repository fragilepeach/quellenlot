# Quellenlot local agent core

Quellenlot's first Python component runs an evidence-first, multi-model review over source snapshots supplied by the user. Inference runs locally through Ollama; no cloud model API, account, or API key is used.

## Workflow

1. Supply an explicit claim or an original article. In article mode, the first model that returns a valid extraction supplies up to five distinct claims anchored to exact quotes. An optional question guides claim selection.
2. Five distinct configured local models independently assess each claim against the supplied source snapshots. Successful models cross-review another model's assessment.
3. A deterministic report preserves disagreements, missing model responses, source versions, and quote-verification results. It does not turn model votes into a truth score.

Models run sequentially. Each Ollama request sets `keep_alive=0` so Ollama unloads that model after the response; only one model needs to be resident at a time. The context is capped at 8,192 tokens by default and can be raised to 16,384. CPU inference is supported, but generation on a laptop CPU can be slow. The largest example model download is about 18 GB; its context cache and the OS also use RAM, so actual peak memory depends on the machine and request length.

The example pool is a starting point, not a validated ranking. It lists Qwen3.8 27B, gpt-oss 20B, Mistral Small 3.2 24B, Gemma 4 12B, and Ministral 3 14B. All run as local weights through Ollama. Model weights are downloaded once; after that, inference can run offline. The license differs by model; check each model card before redistribution or commercial deployment.

## Quick start

Requires Python 3.12+ and a running local Ollama server.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
cp config.example.toml models.toml
```

Pull the models listed in `models.toml` (the first download requires internet access). Then prepare an input JSON:

```json
{
  "case_id": "tankrabatt-001",
  "claim": "The fuel tax cut was fully passed on to consumers.",
  "sources": [
    {
      "source_id": "article-a",
      "version_id": "2026-11-18T09:00:00Z",
      "title": "Example source",
      "url": "https://example.org/article",
      "captured_at": "2026-11-18T09:00:00Z",
      "text": "Paste the relevant source text here.",
      "text_is_complete": true
    }
  ]
}
```

Run the analysis:

```bash
quellenlot-agents --config models.toml --input case.json --output report.json
```

A quote match proves only that the text appears in the supplied snapshot, not that it supports the reasoning. A failed model produces a partial report. Fewer than two successful analyses cannot produce peer review. If every model fails, the command exits nonzero.

### Article input

Use the same CLI command with JSON containing an `article` instead of an explicit `claim`. You can omit the question and submit just the article. To compare sources, add a `comparison_sources` array of snapshots using the same fields as `article`. Source IDs must be unique.

```json
{
  "case_id": "bibliothek-001",
  "article": {
    "source_id": "meldung",
    "version_id": "v1",
    "title": "Neue Bibliothek",
    "url": "https://example.org/meldung",
    "captured_at": "2026-11-18T09:00:00Z",
    "text": "Die Bibliothek öffnet am Montag. Der Eintritt ist frei.",
    "text_is_complete": true
  },
  "question": "Wann öffnet die Bibliothek?",
  "comparison_sources": [
    {
      "source_id": "stadt",
      "version_id": "v1",
      "title": "Information der Stadt",
      "url": "https://example.org/stadt",
      "captured_at": "2026-11-18T09:15:00Z",
      "text": "Die Bibliothek öffnet am Dienstag.",
      "text_is_complete": false
    }
  ]
}
```

Each claim entry contains the original quote, a source comparison in input order, and the detailed review. The comparison groups judgments by source and links exact-match citations to the supplied URL and snapshot version. A judgment may have no exact-match citation. Incomplete snapshots are marked unassessable when a model would otherwise report an omission.

The detailed review holds the claim text, model disagreements, and peer review records. A peer review is successful only when it covers every assigned finding exactly once. If extraction finds no claims, the article report has status `no_claims`. An article run can make up to ten model calls per extracted claim after extraction. Keep source snapshots short enough for the configured context length.

## Development checks

```bash
python -m pip install -e ".[dev]"
pre-commit install
ruff check .
ruff format --check .
pyright
python -m unittest discover -s tests -v
bandit -r src -ll
pip-audit
```

CI runs the checks over the full repository with no changed-file baselines or auto-fixes. It also runs the behavioral tests with simulated Ollama responses and validates the package build.

## Scope boundary

This is a backend library and CLI, not the planned web application. It accepts source snapshots rather than fetching URLs; retrieval, persistence/version history, access control, editorial approval, and public release remain separate work. Local model quality for German political research still needs evaluation against a held-out set before relying on the results.
