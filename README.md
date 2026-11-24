# Quellenlot

Quellenlot helps you check claims in German-language news articles. Start with a public article URL or a saved source snapshot, add a question if you have one, and trace each claim back to the passages used to assess it. Model inference runs locally through Ollama without a cloud model API, account, or API key.

Open [the Tankrabatt demo](web/index.html) to explore the interface without Ollama, follow the [guided walkthrough](web/README.md#what-to-look-for-in-the-tankrabatt-demo), or use the [quick start](#quick-start) to analyze your own article.

## From article to editorial review

**Agenten im Prüfverlauf** highlights the active stage and links to its saved results. Open **Einzelbeiträge** on a stage card to see model attempts, failures, and recorded searches. The stages share a pool of five Ollama models, which run sequentially. Code handles retrieval, quotation matching, and text similarity. [Interface guide](web/README.md#agent-roles)

### 1. Behauptungsanalyse · Extract claims

Quellenlot tries the configured models in order until one returns a valid extraction. It identifies up to five checkable claims, prioritizes your question when supplied, and links each item in the article summary to a verbatim passage.

![Follow a highlighted Tankrabatt claim to its evidence](docs/images/generated/usage.gif)

### 2. Quellenrecherche · Find and trace sources

Quellenlot captures the comparison URLs you supply or discovers sources through a configured SearXNG instance. The provenance graph follows explicit links between pages so you can see when several outlets cite the same source. Snapshots retain publication, update, and capture dates separately and show failed or incomplete retrievals.

### 3. Quellenvergleich · Compare the evidence

The models independently assess each claim against the captured sources and cross-review successful findings. The source diff shows where evidence supports, qualifies, or contradicts a claim, where coverage is absent, and where incomplete captures prevent an assessment. [RapidFuzz passage matches and article-pair similarity](docs/images/generated/claim-diff.gif) help you inspect reused wording. In **KI-Plenum**, open the individual judgments, peer reviews, and unresolved objections. Read each verified quotation in context before deciding whether it supports the interpretation.

![Inspect independent judgments and peer review in KI-Plenum](docs/images/generated/plenum.gif)

### 4. Interessenprüfung · Check publisher and author relationships

Enable this stage to examine documented ownership, funding, and affiliations. The report links each finding to its source and shows where the available material leaves a question unresolved.

### 5. Redaktionelle Schlussprüfung · Review before sharing

The models review assigned evidence findings and surface unresolved objections for the editor. You can save a private draft, preview the reader edition, and export it as HTML. Approval is a human decision tied to the exact saved report and draft revision. Editing either invalidates it.

![Follow the five stages and open their saved results](docs/images/generated/agent-workflow.gif)

## Explore related evidence

- **Studies for a claim.** Compare the populations, periods, and results in relevant papers and see whether the assessment used metadata, an abstract, or full text. [Study walkthrough](docs/images/generated/studies.gif)
- **Topic trends and events.** Compare media coverage from GDELT with an imported Google Trends series on separate scales. Add sourced events to the timeline. [Trend walkthrough](docs/images/generated/topic-trends.gif)
- **Party programmes and parliamentary records.** Follow curated programme excerpts through parliamentary motions, votes, and later laws. [Parliamentary records walkthrough](docs/images/generated/parliament.gif)

The [feature gallery](web/README.md#feature-gallery) includes desktop and mobile screenshots and 25 fps walkthroughs recorded with demo or fixture data. The [capture manifest](docs/images/generated/manifest.json) records the tested revision and file hashes. [Mobile screenshot](docs/images/generated/mobile.png) · [320 px light-theme preview](docs/images/generated/light-mobile.png)

![Quellenlot desktop interface](docs/images/generated/desktop.png)

## Quick start

Requires Python 3.12+ and a running local Ollama server. Run the setup from the repository root.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
cp config.example.toml models.toml
```

Pull the models listed in `models.toml` using the commands in [config.example.toml](config.example.toml). The first download requires internet access.

To start a saved browser analysis, run `quellenlot-ui --config models.toml` and open `http://127.0.0.1:8765`. Paste the article URL and any comparison URLs, add a question if needed, and select **Analyse starten**. The [GUI guide](web/README.md#using-the-local-agent) covers saved runs and report imports.

To run a standalone claim through the CLI, prepare an input JSON:

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

A failed model produces a partial report. Fewer than two successful analyses cannot produce peer review. If every model fails, the command exits nonzero.

### Local model execution

Models run sequentially. Each Ollama request sets `keep_alive=0` to unload the model after responding, so the whole pool need not fit in memory simultaneously. The default context limit is 8,192 tokens (configurable up to 16,384); long reports and model generation can still be CPU- and RAM-intensive.

The example pool in [`config.example.toml`](config.example.toml) is **not** a validated ranking: Qwen3.8 27B, gpt-oss 20B, Mistral Small 3.2 24B, Gemma 4 12B, and Ministral 3 14B. Model weights must be downloaded once. The largest example download is approximately 18 GB; model context and the OS consume additional memory. Inspect the individual model licenses before redistribution or commercial use.

## Input and report reference

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

Article reports can include an `article_summary` of up to three sentences drafted during claim extraction. Each sentence carries the ID of a distinct claim with a verified article quote. This is a summary of what the article says.

Each claim entry contains the original quote, a source comparison in input order, and the detailed review. The comparison groups judgments by source and links exact-match citations to the supplied URL and snapshot version. A judgment may have no exact-match citation. Incomplete snapshots are marked unassessable when a model would otherwise report an omission.

The detailed review holds the claim text, model disagreements, and peer review records. A peer review is successful only when it covers every assigned finding exactly once. If extraction finds no claims, the article report has status `no_claims`.

An article run can make up to ten model calls per extracted claim after extraction. Keep source snapshots short enough for the configured context length.

Sources record optional `published_at` and `updated_at` separately from `captured_at`. A manually supplied snapshot can include `"published_at": {"value": "2024-04-02"}`. Use an ISO date or timestamp and include the UTC offset when known. Missing dates are represented as `null`. The extraction, comparison, and peer-review prompts use the dates as context for time-sensitive claims and distinguish them from the times of events described in the article.

### Article URLs

Pass the same command a case with `article_url` and optionally `comparison_urls` and `question`.

```json
{
  "case_id": "bibliothek-url-001",
  "article_url": "https://example.org/meldung",
  "question": "Wann öffnet die Bibliothek?",
  "comparison_urls": ["https://example.org/stadt"]
}
```

The CLI fetches public HTTP(S) pages on the default ports and extracts readable text from static HTML. Each snapshot records the final URL and capture time. The JSON report records each attempted URL under `retrievals` and puts the article comparison under `review`. Failed comparison fetches leave the remaining sources available for review and mark the overall report `partial`. If the original cannot be fetched, the CLI writes the retrieval failure and exits with code 2.

Fetched text is always marked as having unverified completeness. The retrieval report also flags observable limits such as restricted access, a partial HTTP response, fallback to page text, or snapshot clipping. Omissions from these snapshots are reported as `not_assessable`. Use the text input mode to supply a complete snapshot you have verified. URL intake works with server-rendered HTML. Pages that require login, JavaScript rendering, or another document format may need text input.

For fetched pages, Quellenlot records explicitly declared dates and their provenance. It checks Article JSON-LD (`datePublished` and `dateModified`), then Open Graph article metadata, then labeled `<time>` elements within the article. If the highest-priority available channel gives conflicting values for a date, that date is left unknown. Date-only values remain dates, and timestamps without a UTC offset retain their unspecified timezone.

Each successful `retrievals` entry embeds the saved, versioned text under `snapshot`. Failed entries retain an attempt timestamp and the failure detail. Review quotes refer to a snapshot by source and version ID. When a quote occurs exactly once, `start` and `end` give its zero-based character offsets in that text, with an exclusive end. URL reports contain the captured article text and should be shared accordingly.

The URL workflow follows visible links from the extracted article or main content. It follows up to two hops and makes up to eight additional retrievals, giving priority within each hop to URLs linked by several sources. Redirect aliases and common tracking parameters are resolved when grouping shared targets. A link to an inaccessible page remains visible in the report, and `provenance.limited` records when traversal or link extraction reached a cap. These article-level links document where one page points to another. Claim-level support is assessed separately in `review`. Import the URL report into the GUI to inspect shared link targets and the exact text of the links.

### Automatic comparison search

To discover comparison sources from an article URL, add a `[search]` section to `models.toml` and omit `comparison_urls` from the input JSON. Supply a trusted [SearXNG endpoint](https://docs.searxng.org/dev/search_api) with JSON enabled in its `search.formats` settings. A locally hosted instance works without an API key.

```toml
[search]
endpoint = "http://127.0.0.1:8888/search"
language = "de-DE"
max_sources = 3
```

Quellenlot searches the extracted claims and, if supplied, the question anchored to the first claim. The configured search instance and its upstream search providers receive these queries. The search samples up to 20 results per query, gives preference to government and public institution domains in a fixed list, then tries up to twice `max_sources` URLs to capture unique articles. This preference is based on the publisher's domain. The normal evidence review assesses each captured source and its quotes.

The report lists the executed queries under `discovery.queries`, shows attempted candidates and selection outcomes under `discovery.candidates`, and records individual fetch failures under `retrievals`. Search failures and searches with zero usable comparisons produce a partial report when the original can still be reviewed. Explicit comparison URLs take precedence whenever you supply them.

### Studies for a claim

Start the [local browser interface](web/README.md#using-the-local-agent), reopen a saved analysis, and select a claim. **Studien suchen** searches Crossref and checks up to five candidate DOIs in Europe PMC. The selected claim and locally generated search terms are sent to Crossref. The first configured Ollama model reads the available text locally.

Each result links to the paper and identifies metadata-only, abstract, or full-text access. The interface marks when only excerpts entered the model and shows the supported fields with their exact quotations. A second configured Ollama model checks the study's relation to the claim and the proposed rationale before they appear. When the second check does not confirm the interpretation, the study card marks the relation as unclear and shows the source excerpts. Results are cached by claim alongside the saved run. See the [GUI guide](web/README.md#studies-for-a-claim) for the walkthrough.

### Shared wording

The `shared_wording` field appears in the standalone claim report or once on the article report (`review.shared_wording` for a URL case). Open **Textähnlichkeit der Quellen** below the source graph in the browser to compare every pair of captured articles. Each score links to the two source versions in `shared_wording.source_similarities`. [Browser guide and previews](web/README.md#source-article-similarity)

The score is the percentage of distinct five-token phrases that appear in both snapshots out of all such phrases in either snapshot (Jaccard similarity). It treats upper- and lowercase alike and counts repeated phrases once. Zero means the captures share no five-token phrases. A score of 100 means their phrase sets match. If either snapshot has fewer than 12 tokens, `score` is `null`. The browser flags captures whose completeness is unverified. Quellenlot calculates the score locally from the available text without an additional model call.

The `matches` list contains individual passage matches found with RapidFuzz. Each match contains excerpts from both source versions, their zero-based character offsets in those snapshots, and an ordered-token similarity score from 0 to 100. The ending offset is exclusive.

The matcher looks for lightly edited paragraphs, sentences, and quoted passages. It requires at least 12 tokens and a similarity score of 90. It samples up to 160 passage windows per source and reports up to three matches per source pair and 60 per case. The `limited` flag indicates when a candidate or reporting cap was reached.

Shared wording can come from syndication, attributed quotations, or a common press release. The article score measures wording, so independently phrased accounts of the same event can score low. The report retains all source findings so that additions, changes in numbers or wording, and distinct reporting are visible. Source publication, update, and capture dates describe the available snapshots. Establishing who first published a particular passage requires dated versions of the passage itself.

### Claim-level source diff

Each claim review includes a `source_diff`. In a standalone claim report it is at the top level. In an article report it is under each `claims[].review`. The diff keeps sources in input order, with publication and update dates, independent model judgments, and references to their verified quotes in an evidence table.

The evidence table groups identical quotes from multiple sources when their occurrences are inside a matched passage. Source-specific excerpts and variants stay visible, including quotes that combine reused wording with additional reporting. A citation with a unique location in its snapshot includes zero-based character offsets and any overlapping `shared_wording_match_indexes`. These indexes refer to the standalone report's `shared_wording.matches` or to the enclosing article report's list. Repeated occurrences in a single source leave the exact offsets unknown.

Model disagreements remain visible as separate judgments. An incomplete snapshot yields `not_assessable` when a model would otherwise label a claim omitted. Each row's evidence references cover verified citations from source analysis. Peer-review evidence and retrieval outcomes remain available in the detailed report.

### Targeted second-look checks

By default, no extra follow-up models are called. To enable bounded, source-specific follow-ups for peer-review challenges or conflicting model relations, set `targeted_rechecks = 1` (or at most 2) in the top level of `models.toml`. Each disputed source is sent once to a third configured local model alongside the competing interpretations; the full five-model assessment is **not repeated**. New `targeted_checks` records preserve the model, exact source version, verified quotation if present, and failures. They never overwrite initial findings or resolve human editorial objections automatically. [Plenum walkthrough and limitations](web/README.md#ki-plenum).

### Publisher and author relationships

Set `check_interests = true` in the top-level `models.toml` configuration to run a separate interests investigation. When a SearXNG `[search]` section is configured, Quellenlot searches each available source's declared publisher and up to two named authors for ownership, funding, and affiliations. It captures up to three evidence pages per source, keeps the queries and retrieval outcomes, and asks all five local models to assess their contents sequentially. Without a search endpoint, the report records missing evidence.

Article inputs may also supply an `interest_evidence` list with `target_source_id` and a full `source` snapshot. URL inputs accept `interest_urls`, each with a `target_source_id` and `url`. For URL cases, use `article` for the original or an ID such as `comparison-1` for a supplied comparison URL. Explicit interest evidence is used in place of automatic discovery for that source.

The `interests` section of the article report records source metadata, retrieved evidence versions, search attempts, and each model's findings about ownership, funding, author affiliations, and political affiliations. Every reported relationship must cite an exact passage in an evidence snapshot that names both parties. Each model and source also lists categories that remain unresolved. A model failure remains visible. An exact quote match establishes that the text appears in the captured evidence. The reviewer still needs to verify the relationship and its editorial significance.

### Final editorial assessment

Article cases include an `editorial` section. For each claim it lists the verified comparison evidence IDs, sources without verified quotes, the underlying review status, and the number of unresolved disagreements. It links to the separate interests report by source ID and records incomplete snapshots and URL retrieval or discovery gaps.

When at least one claim has verified comparison excerpts, each of the five models receives up to three passages per eligible claim, with preference for covering conflicting, qualifying, and supporting judgments. The input marks shared wording, clipped excerpts, dates, and examples of unresolved dissent. Each model returns one note per eligible claim with evidence references and a follow-up check where warranted. The selected source findings have stable IDs. The model must return one outcome and explanation for each assigned finding. Missing, repeated, and foreign IDs or citations invalidate the response. The report records how many comparison findings stayed outside the editorial selection, carries the original dissent into the editorial coverage, and flags findings challenged or left unclear by any final reviewer. The source diff retains all model findings and verified excerpts.

The editorial status describes assessment coverage. Unresolved disagreements remain visible even when every assigned finding was reviewed. It is `complete` when every claim has comparison evidence, all five notes are available, and the earlier review, search, and retrieval stages finished without reported failures. An article with no verified comparison excerpt gets `no_comparison_evidence` and skips the additional model calls. The notes ask a human editor to verify interpretations and source independence before making any publication decision.

### Per-model performance metrics

A completed local run now stores one observation per Ollama call in `model_calls`: model name, task schema, success/failure, total wall time, and—when Ollama supplies them—prompt tokens, generated tokens, and generation duration. Open **Modellleistung · Laufzeit und Token** in the saved browser report to compare attempts grouped by model and role. The values are observations of this run, not benchmark rankings. Token/s is calculated only if generation counts and durations are available for every call in the row. No peak RAM value is fabricated: it is explicitly **Nicht erfasst**. CLI reports also include the call records; older reports do not.

[GUI metrics screenshots and 25 fps walkthrough](web/README.md#model-performance-metrics)

## Benchmark and troubleshoot

### CPU benchmark on the self-hosted Docker runner

The [dedicated benchmark workflow](https://github.com/fragilepeach/quellenlot/blob/codex/self-hosted-ollama-benchmark/.github/workflows/ollama-benchmark.yml) runs only on a self-hosted Linux x64 runner with the `docker` label. The benchmark uses three serial repetitions of a fixed Tankrabatt claim and comparison snapshots. The Docker volume `quellenlot-ollama-models` keeps model weights across runs; only missing models are pulled.

Open the [benchmark workflow runs](https://github.com/fragilepeach/quellenlot/actions/workflows/ollama-benchmark.yml) for execution status and the `quellenlot-ollama-benchmark` artifact. It contains plots, per-request timings and sampled Ollama process RAM, and saved reports when the requests complete. This fixed-claim benchmark measures runtime and response validation. Use the annotated evaluation below for agreement with reference judgments.

### Common setup issues

| Symptom | Check |
| --- | --- |
| Only the static demo appears | Launch `quellenlot-ui --config models.toml` and open `http://127.0.0.1:8765` rather than the HTML file |
| Models fail or are very slow | Confirm Ollama is running and that each configured weight is installed; check available RAM and context settings |
| No comparison sources are discovered | Supply comparison URLs explicitly or enable a reachable SearXNG endpoint with JSON search enabled |
| A page is missing evidence | Inspect **Abrufprobleme**; the HTML-only URL intake cannot handle every website or paywall |
| Study or trend results are unavailable | Those features require a network path to Crossref/Europe PMC or GDELT; importing a Google Trends CSV works in the browser |

## Research-quality evaluation

Python and browser CI use controlled fixtures to check software behavior. Evaluating German-language fact-checking quality requires independently annotated cases and a real-source audit.

Run `quellenlot-eval` on saved reports and independently annotated claim/source labels to measure per-model coverage, agreement, missing findings, citation verification and relation confusion. Input SHA-256 hashes make repeated evaluations auditable. This is a **measurement harness**, not proof of model reliability; no real-world reference corpus is bundled. [Evaluation guide and label schema](docs/evaluation.md).

## Development checks

Update this README and any relevant feature guides in the same pull request as every new feature. Cover usage, configuration, and limitations that affect users. For GUI changes, refresh the affected screenshots and walkthroughs through the preview workflow.

```bash
python -m pip install -e ".[dev]"
pre-commit install
pre-commit run --all-files
python -m unittest discover -s tests -v
pip-audit
python -m build
twine check dist/*
```

The [Python quality workflow](.github/workflows/python-quality.yml) runs the full suite on pushes, pull request updates, merge-queue events, and manual runs. The checks cover every tracked Python source and stub, including tests and tooling, without a changed-file baseline or CI auto-fixes.

- Ruff enforces linting, formatting, annotations, and Google-style docstrings. The documentation contract checks descriptive summaries and applicable `Args`, `Returns`, `Yields`, and `Raises` sections for public APIs. It rejects explicit generic annotations and inline diagnostic suppressions.
- Pyright runs in strict mode with warnings treated as failures. Astral's ty enables every rule as an error.
- CrossHair checks exact peer-review coverage and how the workflow handles apparent omissions in incomplete sources. The symbolic coverage check uses assignments of up to three findings. Import Linter enforces the package layers, and Vulture checks high-confidence dead code.
- Actionlint, Zizmor, and Yamllint validate workflow definitions. CI also runs Bandit, the dependency audit, deterministic behavioral tests with fixture HTML and simulated Ollama responses, and the package build checks.

## Private authenticated hosting

Quellenlot can run as a private HTTPS editorial workspace behind a Caddy Basic Authentication reverse proxy. Its Python API stays bound to loopback and validates the public Host/Origin pair; saved analyses, private drafts and approvals remain behind authentication. Public publication is a separate explicit export action. [Linux Docker Compose deployment and security notes](deploy/README.md).

