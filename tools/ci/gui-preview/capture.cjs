"use strict";

const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { createHash } = require("node:crypto");
const { mkdir, mkdtemp, readFile, rm, writeFile } = require("node:fs/promises");
const { tmpdir } = require("node:os");
const { join, resolve } = require("node:path");
const { pathToFileURL } = require("node:url");
const { chromium } = require("playwright");

const repo = resolve(__dirname, "../../..");
const output = resolve(process.argv[2] || join(repo, "artifacts/gui-preview"));
const entry = pathToFileURL(join(repo, "web/index.html")).href;
const screenshotOptions = { animations: "disabled", caret: "hide" };
const commands = { ffmpeg: process.env.FFMPEG || "ffmpeg", ffprobe: process.env.FFPROBE || "ffprobe" };

async function openDemo(browser, viewport) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1, reducedMotion: "reduce" });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route(/^https?:/, (route) => route.abort());
  await page.goto(entry);
  await page.getByRole("heading", { name: "Kam der Tankrabatt an?" }).waitFor();
  const plexLoaded = await page.evaluate(async () => {
    const faces = await Promise.all([
      document.fonts.load('400 16px "IBM Plex Mono"'),
      document.fonts.load('600 16px "IBM Plex Mono"'),
    ]);
    await document.fonts.ready;
    return faces.every((weight) => weight.some((face) => face.status === "loaded"));
  });
  assert.ok(plexLoaded, "Both IBM Plex Mono weights load offline");
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), viewport.width);
  return { page, errors };
}

async function captureOverview(browser, width, height, name) {
  const { page, errors } = await openDemo(browser, { width, height });
  try {
    await page.screenshot({ ...screenshotOptions, fullPage: true, path: join(output, name) });
    if (width < 600) {
      await page.getByRole("link", { name: "in allen drei Monaten gleich stark gewirkt" }).click();
      assert.equal(await page.locator(":focus").getAttribute("id"), "evidence-heading");
      await page.getByRole("button", { name: "Zur ausgewählten Aussage" }).click();
      assert.equal(await page.locator(":focus").getAttribute("data-claim"), "1");
    }
    assert.deepEqual(errors, []);
  } finally {
    await page.close();
  }
}

