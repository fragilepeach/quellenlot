# Quellenlot agent core

Quellenlot's first Python component runs an evidence-first, multi-model review over sources supplied by the user. It does not fetch URLs or publish findings.

## Workflow

1. Five distinct configured models independently assess the claim against the supplied source snapshots.
2. Available models cross-review another model's assessment. The reviewer is never assigned its own assessment.
3. A deterministic report preserves disagreements, missing model responses, source versions, and quote-verification results. It does not turn model votes into a truth score.

A source excerpt is untrusted input. Prompts explicitly prohibit following instructions found inside it. Model output is parsed into typed schemas; every quoted excerpt is checked against the exact supplied source text. A quote match verifies only that the string appears in that snapshot, not that the reasoning is sound.

## Quick start

Requires Python 3.12+.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
cp config.example.toml models.toml
```

Set each model's API key in the environment variable named by `api_key_env`. Configure five distinct model names and OpenAI-compatible chat-completions endpoints in `models.toml`. Never commit API keys.

Create an input JSON file:

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
      "text": "Paste the source text here.",
      "text_is_complete": true
    }
  ]
}
```

Run the analysis:

```bash
quellenlot-agents --config models.toml --input case.json --output report.json
```

One or more model failures produce a partial report when at least one analysis succeeds. Fewer than two successful analyses cannot produce peer review and are reported as incomplete. The process exits nonzero if every model fails.

## Development checks

```bash
python -m pip install -e ".[dev]"
pre-commit install
ruff check .
ruff format --check .
pyright
bandit -r src -ll
pip-audit
```

CI runs these checks against the entire repository without changed-file baselines or auto-fixes. It also validates the package build. Add behavioral tests alongside each feature before enabling a test-coverage gate.

## Scope boundary

This is a backend library and CLI, not the planned web application. It accepts source snapshots rather than fetching them; source acquisition, persistence/version history, access control, editorial approval, and public release remain separate work.
