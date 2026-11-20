# Quellenlot browser interface

Open `web/index.html` in a modern browser for the static demo or to import a report. The Tankrabatt case opens by default. Its input article and summary are written for the demo. Its evidence passages and external links come from published sources. Start the [local browser server](#using-the-local-agent) to run and save analyses, search for papers, fetch GDELT news trends, and approve editorial drafts. Both modes use local HTML, CSS and JavaScript with no build step.

Quellenlot opens in dark mode. Use **Dunkles Design** in the header to switch between dark and light. The browser remembers your selection when local storage is available. Headings and evidence quotations use IBM Plex Mono, bundled under its [Open Font License](fonts/IBM-Plex-Mono-OFL.txt).

## Screenshots and walkthrough

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

## Party programmes and parliamentary records

Choose **Programme & Abstimmungen** from the header. In the first case, compare the CDU/CSU and SPD programme excerpts on the debt rule and optionally answer the policy statement yourself. The comparison distinguishes a clear programme position from an open interpretation. Your answer stays in the open page.

Follow the timeline to compare the FDP amendment with the subsequent final vote. Each roll call links its parliamentary text, official voting record, and the available debate context. The tables include the total and the selected caucuses, with non-votes shown separately from abstentions. The last records link the constitutional amendment's publication and the later law establishing the infrastructure fund.

Cases are curated in [parliament-data.js](parliament-data.js). To add a case, supply exact programme and motion excerpts, document locators, dated records, verified vote totals, and later actions with primary-source links. Keep editorial interpretations explicit about whether a programme addresses the precise policy in the statement. The interface supports multiple cases through a case picker.

## How the previews are generated

The [GUI previews workflow](../.github/workflows/gui-previews.yml) runs the built-in demo in headless Chromium. It checks the claim selection, excerpt, source graph, document dates, mobile focus behavior, theme switching, offline font loading and the imported claim diff before uploading the dark-mode screenshots and the 20 fps walkthrough GIF. The walkthrough holds the evidence on screen and animates scrolling and node dragging. It also imports a single report containing the claim diff, an upstream citation shared by two sources, and an unresolved private editorial review at desktop and mobile widths. The [capture manifest](../docs/images/generated/manifest.json) records the tested source revision, output dimensions, and SHA-256 hashes.

Pull requests that change the browser interface or its capture workflow get a **quellenlot-gui-previews** artifact under the Actions run. The workflow refreshes the tracked images after a successful capture on `main` when their bytes change. It can also be run manually for `main`. The tracked images include the [parliamentary comparison](../docs/images/generated/parliament.png) and desktop and mobile claim study previews. The artifact also includes fixture screenshots of the private editorial review, the reader preview and the trend charts.

To generate the files locally from the repository root, install Node.js and FFmpeg (including `ffprobe`), then run:

```sh
npm ci --prefix tools/ci/gui-preview --ignore-scripts
tools/ci/gui-preview/node_modules/.bin/playwright install chromium
node tools/ci/gui-preview/capture.cjs
```

The output is written to `artifacts/gui-preview/`. The walkthrough uses the built-in fixture and runs without Ollama.

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

## Studies for a claim

![Saved claim study results showing full-text and metadata-only access, the observation period, and its source excerpt](../docs/images/generated/studies.png)

[Mobile preview](../docs/images/generated/studies-mobile.png)

Open a saved local run, select a claim, and click **Studien suchen**. Quellenlot sends the selected claim and an English query generated locally to [Crossref](https://www.crossref.org/documentation/retrieve-metadata/rest-api/), then checks candidate DOIs for abstracts and open full text in [Europe PMC](https://dev.europepmc.org/RestfulWebService). The article, question, and editorial notes are not part of the search request.

Results distinguish metadata-only candidates, a retrieved abstract, and a retrieved full text. If the text exceeds the model input limit, the interface marks that excerpts were assessed. The study publication year and observation period are displayed separately. The local model describes the measure, population and place, observation period, finding, and its relationship to the claim. Fields need a matching quotation to appear. An exact quotation confirms that the words occur in the source. The interpretation still needs reading in context.

The search checks up to five distinct candidate DOIs. The first configured Ollama model extracts source-backed details. A second configured model independently checks any directional conclusion against the retrieved text. Quellenlot shows the rationale only when the second model agrees with the relation and confirms the interpretation. Otherwise the card shows an unclear relation alongside the extracted material. Older results keep their excerpts and need a fresh search for a reviewed relation.

Results are saved with the run for that claim, separately from the private editorial report. Start the search again to refresh the results. Publisher paywalls and PDFs outside the supported repository can leave a paper at abstract or metadata access.

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

Add an event with its documented date, title, and evidence URL. Publication dates from the open report appear as **Veröffentlichung**. Select a date in the list to highlight it on each applicable chart. Events and imported series stay in the current browser tab until reload.

- [GDELT DOC 2.0 timeline documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
- [Export Google Trends data](https://support.google.com/trends/answer/4365538?hl=de)