async function captureWalkthrough(browser, frames) {
  const { page, errors } = await openDemo(browser, { width: 1120, height: 780 });
  const highlight = page.getByRole("link", { name: "in allen drei Monaten gleich stark gewirkt" });
  const evidence = page.locator("#source-detail");
  const graph = page.locator("#graph");
  let frame = 0;

  async function shot(anchor) {
    await page.locator(anchor).evaluate((node) => node.scrollIntoView({ block: "start" }));
    frame += 1;
    await page.screenshot({ ...screenshotOptions, path: join(frames, `frame-${frame}.png`) });
  }

  try {
    await shot("#review");

    await highlight.focus();
    await page.keyboard.press("Enter");
    assert.equal(await highlight.getAttribute("aria-current"), "true");
    assert.equal(await evidence.locator(".relation").textContent(), "Widerspricht");
    await shot("#workspace");

    await page.locator("#diff-sources").getByRole("button", { name: "TU Dresden" }).click();
    assert.match(await evidence.locator("blockquote").textContent(), /Anfang Juni/);
    await evidence.getByText("Datum und Version", { exact: true }).click();
    assert.match(await evidence.locator("dl").textContent(), /19\.10\.2022.*20\.10\.2022/);
    await graph.getByText("verweist auf", { exact: true }).waitFor();
    await shot("#source-detail");

    await graph.locator(".graph-origin").getByRole("button", { name: "Freitas & Syga" }).click();
    assert.match(await evidence.locator(".source-type").textContent(), /ifo Dresden berichtet/);
    assert.match(await evidence.getByRole("link", { name: "Originalquelle öffnen" }).getAttribute("href"), /#:~:text=/);
    await shot("#graph-heading");
    assert.deepEqual(errors, []);
    return frame;
  } finally {
    await page.close();
  }
}

async function checkImportOutcomes(browser) {
  const { page, errors } = await openDemo(browser, { width: 1280, height: 960 });
  const report = {
    case_id: "tankrabatt-import-test",
    question: null,
    article_source_id: "article",
    sources: [{ source_id: "article", title: "Artikel mit offenem Ergebnis" }],
    extraction_attempts: [],
    claims: [],
  };

  async function importReport(data) {
    await page.locator("#report-file").setInputFiles({
      name: "report.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(data)),
    });
  }

  try {
    await importReport({ ...report, status: "no_claims" });
    await page.getByText("Der Bericht enthält keine prüfbaren Aussagen.", { exact: true }).waitFor();

    const status = "failed";
    await importReport({ status, retrievals: [], review: { ...report, status } });
    await page.getByText("Importierter Bericht · Analyse fehlgeschlagen", { exact: true }).waitFor();
    assert.match(await page.locator("#empty-report").textContent(), /Extraktion fehlgeschlagen/);
    const article = {
      source_id: "article",
      title: "Bibliothek",
      version_id: "v1",
      url: "https://example.org/bibliothek",
    };
    const quote = "Der Eintritt ist frei.";
    const claim = {
      claim_id: "claim-1",
      article_quote: { source_id: "article", version_id: "v1", verified: true, text: quote },
      review: { claim: quote, status: "complete" },
      source_comparison: [],
    };
    const text = "Dem Bericht zufolge kostet der Eintritt nichts.";
    const articleReport = { ...report, status: "complete", sources: [article], claims: [claim] };
    await importReport({
      ...articleReport,
      article_summary: [{ text, claim_id: claim.claim_id }],
    });
    await page.getByRole("link", { name: text }).click();
    assert.equal(await page.locator("#original-quote").textContent(), quote);
    assert.ok(await page.locator("#original-quote").isVisible());
    assert.match(await page.locator("#original-link a").getAttribute("href"), /#:~:text=/);

    await importReport({
      ...articleReport,
      article_summary: [{ text, claim_id: "claim-missing" }],
    });
    await page.getByText("Dieser Agentenbericht enthält keine ausformulierte Artikelzusammenfassung.", { exact: true }).waitFor();
    assert.equal(await page.getByRole("link", { name: text }).count(), 0);

    const finding = { finding_id: "claim-1-finding-1", source_id: "comparison", relation: "qualifies" };
    const coverage = {
      claim_id: "claim-1",
      assigned_findings: [finding],
      unresolved_dissent: ["Die Vergleichsquelle nennt einen anderen Zeitraum."],
      unresolved_finding_ids: [finding.finding_id],
    };
    const note = {
      claim_id: "claim-1",
      assessment: "Die Aussage ist weiter zu prüfen.",
      findings: [{ finding_id: finding.finding_id, outcome: "challenges", reasoning: "Zeitraum unklar." }],
    };
    const evidence = {
      source_id: "interest-evidence",
      version_id: "interest-v1",
      url: "https://example.org/finanzierung",
    };
    const withReview = {
      ...articleReport,
      interests: {
        sources: [{
          source: article,
          evidence_sources: [evidence],
          unresolved_categories: ["ownership"],
          assessments: [{
            agent_id: "model-1",
            findings: [{
              category: "funding",
              relationship: "Die Stadt finanziert die Bibliothek.",
              evidence: { ...evidence, verified: true, text: "Die Stadt übernimmt die Kosten." },
            }],
          }],
        }],
      },
      editorial: {
        status: "partial",
        claims: [coverage],
        assessments: [{ agent_id: "model-1", status: "succeeded", claims: [note] }],
      },
    };
    await importReport(withReview);
    const panel = page.locator("#private-review");
    await panel.waitFor();
    await panel.getByText("Eigentümerschaft, Finanzierung und Verbindungen", { exact: true }).click();
    await panel.getByText("Offen: Eigentümerschaft", { exact: true }).waitFor();
    assert.match(await panel.getByRole("link", { name: "Beleg der Verbindung öffnen" }).getAttribute("href"), /finanzierung/);
    await panel.getByText(quote, { exact: true }).click();
    await panel.getByText("Die Vergleichsquelle nennt einen anderen Zeitraum.", { exact: true }).waitFor();
    await panel.getByText("In der Schlussprüfung umstritten oder unklar.", { exact: true }).waitFor();
    const save = panel.getByRole("button", { name: "Freigabeentwurf speichern" });
    assert.ok(await save.isDisabled());
    await panel.getByLabel("Redaktioneller Text für die Veröffentlichung").fill("Die Aussage bleibt offen.");
    for (const checkbox of await panel.getByRole("checkbox").all()) await checkbox.check();
    assert.ok(await save.isEnabled());
    const [download] = await Promise.all([page.waitForEvent("download"), save.click()]);
    const draft = JSON.parse(await readFile(await download.path(), "utf8"));
    assert.equal(draft.text, "Die Aussage bleibt offen.");
    assert.match(draft.review_sha256, /^[a-f0-9]{64}$/);
    assert.equal(draft.interests, undefined);
    assert.equal(draft.editorial, undefined);
    await importReport({
      ...withReview,
      editorial: {
        ...withReview.editorial,
        assessments: [{
          agent_id: "model-1",
          status: "succeeded",
          claims: [{ ...note, findings: [note.findings[0], note.findings[0]] }],
        }],
      },
    });
    await panel.locator("#release-form").waitFor({ state: "hidden" });
    assert.deepEqual(errors, []);
  } finally {
    await page.close();
  }
}

async function checkTheme(browser) {
  const width = 320;
  const { page, errors } = await openDemo(browser, { width, height: 800 });
  const toggle = page.getByRole("button", { name: "Dunkles Design" });
  const scheme = () => page.locator("html").evaluate((root) => getComputedStyle(root).colorScheme);

  try {
    assert.equal(await scheme(), "dark");
    assert.equal(await toggle.getAttribute("aria-pressed"), "true");

    await toggle.focus();
    await page.keyboard.press("Space");
    assert.equal(await scheme(), "light");
    assert.equal(await toggle.getAttribute("aria-pressed"), "false");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width);

    await page.reload();
    await toggle.waitFor();
    assert.equal(await scheme(), "light");
    assert.equal(await toggle.getAttribute("aria-pressed"), "false");

    await toggle.click();
    assert.equal(await scheme(), "dark");
    assert.deepEqual(errors, []);
  } finally {
    await page.close();
  }
}

async function checkClaimDiff(browser) {
  const release = "Nach sechs Monaten empfängt die Bibliothek wieder alle Besucherinnen und Besucher aus dem Landkreis zu den üblichen Zeiten.";
  const revised = release.replace("üblichen", "verkürzten");
  const observed = "Am ersten Tag warteten Besucher vor dem Gebäude.";
  const snapshot = (source_id, title, published, updated, text_is_complete = true) => ({
    source_id, title, version_id: "v1", url: `https://example.org/${source_id}`, text_is_complete,
    published_at: published ? { value: published } : null,
    updated_at: updated ? { value: updated } : null,
    captured_at: "2025-02-03T14:00:00Z",
  });
  const original = snapshot("article", "Bibliothek aktuell", "2025-02-02", "2025-02-03");
  const releaseSource = snapshot("release", "Stadtmitteilung", "2025-02-01");
  const news = snapshot("news", "Lokalzeitung", "2025-02-03");
  const omitted = snapshot("newsletter", "Stadtteilbrief", "2025-02-02");
  const partial = snapshot("excerpt", "Unvollständiger Archivtext", null, "2025-02-01", false);
  const unreviewed = snapshot("archive", "Archiv", null);
  const sources = [original, releaseSource, news, omitted, partial, unreviewed];
  const citation = (source, ...shared_wording_match_indexes) => ({
    source_id: source.source_id, version_id: source.version_id, locators: ["Absatz 2"], shared_wording_match_indexes,
  });
  const passage = (source, text) => ({ ...citation(source), text });
  const judgment = (agent_id, relation, ...evidence_ids) => ({
    agent_id, relation, reasoning: "Begründung von " + agent_id, evidence_ids,
  });
  const first = {
    claim_id: "claim-1",
    article_quote: { ...passage(original, release), verified: true },
    review: {
      claim: "Die Bibliothek hat wieder regulär geöffnet.", status: "complete",
      source_diff: {
        sources: [
          { source: original, judgments: [judgment("eins", "supports", "common")] },
          { source: releaseSource, judgments: [judgment("eins", "supports", "common")] },
          { source: news, judgments: [judgment("eins", "qualifies", "revised", "observed"), judgment("zwei", "contradicts", "revised")] },
          { source: omitted, judgments: [judgment("eins", "omits")] },
          { source: partial, judgments: [judgment("eins", "not_assessable")] },
          { source: unreviewed, judgments: [] },
        ],
        evidence: [
          { evidence_id: "common", kind: "shared_wording", text: release, citations: [citation(original, 0), citation(releaseSource, 0)] },
          { evidence_id: "revised", kind: "source_specific", text: revised, citations: [citation(news, 1)] },
          { evidence_id: "observed", kind: "source_specific", text: observed, citations: [citation(news)] },
        ],
      },
    },
    source_comparison: [],
  };
  const legacyQuote = "Der Eintritt ist frei.";
  const legacy = {
    claim_id: "claim-2",
    review: { claim: legacyQuote, status: "complete" },
    source_comparison: [{
      source: releaseSource,
      judgments: [{ relation: "supports", citations: [{ ...passage(releaseSource, legacyQuote), verified: true }] }],
    }],
  };
  const report = {
    status: "complete", article_source_id: "article", sources, claims: [first, legacy],
    shared_wording: {
      limited: true,
      matches: [
        { first: passage(original, release), second: passage(releaseSource, release), similarity: 100 },
        { first: passage(news, revised), second: passage(releaseSource, release), similarity: 94.44 },
        { first: passage(omitted, "Passage ohne Bezug"), second: passage(news, "Passage ohne Bezug"), similarity: 100 },
      ],
    },
  };
  for (const width of [1280, 390]) {
    const { page, errors } = await openDemo(browser, { width, height: 900 });
    try {
      await page.locator("#report-file").setInputFiles({
        name: "claim-diff.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(report)),
      });
      const rows = page.locator("#diff-sources > li");
      const names = rows.locator("button");
      await names.first().waitFor();
      assert.deepEqual(await names.allTextContents(), ["Stadtmitteilung", "Bibliothek aktuell", "Stadtteilbrief", "Lokalzeitung", "Unvollständiger Archivtext", "Archiv"]);
      assert.match(await rows.nth(1).textContent(), /Veröffentlicht 02\.02\.2025Aktualisiert 03\.02\.2025/);
      assert.match(await rows.nth(2).textContent(), /Nicht behandelt/);
      assert.match(await rows.nth(4).textContent(), /Veröffentlichung unbekannt.*Nicht beurteilbar.*Nur Auszug/);
      assert.match(await rows.nth(5).textContent(), /Keine Modellbeurteilung/);
      await rows.nth(3).getByRole("button", { name: "Lokalzeitung" }).click();
      const detail = page.locator("#source-detail");
      assert.deepEqual(await detail.locator(".relation").allTextContents(), ["Schränkt ein", "Widerspricht"]);
      assert.deepEqual(await detail.locator(".judgment .source-reason").allTextContents(), ["Begründung von eins", "Begründung von zwei"]);
      await detail.getByRole("link", { name: "Zitat 3" }).focus();
      await page.keyboard.press("Enter");
      assert.equal(await page.locator(":focus blockquote").textContent(), observed);
      const sharedQuote = page.locator("#claim-quote-1");
      assert.deepEqual(await sharedQuote.getByRole("link").allTextContents(), ["Bibliothek aktuell", "Stadtmitteilung"]);
      assert.equal(await sharedQuote.locator("blockquote").textContent(), release);
      const matches = page.locator(".diff-match");
      assert.equal(await matches.count(), 2);
      await matches.nth(0).locator("summary").click();
      assert.equal(await matches.nth(0).locator("blockquote").count(), 0);
      assert.equal(await matches.nth(0).getByRole("link", { name: "Zitat 1" }).count(), 1);
      await matches.nth(1).locator("summary").click();
      assert.deepEqual(await matches.nth(1).locator("blockquote").allTextContents(), [release, revised]);
      assert.equal(await matches.nth(1).locator("del").textContent(), "üblichen");
      assert.equal(await matches.nth(1).locator("ins").textContent(), "verkürzten");
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width);
      await page.locator("#claim-list button").nth(1).click();
      assert.equal(await matches.count(), 0);
      assert.equal(await detail.locator("blockquote").textContent(), `„${legacyQuote}“`);
      assert.deepEqual(errors, []);
    } finally {
      await page.close();
    }
  }
}

