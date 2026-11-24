# Quellenlot browser interface

Open `web/index.html` in a modern browser for the static demo or to import a report. The Tankrabatt case opens by default. Its input article and summary are written for the demo. Its evidence passages and external links come from published sources. Start the [local browser server](#using-the-local-agent) to run and save analyses, search for papers, fetch GDELT news trends, and approve editorial drafts. Both modes use local HTML, CSS and JavaScript with no build step.

Quellenlot opens in dark mode. Use **Dunkles Design** in the header to switch between dark and light. The browser remembers your selection when local storage is available. Headings and evidence quotations use IBM Plex Mono, bundled under its [Open Font License](fonts/IBM-Plex-Mono-OFL.txt).

## Feature gallery

![Desktop view showing the Tankrabatt summary and the selected claim's evidence and citation path](../docs/images/generated/desktop.png)

<details>
<summary>Mobile view</summary>

<img src="../docs/images/generated/mobile.png" alt="Mobile Quellenlot layout with the URL form, Tankrabatt summary, claims and evidence stacked vertically" width="350">

</details>

### Follow an article claim to its source

1. Open the Tankrabatt example and select **in allen drei Monaten gleich stark gewirkt**.
2. Choose **TU Dresden** to read the passage that disputes the claim. Open **Datum und Version** to inspect when the report was published and updated.
3. In **Herkunft & Belege**, follow the dashed citation arrow from **TU Dresden** to **Freitas & Syga**. Select the study node and choose **Beurteilungen ansehen** to jump to the updated evidence panel.
4. Drag a node to reposition it. With a node focused, use the arrow keys to move it and Enter to select it.

![Animated walkthrough from the highlighted Tankrabatt claim to the TU Dresden passage and its cited Freitas–Syga study](../docs/images/generated/usage.gif)

The walkthroughs play at 25 frames per second. The article demo includes published evidence, and the parliamentary case uses curated official records. Local analyses, imported comparison and editorial reports, paper searches and trend responses use controlled demonstration data.

<details>
<summary>Mobile navigation, themes and static export</summary>

Select a claim to jump to its evidence and return to the same claim. Switch the theme and use **Anfrage speichern** to download a local CLI request as `case.json`.

[Light theme screenshot](../docs/images/generated/light-mobile.png)

![Follow a claim on a phone, switch to light mode and export a CLI request](../docs/images/generated/mobile-workflow.gif)

</details>

<details>
<summary>Local analyses and saved runs</summary>

Start an analysis with the article, a comparison URL and a question. Inspect progress and retrieval issues, then reopen the saved run.

![Local analysis showing a failed comparison-source fetch and the available report](../docs/images/generated/local-analysis.png)

![Start an analysis, inspect retrieval issues and open saved runs](../docs/images/generated/local-analysis.gif)

</details>

<details>
<summary>Agent roles and live progress</summary>

The five cards follow an analysis from the original article to the editorial assessment. Choose a role with an available result to inspect its evidence. [Agent roles and status labels](#agent-roles)

![Five agent roles with the interests check active and editorial assessment pending](../docs/images/generated/agent-workflow.png)

[Mobile screenshot](../docs/images/generated/agent-workflow-mobile.png)

![Follow all five active roles in order and open a result](../docs/images/generated/agent-workflow.gif)

</details>

<details>
<summary>Claim-level comparison</summary>

Read the dated source judgments, open the exact quotes, and expand a RapidFuzz match to inspect the changed words. Open **Textähnlichkeit der Quellen** to compare wording across pairs of captured articles.

![Exact quotations in a claim comparison with changed words highlighted](../docs/images/generated/claim-diff.png)

![Inspect the chronology, open a wording comparison, and view the similarity scores](../docs/images/generated/claim-diff.gif)

[Similarity scores on desktop and mobile](#source-article-similarity)

</details>

<details>
<summary>Report import, shared citations and source interests</summary>

Open a JSON report, inspect the funding record and outstanding ownership question, then trace two sources to the same upstream study.

![Source graph with two articles citing one shared study](../docs/images/generated/shared-provenance.png)

![Private funding evidence and an unresolved ownership category](../docs/images/generated/source-interests.png)

![Inspect an imported report, record a private draft, and trace the shared citation](../docs/images/generated/report-import.gif)

</details>

<details>
<summary>KI-Plenum</summary>

Expand the independent model analyses, peer-review outcomes, verified quotations and unresolved objections.

![Independent findings and objections in the KI-Plenum](../docs/images/generated/plenum.png)

![Open the KI-Plenum and inspect the peer-review evidence](../docs/images/generated/plenum.gif)

</details>

<details>
<summary>Studies for a claim</summary>

Search for papers and open the quotation that supports an extracted finding. Compare the assessed material with metadata-only results.

![Study cards showing access, observation period and findings](../docs/images/generated/studies.png)

[Mobile screenshot](../docs/images/generated/studies-mobile.png)

![Search for studies and inspect quoted evidence](../docs/images/generated/studies.gif)

</details>

<details>
<summary>Topic trends and event timeline</summary>

Load the GDELT news series and a Google Trends CSV, investigate a peak, and add a dated event with a source link.

![News coverage and search interest on desktop](../docs/images/generated/trends-desktop.png)

[Mobile screenshot](../docs/images/generated/trends-mobile.png)

![Suggested article, date and evidence fields, and recorded events](../docs/images/generated/trend-events.png)

![Explore both trend series and add a dated event](../docs/images/generated/topic-trends.gif)

</details>

<details>
<summary>Private editorial review and reader edition</summary>

Save draft text, reopen it, complete the release checks and inspect the approved reader page. The local workflow offers approved JSON and HTML downloads.

![Private editorial review with assigned evidence](../docs/images/generated/editorial-draft.png)

![Approved reader page with publication controls and approval details](../docs/images/generated/reader-preview.png)

![Save and approve text and open the reader preview](../docs/images/generated/editorial-review.gif)

</details>

<details>
<summary>Party programmes, parliamentary votes and laws</summary>

Compare programme excerpts with a policy answer, inspect the final vote and amendment tallies, and follow the link to the subsequent law.

![Programme comparison and official records for the 2025 debt rule changes](../docs/images/generated/parliament.png)

![Compare programme positions, roll calls and later implementation](../docs/images/generated/parliament.gif)

</details>

## Party programmes and parliamentary records

Choose **Programme & Abstimmungen** from the header. In the first case, compare the CDU/CSU and SPD programme excerpts on the debt rule and optionally answer the policy statement yourself. The comparison distinguishes a clear programme position from an open interpretation. Your answer stays in the open page.

Follow the timeline to compare the FDP amendment with the subsequent final vote. Each roll call links its parliamentary text, official voting record, and the available debate context. The tables include the total and the selected caucuses, with non-votes shown separately from abstentions. The last records link the constitutional amendment's publication and the later law establishing the infrastructure fund.

Cases are curated in [parliament-data.js](parliament-data.js). To add a case, supply exact programme and motion excerpts, document locators, dated records, verified vote totals, and later actions with primary-source links. Keep editorial interpretations explicit about whether a programme addresses the precise policy in the statement. The interface supports multiple cases through a case picker.

## How the previews are generated

The [GUI previews workflow](../.github/workflows/gui-previews.yml) runs the static demo and local-server fixtures in headless Chromium. It checks the same controls shown in the gallery, plus keyboard navigation, offline fonts, theme persistence, compatibility with earlier reports, and approval invalidation after editing. The GIFs record browser interactions and scrolling, with brief holds for reading. The [capture manifest](../docs/images/generated/manifest.json) records the tested revision, run, dimensions, frame counts, frame rates, file sizes and SHA-256 hashes.

Pull requests that change the browser interface or its capture code upload a **quellenlot-gui-previews** artifact to the Actions run. A successful run on `main` refreshes the tracked gallery when its media change. You can also run the workflow manually for `main`.

To generate the files locally from the repository root, install Node.js and FFmpeg (including `ffprobe`), then run:

```sh
npm ci --prefix tools/ci/gui-preview --ignore-scripts
tools/ci/gui-preview/node_modules/.bin/playwright install chromium
node tools/ci/gui-preview/capture.cjs
```

The output is written to `artifacts/gui-preview/`. The captures use the built-in demo and fixture responses, so they run without Ollama.

## Design research

| Reference | Design decision |
| --- | --- |
| [Full Fact methodology](https://fullfact.org/about/frequently-asked-questions/) | Keep the submitted article's words, the assessment and the supporting material separately identifiable. |
| [Liu, Zhang and Liang, EMNLP 2023](https://aclanthology.org/2023.findings-emnlp.467/) | A citation needs to support the specific statement. Place the excerpt and its relationship beside the focused claim. |
| [W3C Web Annotation Data Model](https://www.w3.org/TR/annotation-model/#text-quote-selector) | The production anchor should combine a snapshot version, exact text and surrounding context. For now, show the report's verified excerpt alongside a link to the external page. |
| [W3C PROV-O](https://www.w3.org/TR/prov-o/) and [Litmaps reference views](https://docs.litmaps.com/en/articles/11128319-make-a-litmap-with-an-article-s-references) | Scope the graph to the selected claim. Label the evidence relationship and show explicit source-to-source citations as distinct edges. |
| [GOV.UK Details](https://design-system.service.gov.uk/components/details/) and [WCAG 2.2](https://www.w3.org/TR/WCAG22/) | Keep the excerpt visible. Expand secondary metadata on demand. Make the claim and source controls keyboard operable and give relationship labels readable text. |

## Interaction and rationale

1. Paste one or more links and optionally ask a question. The first link is the article. The rest are comparisons. This matches the CLI and gives an explicit answer when several URLs are supplied.
2. Read an attributed summary, then select a highlighted phrase or a claim in the list. The selected claim drives the article excerpt and source assessments. The graph connects the claim to its assessed sources and draws documented source-to-source citations as dashed arrows. Outlets that cite the same study share a target node.
3. Inspect the exact passage, the type of evidence relationship and the document dates. Publication, modification and capture are separate. A web page may have changed since capture. Evidence without a verified excerpt stays visibly marked.
4. If a source states where its finding comes from, show that citation. In the demo, the TU Dresden announcement points to the same Freitas–Syga study shown in the graph. An inferred historical origin or a duplicate-detection result needs separate treatment.

The reading view keeps the article and the selected claim’s evidence in view side by side. On narrow screens, selecting a claim moves focus to its evidence heading.

## Model performance metrics

Open **Modellleistung · Laufzeit und Token** in a completed local analysis. The table groups saved `model_calls` observations by model name and task type. It displays call count, failed calls, cumulative wall-clock duration, generated tokens and effective generation tokens per second **only when Ollama supplied both the token count and evaluation duration for every call**. If the counters are missing, they remain unreported; a blank memory measurement is displayed as **Nicht erfasst**. Context preparation, prompt processing, loading, response validation and source retrieval can make wall time significantly different from generation duration. A successful fixture-driven browser test is not a real hardware benchmark. No extra Ollama requests are made to draw the table.

![Per-model timing and generation statistics](../docs/images/generated/model-metrics.png)

[Mobile screenshot](../docs/images/generated/model-metrics-mobile.png)

![Inspect per-model statistics in a saved run](../docs/images/generated/model-metrics.gif)

## Agent roles

Select **Einzelbeiträge** on a role card to open **Modellbeiträge und Prüfpfad**, which lists recorded model IDs and model names, source or claim context, successful and failed attempts, peer-review partners, failure codes, and the count of judgments or unresolved categories. The sources/research role explicitly labels deterministic retrieval and SearXNG search as **Code, kein KI-Modell**, rather than inventing a model identity. It retains the original order, and reports that lack detailed model records say so. During an active run the inspector is unavailable until a saved report exists. Open **KI-Plenum** for full source-linked judgments and review reasons. The built-in static Tankrabatt demo has no real model execution trace.

![Recorded model contributions and peer-review outcomes](../docs/images/generated/agent-inspector.png)

[Mobile inspector screenshot](../docs/images/generated/agent-inspector-mobile.png)

![Open model contributions from the five-stage workflow](../docs/images/generated/agent-inspector.gif)


**Agenten im Prüfverlauf** shows the five roles below the article form. During a local run, the panel shows the article URL and marks the role reported by the server **Läuft**. **Phase beendet** means the run moved past that role. The interests check is optional.

| Role | Opens the available result |
| --- | --- |
| **Behauptungsanalyse** | The linked summary when available, otherwise the extracted claims |
| **Quellenrecherche** | Source links and provenance, or the retrieval issues when the graph is unavailable |
| **Quellenvergleich** | Evidence for the selected claim, including the KI-Plenum when the report has model and peer reviews |
| **Interessenprüfung** | Documented ownership, funding, and affiliations in the private review |
| **Redaktionelle Schlussprüfung** | Model notes, assigned findings, and unresolved objections in the private review |

The built-in case marks its sample results **Beispiel**. Saved and imported reports show available results, partial results, or missing evidence. Older reports still open and show **Kein Ergebnis** where they lack information for a role.

## Private HTTPS hosting

The [private Docker Compose deployment](../deploy/README.md) uses Caddy HTTPS authentication on all pages and API requests. The browser supports saved analyses from a configured HTTPS origin while the Python server remains loopback-only. Basic auth is intended for a single trusted editor; an explicit approved HTML export is still required to share a public reader edition.

## Using the local agent

From the repository root with the package installed and Ollama running, launch the local server:

```bash
quellenlot-ui --config models.toml
```

Open `http://127.0.0.1:8765` and select **Analyse starten**. The form shows each stage and opens the report when the analysis ends. **Abrufprobleme** lists unavailable or partially captured sources. **Gespeicherte Analysen** reopens earlier runs, including the last saved checkpoint of an interrupted run. One run can be active at a time in the server.

The server binds to `127.0.0.1`. Runs stay under `$XDG_DATA_HOME/quellenlot/runs` (default `~/.local/share/quellenlot/runs`), with `case.json`, `status.json`, and the latest `report.json` under each run ID. The report contains the captured snapshots. Pass `--runs-dir` to choose another directory or `--port` to change the browser port. Keep the Ollama server running while the analysis is underway.

For the static file workflow, open `web/index.html`, save the form as `case.json`, then run the CLI from an environment with the configured Ollama models:

```sh
quellenlot-agents --config models.toml --input case.json --output report.json
```

Open `report.json` with **Bericht öffnen**. Both article report shapes are supported, including partial runs, failed URL retrieval and runs with no extractable claims. When the report includes a model-written summary, select a sentence to open its claim and article quote. Older reports still open with their extracted claims and source judgments.

**Quellenvergleich** orders the selected claim's sources by publication day and displays update dates alongside them. Sources with unknown publication dates appear last. Select a source to read each model's reasoning and inspect the capture time and snapshot version. **Nicht behandelt** means a model found no coverage in the supplied text. **Nicht beurteilbar** also covers omissions that could not be assessed from an incomplete excerpt.

Repeated verified quotations link to one excerpt with a link for each source. **Mögliche Textübernahme** shows RapidFuzz matches linked to the selected claim's citations. Expand a match to see the original passages and highlighted wording changes. A match can reflect common wording or a common upstream source. Publication and update dates establish the visible chronology of the sources. The exact origin of the wording requires separate evidence.

## Source article similarity

Open **Textähnlichkeit der Quellen** below the source graph in a newly generated article report. The table ranks each pair of captured articles by how much wording they share. It counts distinct five-token phrases, so one verbatim quotation can yield a high passage match and a much lower score across the two articles.

**Vollständigkeit ungeprüft** means the score covers the available capture. **Zu wenig Text** means one capture contains fewer than 12 tokens. Generate a new report to see scores for a case saved before this feature.

![Article-pair wording scores showing two matching captures, a partial overlap, no overlap, and a capture with too little text](../docs/images/generated/source-similarity.png)

[Mobile preview](../docs/images/generated/source-similarity-mobile.png)

## Studies for a claim

![Saved claim study results showing full-text and metadata-only access, the observation period, and its source excerpt](../docs/images/generated/studies.png)

[Mobile preview](../docs/images/generated/studies-mobile.png)

Open a saved local run, select a claim, and click **Studien suchen**. Quellenlot sends the selected claim and an English query generated locally to [Crossref](https://www.crossref.org/documentation/retrieve-metadata/rest-api/), then checks candidate DOIs for abstracts and open full text in [Europe PMC](https://dev.europepmc.org/RestfulWebService). The article, question, and editorial notes are not part of the search request.

Results distinguish metadata-only candidates, a retrieved abstract, and a retrieved full text. If the text exceeds the model input limit, the interface marks that excerpts were assessed. The study publication year and observation period are displayed separately. The local model describes the measure, population and place, observation period, finding, and its relationship to the claim. Fields need a matching quotation to appear. An exact quotation confirms that the words occur in the source. The interpretation still needs reading in context.

The search checks up to five distinct candidate DOIs. The first configured Ollama model extracts source-backed details. A second configured model independently checks any directional conclusion against the retrieved text. Quellenlot shows the rationale only when the second model agrees with the relation and confirms the interpretation. Otherwise the card shows an unclear relation alongside the extracted material. Older results keep their excerpts and need a fresh search for a reviewed relation.

Results are saved with the run for that claim, separately from the private editorial report. Start the search again to refresh the results. Publisher paywalls and PDFs outside the supported repository can leave a paper at abstract or metadata access.

## KI-Plenum

When `targeted_rechecks` is enabled in `models.toml`, the Plenum displays **Gezielte Nachprüfungen** for sources with a challenged or unclear peer review, then other conflicting source relations if capacity remains. Each record identifies the original and challenging models, the additional local model, its source-specific reasoning, and any verified quotation. A targeted recheck is an **additional opinion**, not proof of consensus; original disagreements remain visible. At most two calls are added per claim and there are no extra calls by default.


Open **KI-Plenum** under **Belege zur Aussage** to read each model’s independent summary and see which model checked each finding. A peer review shows the original source judgment, the reviewer’s outcome and reasoning, and any verified review quote that matches the finding’s source and captured version. Open the quote through **Beleg öffnen** when the source has a URL. The panel lists unresolved objections and recorded failures. Reports created before analysis and review records were included can still be opened.

The [feature gallery](#feature-gallery) includes a walkthrough of the independent findings and peer review. The workflow also checks this panel at mobile width.

## Private editorial review

Open a report containing interests or editorial results to see **Private Redaktionsprüfung**. For each investigated source, the panel shows documented ownership, funding and affiliations, verified evidence passages and unresolved categories. Each editorial claim shows earlier dissent, the assigned findings and the individual reviewers’ outcomes.

Expand **Belege zum Befund** to read the exact excerpts assigned to a finding and open the source at the cited passage. The panel flags any assigned excerpt that cannot be matched to the finding’s source and snapshot version.

For a completed local analysis, **Entwurf speichern** keeps the text with that saved run. Reopen the run from **Gespeicherte Analysen** to resume editing. Review the sources and documented relationships, account for unresolved findings and missing evidence, then confirm both checklist items and choose **Freigabe erteilen**. Approval applies to the saved text and the exact SHA-256 digest of the report, including its citations and unresolved findings. Saving an edit clears approval. A new run or a changed report requires a fresh review.

Open **Leservorschau öffnen** to inspect the approved text, the original article link when available, and the approval date and report digest under **Freigabedaten**. **HTML herunterladen** saves that same reader view as a self-contained page. It can be opened offline. The local interface checks that the approval is current when it opens the preview and when it exports the page.

**Freigegebenen Text exportieren** downloads the human-written text, approval time, article link, and report digest. The assessment and interests data remain in the private run. With a manually imported report, **Freigabeentwurf speichern** continues to download a JSON draft after the checklist. Reports without a final assessment covering its assigned findings remain available for inspection. The interface keeps editorial material local, and publishing the exported text is a separate editorial action.

## Usability checks

Give unfamiliar readers the Tankrabatt case and ask them to find the passage that qualifies the claim of complete pass-through, identify whether the TU announcement and the Freitas–Syga study are independent, and explain the difference between publication and update dates. Observe where they click and ask them to explain each relationship in their own words. Repeat the first two tasks on a small mobile viewport and using only the keyboard.

For a local run, check both citation coverage and whether each citation supports its claim.

## Topic trends and events

Open **Thementrends und Ereignisse** above the article review. When using the local browser server, enter a search phrase and choose 30 or 90 days of German-language or all-language news coverage. Quellenlot requests the daily share of articles monitored by GDELT that match the phrase and links to the corresponding query. The search term and filters are sent to GDELT when you click **GDELT abfragen**. Article URLs, report contents, and event annotations stay out of this request.

Import a single-series **Interesse im zeitlichen Verlauf** CSV exported by Google Trends for search interest, including older periods. English and German daily, weekly, and monthly exports are accepted. Data remain in the browser tab. The search index and GDELT share retain separate scales. The charts leave gaps for unavailable values and dates.

After loading daily data in the local GUI, select **Medienausschlag untersuchen** or **Suchausschlag untersuchen**. Quellenlot ranks peaks from the last 90 UTC days by their rise above the mean of both neighboring days. A peak must exceed both neighbors and reach at least 125% of their mean. Weekly and monthly exports remain available for viewing and manual annotation.

When you start a search, Quellenlot sends the topic, language and a window of up to two days on either side of the strongest eligible peak to GDELT. For a CSV, set the topic and language in the news form first. Up to five results display the date GDELT indexed each article. Choose **Beleg übernehmen** to copy the article title and link into the event form, then check the source and enter the actual event date before saving. Temporal proximity alone does not establish causation. The [feature gallery](#feature-gallery) shows suggestions and event annotations on desktop and mobile.

Add an event with its documented date, title, and evidence URL. Publication dates from the open report appear as **Veröffentlichung**. Select a date in the list to highlight it on each applicable chart. Events and imported series stay in the current browser tab until reload.

- [GDELT DOC 2.0 timeline documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
- [Export Google Trends data](https://support.google.com/trends/answer/4365538?hl=de)
