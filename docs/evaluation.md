# Annotated evaluation of research quality

The quality evaluator reads *saved* article or URL reports and compares independent model judgments against human-written references. It performs **no Ollama calls** and does not fetch external pages.

## Reference labels

Use a JSON file with a top-level `labels` array. Each record needs `case_id`, `claim_id`, `source_id`, `expected_relation` and a reviewer `rationale`. An optional `reference_quote` must be verified by the human annotator against the captured source version. Relations: `supports`, `qualifies`, `contradicts`, `omits`, `not_assessable`. Use `not_assessable` when captured source text is incomplete.

Example:

```json
{"labels":[{"case_id":"bibliothek-001","claim_id":"claim-1","source_id":"stadt","expected_relation":"contradicts","rationale":"The city reports Tuesday, unlike the article's Monday claim.","reference_quote":"Die Bibliothek öffnet am Dienstag."}]}
```

## Run

```sh
quellenlot-eval --labels reviewed-labels.json --report saved-article-a.json --report saved-article-b.json --output evaluation.json
```

The command prints a per-model summary and exports JSON with source-relation confusion matrices, annotated-pair coverage, agreement on assessed cases, verified-quote flags, optional strict reference-quote matches and SHA-256 hashes of the exact inputs. Missing models and claims remain in denominators where applicable. Duplicate reference keys and absent case reports are rejected.

## Interpretation and limitations

Agreement is conditional on independently labelled cases. Quote verification flags mean only that a quotation was previously found in a snapshot; source relevance and factual accuracy still require manual examination. An exact reference quote check is conservative: another valid passage may fail it. Source independence, temporal and causal claims, and political interpretations require a carefully annotated, adjudicated corpus with multiple reviewers.

The included unit tests use synthetic library-opening statements. **They validate arithmetic, not German political fact-checking accuracy or model rankings.** Publish sampling frames, model versions, annotation decisions and disagreement rates alongside any future benchmark conclusions.