function encodeGif(frames) {
  execFileSync(commands.ffmpeg, [
    "-hide_banner", "-loglevel", "error", "-y", "-filter_complex_threads", "1",
    "-framerate", "1/2", "-i", join(frames, "frame-%d.png"),
    "-filter_complex", "scale=960:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse",
    "-loop", "0", join(output, "usage.gif"),
  ]);
}

async function inspectMedia(name, expectedWidth, expectedFrames = 1) {
  const path = join(output, name);
  const probe = execFileSync(commands.ffprobe, [
    "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
    "stream=width,height,nb_read_frames:format=duration", "-of", "json", path,
  ], { encoding: "utf8" });
  const { streams: [stream], format } = JSON.parse(probe);
  assert.equal(stream.width, expectedWidth, name);
  assert.equal(Number(stream.nb_read_frames), expectedFrames, name);
  assert.ok(stream.height >= 500, name);
  if (name.endsWith(".gif")) {
    assert.ok(Number(format.duration) >= expectedFrames * 2 - 0.1, "GIF holds each step for two seconds");
  }
  const bytes = await readFile(path);
  assert.ok(bytes.length > 10_000 && bytes.length < 2_000_000, name);
  return {
    file: name,
    width: stream.width,
    height: stream.height,
    frames: expectedFrames,
    bytes: bytes.length,
    sha256: createHash("sha256").update(bytes).digest("hex"),
  };
}

