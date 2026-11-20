# Quellenlot GUI prototype

Open `web/index.html` in a modern browser. The prototype uses local HTML, CSS and JavaScript with no build step. The Tankrabatt case opens by default. Its input article and summary are written for the demo. Its evidence passages and external links come from published sources.

## Screenshots and walkthrough

![Desktop view showing the Tankrabatt summary and the selected claim's evidence and citation path](../docs/images/generated/desktop.png)

<details>
<summary>Mobile view</summary>

<img src="../docs/images/generated/mobile.png" alt="Mobile Quellenlot layout with the URL form, Tankrabatt summary, claims and evidence stacked vertically" width="350">

</details>

### Follow an article claim to its source

1. Open the Tankrabatt example and select **in allen drei Monaten gleich stark gewirkt**.
2. Choose **TU Dresden** to read the passage that disputes the claim. Open **Datum und Version** to inspect when the report was published and updated.
3. In **Herkunft & Belege**, follow **verweist auf** to **Freitas & Syga**. The evidence panel switches to the study and provides a link to the quoted passage.

![Animated walkthrough from the highlighted Tankrabatt claim to the TU Dresden passage and its cited Freitas–Syga study](../docs/images/generated/usage.gif)

## How the previews are generated

The [GUI previews workflow](../.github/workflows/gui-previews.yml) runs the built-in demo in headless Chromium. It checks claim selection, source links, document dates, mobile focus and the imported claim diff before uploading the screenshots and GIF. The [capture manifest](../docs/images/generated/manifest.json) records the tested source revision, output dimensions, and SHA-256 hashes.

Pull requests that change the prototype or its capture workflow get a **quellenlot-gui-previews** artifact under the Actions run. The workflow refreshes the repository images after a successful capture on `main` when the media bytes change. The same workflow can be run manually for `main`.

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
2. Read an attributed summary, then select a highlighted phrase or a claim in the list. The selected claim drives the article excerpt, source list and graph. The graph uses a fixed hierarchy so the reader can follow the path without dragging or zooming.
3. Inspect the exact passage, the type of evidence relationship and the document dates. Publication, modification and capture are separate. A web page may have changed since capture. Evidence without a verified excerpt stays visibly marked.
4. If a source states where its finding comes from, show that citation. In the demo, the TU Dresden announcement points to the same Freitas–Syga study shown in the graph. An inferred historical origin or a duplicate-detection result needs separate treatment.

The prototype follows one review at a time. A conversational thread would make it easier to ask follow-ups and harder to locate the active claim and evidence. A graph-led page would make dependencies prominent while the reader is still trying to understand the article. The side-by-side reading view keeps the claim and evidence in scope. On narrow screens, activating a claim moves focus to its evidence heading.

## Using the local agent

Save the form as `case.json`, then run the existing CLI from an environment with the configured Ollama models:

```sh
quellenlot-agents --config models.toml --input case.json --output report.json
```

Open `report.json` with **Bericht öffnen**. Both article report shapes are supported, including partial runs, failed URL retrieval and runs with no extractable claims. When the report includes a model-written summary, select a sentence to open its claim and article quote. Older reports still open with their extracted claims and source judgments.

**Quellenvergleich** orders the selected claim's sources by publication day and displays update dates alongside them. Sources with unknown publication dates appear last. Select a source to read each model's reasoning and inspect the capture time and snapshot version. **Nicht behandelt** means a model found no coverage in the supplied text. **Nicht beurteilbar** also covers omissions that could not be assessed from an incomplete excerpt.

Repeated verified quotations link to one excerpt with a link for each source. **Mögliche Textübernahme** shows RapidFuzz matches linked to the selected claim's citations. Expand a match to see the original passages and highlighted wording changes. A match can reflect common wording or a common upstream source. Publication and update dates establish the visible chronology of the sources. The exact origin of the wording requires separate evidence.

## Usability test before backend integration

Give unfamiliar readers the Tankrabatt case and ask them to find the passage that qualifies the claim of complete pass-through, identify whether the TU announcement and the Freitas–Syga study are independent, and explain the difference between publication and update dates. Observe where they click and ask them to explain each relationship in their own words. Repeat the first two tasks on a small mobile viewport and using only the keyboard.

The next integration slice is one local run from the composer to this view using the ready-made CLI contract, with durable case and snapshot IDs and explicit run states for capture, partial results and failure. Evaluate citation coverage and whether each citation supports its claim separately.