async function main() {
  await mkdir(output, { recursive: true });
  const frames = await mkdtemp(join(tmpdir(), "quellenlot-preview-"));
  try {
    const browser = await chromium.launch();
    let count;
    try {
      await captureOverview(browser, 1280, 960, "desktop.png");
      await captureOverview(browser, 390, 844, "mobile.png");
      count = await captureWalkthrough(browser, frames);
      await checkImportOutcomes(browser);
      await checkTheme(browser);
      await checkClaimDiff(browser);
    } finally {
      await browser.close();
    }
    encodeGif(frames);
    const media = await Promise.all([
      inspectMedia("desktop.png", 1280),
      inspectMedia("mobile.png", 390),
      inspectMedia("usage.gif", 960, count),
    ]);
    const { GITHUB_SHA, GITHUB_SERVER_URL, GITHUB_REPOSITORY, GITHUB_RUN_ID } = process.env;
    const manifest = {
      source_commit: GITHUB_SHA || null,
      workflow_run: GITHUB_RUN_ID ? `${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}` : null,
      scenario: "Tankrabatt fixture, article claim investigation",
      playwright: require("playwright/package.json").version,
      media,
    };
    await writeFile(join(output, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
    console.log(JSON.stringify(manifest, null, 2));
  } finally {
    await rm(frames, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
