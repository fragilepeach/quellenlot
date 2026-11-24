"use strict";

const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { createHash } = require("node:crypto");
const { link, mkdir, mkdtemp, readFile, rm, writeFile } = require("node:fs/promises");
const { tmpdir } = require("node:os");
const { join, resolve } = require("node:path");
const { pathToFileURL } = require("node:url");
const { chromium } = require("playwright");

const repo = resolve(__dirname, "../../..");
const output = resolve(process.argv[2] || join(repo, "artifacts/gui-preview"));
const entry = pathToFileURL(join(repo, "web/index.html")).href;
const gallery = require("./gallery.json");
const gifFps = 25;
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

async function captureOverview(browser, width, height, name, record) {
  const { page, errors } = await openDemo(browser, { width, height });
  try {
    await page.screenshot({ ...screenshotOptions, fullPage: true, path: join(output, name) });
    if (width < 600) {
      const clip = await record.open("mobile-workflow.gif", page);
      await clip.scrollTo("#review", 1);
      await clip.hold();
      await page.getByRole("link", { name: "in allen drei Monaten gleich stark gewirkt" }).click();
      assert.equal(await page.locator(":focus").getAttribute("id"), "evidence-heading");
      await clip.hold(1.4);
      await page.getByRole("button", { name: "Zur ausgewählten Aussage" }).click();
      assert.equal(await page.locator(":focus").getAttribute("data-claim"), "1");
      await clip.hold(1);
      await clip.scrollTo("#main");
      const theme = page.getByRole("button", { name: "Dunkles Design" });
      await theme.click();
      assert.equal(await theme.getAttribute("aria-pressed"), "false");
      await page.locator("#urls").fill("https://example.org/artikel");
      await clip.hold();
      const [download] = await Promise.all([
        page.waitForEvent("download"),
        page.getByRole("button", { name: "Anfrage speichern" }).click(),
      ]);
      assert.equal(download.suggestedFilename(), "case.json");
      assert.equal(JSON.parse(await readFile(await download.path(), "utf8")).article_url,
        "https://example.org/artikel");
      await page.getByText(/case.json gespeichert/).waitFor();
      await clip.hold(1.6);
    }
    assert.deepEqual(errors, []);
  } finally {
    await page.close();
  }
}

function createRecorder(root) {
  const recordings = new Map();
  return {
    async open(name, page) {
      assert.ok(!recordings.has(name), name + " was captured twice");
      const directory = join(root, name);
      await mkdir(directory);
      const recording = { directory, frame: 0 };
      recordings.set(name, recording);
      const framePath = (index) => join(directory, `frame-${index}.png`);
      async function shot() {
        await page.screenshot({ ...screenshotOptions, path: framePath(++recording.frame) });
      }
      return {
        shot,
        async hold(seconds = 1.25) {
          await shot();
          const still = framePath(recording.frame);
          for (let count = Math.round(seconds * gifFps) - 1; count > 0; count -= 1) {
            await link(still, framePath(++recording.frame));
          }
        },
        async scrollTo(anchor, steps = 12) {
          const target = typeof anchor === "string" ? page.locator(anchor) : anchor;
          const { start, finish } = await target.evaluate((node) => ({
            start: window.scrollY,
            finish: Math.min(window.scrollY + node.getBoundingClientRect().top,
              document.documentElement.scrollHeight - window.innerHeight),
          }));
          for (let step = 1; step <= steps; step += 1) {
            const progress = (1 - Math.cos(Math.PI * step / steps)) / 2;
            await page.evaluate((top) => window.scrollTo(0, top), Math.round(start + progress * (finish - start)));
            if (steps > 1 && start !== finish) await shot();
          }
        },
      };
    },
    get(name) {
      const recording = recordings.get(name);
      assert.ok(recording?.frame >= gifFps, name + " has no complete recording");
      return recording;
    },
  };
}

async function captureSection(page, target, name) {
  await target.evaluate((node) => node.scrollIntoView({ block: "start", behavior: "instant" }));
  await page.screenshot({ ...screenshotOptions, path: join(output, name) });
}

async function captureWalkthrough(browser, record) {
  const { page, errors } = await openDemo(browser, { width: 1120, height: 780 });
  const highlight = page.getByRole("link", { name: "in allen drei Monaten gleich stark gewirkt" });
  const evidence = page.locator("#source-detail");
  const graph = page.locator("#graph");
  const { hold, scrollTo, shot } = await record.open("usage.gif", page);

  try {
    await scrollTo("#review", 1);
    await hold(1.6);

    await highlight.focus();
    await page.keyboard.press("Enter");
    assert.equal(await highlight.getAttribute("aria-current"), "true");
    assert.equal(await evidence.locator(".relation").textContent(), "Widerspricht");
    await hold(1.55);

    await page.locator("#diff-sources").getByRole("button", { name: "TU Dresden" }).click();
    assert.match(await evidence.locator("blockquote").textContent(), /Anfang Juni/);
    await evidence.getByText("Datum und Version", { exact: true }).click();
    assert.match(await evidence.locator("dl").textContent(), /19\.10\.2022.*20\.10\.2022/);
    await scrollTo("#source-detail", 7);
    await hold(1.7);

    const citation = graph.locator('.graph-connections > [data-kind="citation"]');
    await graph.getByText("→ Verweist auf", { exact: true }).waitFor();
    await scrollTo("#graph-heading", 7);
    await hold(1.2);
    const source = graph.getByRole("button", { name: /TU Dresden/ });
    const oldPath = await citation.getAttribute("d");
    const position = await source.boundingBox();
    const x = position.x + position.width / 2;
    const y = position.y + position.height / 2;
    await page.mouse.move(x, y);
    await page.mouse.down();
    for (let step = 1; step <= 12; step += 1) {
      await page.mouse.move(x + step * 7, y + step * 3);
      await shot();
    }
    await page.mouse.up();
    assert.notEqual(await citation.getAttribute("d"), oldPath);
    assert.equal(await source.getAttribute("aria-pressed"), "true");
    await hold(0.65);

    const study = graph.getByRole("button", { name: /Freitas & Syga/ });
    await study.click();
    assert.equal(await study.getAttribute("aria-pressed"), "true");
    assert.match(await evidence.locator(".source-type").textContent(), /ifo Dresden berichtet/);
    assert.match(await evidence.getByRole("link", { name: "Originalquelle öffnen" }).getAttribute("href"), /#:~:text=/);
    await hold(1.55);
    assert.deepEqual(errors, []);
  } finally {
    await page.close();
  }
}

async function checkImportOutcomes(browser, record) {
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

    await importReport({
      status, review: null,
      retrievals: [{ source_id: "article", status, requested_url: "https://example.org/unavailable" }],
    });
    await page.getByRole("heading", { name: "Artikel konnte nicht gelesen werden" }).waitFor();
    assert.deepEqual(await page.locator("#agent-roles .agent-status").allTextContents(),
      ["Fehlgeschlagen", "Kein Ergebnis", "Kein Ergebnis", "Kein Ergebnis", "Kein Ergebnis"]);
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
    const clip = await record.open("report-import.gif", page);
    const openReport = page.getByRole("button", { name: "Bericht öffnen" });
    await openReport.focus();
    await clip.hold();
    const [chooser] = await Promise.all([page.waitForEvent("filechooser"), openReport.click()]);
    await chooser.setFiles({
      name: "report.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(withReview)),
    });
    const panel = page.locator("#private-review");
    await panel.waitFor();
    await clip.scrollTo("#review", 1);
    await clip.hold();
    await clip.scrollTo(panel);
    await panel.getByText("Eigentümerschaft, Finanzierung und Verbindungen", { exact: true }).click();
    await panel.getByText("Offen: Eigentümerschaft", { exact: true }).waitFor();
    assert.match(await panel.getByRole("link", { name: "Beleg der Verbindung öffnen" }).getAttribute("href"), /finanzierung/);
    await captureSection(page, panel, "source-interests.png");
    await clip.hold();
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
    await clip.hold();
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

    const snapshot = (source_id, title, text) => ({
      source_id, version_id: "v1", title, text, url: "https://example.org/" + source_id,
      captured_at: "2026-11-20T12:00:00Z",
    });
    const provenanceArticle = snapshot("article", "Artikel A", "Erste Studie");
    const comparison = snapshot("comparison", "Artikel B", "Zweite Studie");
    const study = snapshot("study", "Gemeinsame Studie", "Methodik der Studie");
    const retrievals = [provenanceArticle, comparison, study].map((source) => ({
      source_id: source.source_id, status: "captured", snapshot: source,
    }));
    retrievals.push({ source_id: "appendix", requested_url: "https://example.org/appendix", status: "failed", detail: "HTTP 403" });
    const link = (source, cited_source_id, anchor) => ({
      citing_source_id: source.source_id, citing_version_id: source.version_id,
      cited_source_id, link: { anchor },
    });
    await importReport({
      retrievals, status: "partial",
      review: {
        ...report, sources: [provenanceArticle, comparison], claims: [{
          review: { claim: "Die Studie hat ein Ergebnis.", status: "complete" },
          source_comparison: [],
        }],
      },
      provenance: { limited: true, citations: [
        link(provenanceArticle, "study", "Erste Studie"), link(comparison, "study", "Zweite Studie"),
        link(study, "appendix", "Methodik"), link(study, "appendix", "Erfundener Link"),
      ] },
    });
    const graph = page.locator(".source-provenance");
    await graph.locator(":scope > summary").click();
    const sharedNode = page.locator("#graph").getByRole("button", { name: "Gemeinsame Studie", exact: true });
    assert.equal(await sharedNode.count(), 1);
    assert.equal(await page.locator('#graph .graph-connections > [data-kind="citation"]').count(), 3);
    await sharedNode.click();
    assert.equal(await sharedNode.getAttribute("aria-pressed"), "true");
    assert.match(await page.locator("#graph-selection a").getAttribute("href"), /example\.org\/study/);
    await graph.getByText("2 Quellen verlinken dieses Ziel.", { exact: true }).waitFor();
    assert.equal(await graph.getByRole("link", { name: "Gemeinsame Studie", exact: true }).count(), 1);
    assert.equal(await graph.getByText("Nicht abrufbar · HTTP 403").count(), 1);
    assert.equal(await graph.getByText("Erfundener Link", { exact: false }).count(), 0);
    await captureSection(page, page.locator("#graph-heading"), "shared-provenance.png");
    await clip.hold(1.5);
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
    const help = page.getByRole("button", { name: "Hilfe zur Frage" });
    const helpText = page.locator("#question-help");
    await help.hover();
    assert.ok(await helpText.isVisible());
    await help.focus();
    await page.keyboard.press("Enter");
    assert.equal(await help.getAttribute("aria-expanded"), "true");
    await page.keyboard.press("Escape");
    assert.ok(!(await helpText.isVisible()));

    const active = page.locator('#summary-text [aria-current="true"]');
    const inactive = page.locator('#summary-text [aria-current="false"]').first();
    assert.notEqual(await active.evaluate((node) => getComputedStyle(node).color),
      await inactive.evaluate((node) => getComputedStyle(node).color));
    const graph = page.locator("#graph");
    const tu = graph.getByRole("button", { name: /TU Dresden/ });
    const activeStudy = graph.getByRole("button", { name: /Freitas & Syga/ });
    const edge = graph.locator('.graph-connections > [data-kind="citation"]');
    await tu.scrollIntoViewIfNeeded();
    const before = await edge.getAttribute("d");
    const start = await tu.boundingBox();
    await page.mouse.move(start.x + start.width / 2, start.y + start.height / 2);
    await page.mouse.down();
    await page.mouse.move(start.x + start.width / 2 + 25, start.y + start.height / 2 - 25, { steps: 5 });
    await page.mouse.up();
    assert.notEqual(await edge.getAttribute("d"), before);
    assert.equal(await tu.getAttribute("aria-pressed"), "false");
    assert.equal(await activeStudy.getAttribute("aria-pressed"), "true");
    await tu.focus();
    const moved = await edge.getAttribute("d");
    await page.keyboard.press("ArrowDown");
    assert.notEqual(await edge.getAttribute("d"), moved);
    await page.keyboard.press("Enter");
    assert.equal(await tu.getAttribute("aria-pressed"), "true");
    assert.equal(await page.locator("#source-detail h4").textContent(), "Beurteilungen zu TU Dresden");

    await toggle.focus();
    await page.keyboard.press("Space");
    assert.equal(await scheme(), "light");
    assert.equal(await toggle.getAttribute("aria-pressed"), "false");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ ...screenshotOptions, path: join(output, "light-mobile.png") });

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

async function checkClaimDiff(browser, record) {
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
      sources,
      unresolved_dissent: ["Öffnungszeiten bleiben umstritten."],
      analyses: [
        { agent_id: "eins", model: "modell-eins", status: "succeeded", summary: "Die Mitteilung nennt reguläre Zeiten.",
          findings: [{ source_id: news.source_id, version_id: "v1", relation: "qualifies", reasoning: "Die Zeitung nennt kürzere Zeiten." }] },
        { agent_id: "zwei", model: "modell-zwei", status: "succeeded", findings: [
          { source_id: news.source_id, version_id: "v1", relation: "contradicts", reasoning: "Die Zeiten weichen ab." },
        ] },
      ],
      reviews: [
        { reviewer_agent_id: "zwei", reviewed_agent_id: "eins", status: "succeeded", findings: [{
          finding_index: 0, outcome: "challenges", reasoning: "Die Änderung betrifft alle Öffnungstage.",
          quote: { ...passage(news, revised), verified: true },
        }] },
        { reviewer_agent_id: "eins", reviewed_agent_id: "zwei", status: "succeeded", findings: [{
          finding_index: 0, outcome: "unclear", reasoning: "Die Gültigkeit ist offen.",
          quote: { ...passage({ ...news, version_id: "old" }, "Falsche Belegversion"), verified: true },
        }] },
        { reviewer_agent_id: "drei", reviewed_agent_id: "eins", status: "failed", findings: [] },
      ],
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
          { evidence_id: "stale", kind: "source_specific", text: "Eine ältere Darstellung.", citations: [citation({ ...news, version_id: "old" })] },
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
      source_similarities: [
        { first: citation(original), second: citation(omitted), score: 0 },
        { first: citation(original), second: citation(partial), score: null },
        { first: citation(releaseSource), second: citation(news), score: 62.5 },
        { first: citation({ ...original, version_id: "old" }), second: citation(news), score: 90 },
        { first: citation(original), second: citation(releaseSource), score: 100 },
      ],
      matches: [
        { first: passage(original, release), second: passage(releaseSource, release), similarity: 100 },
        { first: passage(news, revised), second: passage(releaseSource, release), similarity: 94.44 },
        { first: passage(omitted, "Passage ohne Bezug"), second: passage(news, "Passage ohne Bezug"), similarity: 100 },
      ],
    },
  };
  const finding = {
    finding_id: "claim-1-finding-1", source_id: news.source_id, relation: "qualifies",
    evidence_ids: ["revised", "common", "stale"],
  };
  report.editorial = {
    status: "partial",
    claims: [{ claim_id: first.claim_id, assigned_findings: [finding], unresolved_finding_ids: [finding.finding_id] }],
    assessments: [{
      agent_id: "eins", status: "succeeded",
      claims: [{
        claim_id: first.claim_id, assessment: "Die Angaben weichen voneinander ab.",
        findings: [{ finding_id: finding.finding_id, outcome: "unclear", reasoning: "Öffnungszeiten unbekannt." }],
      }],
    }],
  };
  const study = snapshot("study", "Offizielle Studie", "2025-01-31");
  const anchor = "Link zur Studie";
  const bundle = {
    status: "partial",
    review: report,
    retrievals: [original, news, study].map((source) => ({
      source_id: source.source_id, status: "captured", snapshot: { ...source, text: anchor },
    })),
    provenance: {
      citations: [original, news].map((source) => ({
        citing_source_id: source.source_id, citing_version_id: source.version_id,
        cited_source_id: study.source_id, link: { anchor },
      })),
    },
  };
  for (const width of [1280, 390, 320]) {
    const { page, errors } = await openDemo(browser, { width, height: 900 });
    try {
      await page.locator("#report-file").setInputFiles({
        name: "claim-diff.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(bundle)),
      });
      const rows = page.locator("#diff-sources > li");
      const names = rows.locator("button");
      await names.first().waitFor();
      const comparison = width === 1280 ? await record.open("claim-diff.gif", page) : null;
      const reviews = width === 1280 ? await record.open("plenum.gif", page) : null;
      await comparison?.scrollTo("#claim-diff", 1);
      await comparison?.hold();
      await reviews?.hold(1);
      await page.locator(".source-provenance > summary").click();
      await page.locator(".source-provenance").getByText("2 Quellen verlinken dieses Ziel.").waitFor();
      const plenum = page.locator("#claim-plenum");
      await plenum.locator("summary").click();
      await plenum.getByText("zwei prüft eins", { exact: true }).waitFor();
      await plenum.getByText("Die Zeitung nennt kürzere Zeiten.", { exact: true }).waitFor();
      await plenum.getByText("Die Änderung betrifft alle Öffnungstage.", { exact: true }).waitFor();
      await plenum.getByText("Öffnungszeiten bleiben umstritten.", { exact: true }).waitFor();
      await plenum.getByText("Gegenprüfung fehlgeschlagen.", { exact: true }).waitFor();
      assert.deepEqual(await plenum.locator("blockquote").allTextContents(), [revised]);
      const reviewLink = new URL(await plenum.getByRole("link", { name: "Beleg öffnen" }).getAttribute("href"));
      assert.equal(reviewLink.origin + reviewLink.pathname, news.url);
      assert.equal(decodeURIComponent(reviewLink.hash), "#:~:text=" + revised);
      if (reviews) {
        await reviews.scrollTo(plenum);
        await captureSection(page, plenum, "plenum.png");
        await reviews.hold(1.6);
        await reviews.scrollTo(plenum.locator("blockquote").first());
        await reviews.hold(1.5);
      }
      await plenum.locator("summary").click();
      const privateReview = page.locator("#private-review");
      await privateReview.getByText(first.review.claim, { exact: true }).click();
      await privateReview.getByText("In der Schlussprüfung umstritten oder unklar.").waitFor();
      const findingEvidence = privateReview.locator(".editorial-evidence");
      await findingEvidence.getByText("Belege zum Befund", { exact: true }).click();
      assert.deepEqual(await findingEvidence.locator("blockquote").allTextContents(), [revised]);
      const articleLink = findingEvidence.getByRole("link", { name: "Lokalzeitung", exact: true });
      const citationUrl = new URL(await articleLink.getAttribute("href"));
      assert.equal(citationUrl.origin + citationUrl.pathname, news.url);
      assert.equal(decodeURIComponent(citationUrl.hash), "#:~:text=" + revised);
      await findingEvidence.getByText("Zugewiesene Belege fehlen für diese Quelle im Bericht.").waitFor();
      assert.ok(await privateReview.locator("#release-form").isVisible());
      assert.ok(await privateReview.getByRole("button", { name: "Freigabeentwurf speichern" }).isDisabled());
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
      if (comparison) {
        await comparison.scrollTo("#diff-wording");
        await captureSection(page, page.locator("#diff-wording"), "claim-diff.png");
        await comparison.hold(1.8);
      }
      const similarity = page.locator("#source-similarity");
      await similarity.locator("summary").click();
      const scoreRows = similarity.locator("tbody tr");
      assert.deepEqual(await scoreRows.locator("td:last-child").allTextContents(),
        ["100 %", "62,5 %", "0 %", "Zu wenig Text"]);
      assert.deepEqual(await scoreRows.first().getByRole("link").allTextContents(),
        ["Bibliothek aktuell", "Stadtmitteilung"]);
      await scoreRows.last().getByText("Vollständigkeit ungeprüft", { exact: true }).waitFor();
      if (width >= 390) {
        await captureSection(page, similarity, width === 1280 ? "source-similarity.png" : "source-similarity-mobile.png");
      }
      await comparison?.hold(2);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width);
      await page.locator("#claim-list button").nth(1).click();
      assert.equal(await matches.count(), 0);
      assert.equal(await plenum.isVisible(), false);
      assert.equal(await detail.locator("blockquote").textContent(), `„${legacyQuote}“`);
      if (comparison) {
        const oldBundle = structuredClone(bundle);
        delete oldBundle.review.shared_wording.source_similarities;
        oldBundle.review.sources[0].title = "Älterer Prüfbericht";
        await page.locator("#report-file").setInputFiles({
          name: "old-report.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(oldBundle)),
        });
        await page.getByRole("heading", { name: "Älterer Prüfbericht" }).waitFor();
        assert.equal(await similarity.isVisible(), false);
      }
      assert.deepEqual(errors, []);
    } finally {
      await page.close();
    }
  }
}

async function checkLocalRun(browser, recorder) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 960 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const origin = "http://127.0.0.1:8765";
  const runId = "ab".repeat(16);
  const runPath = "/api/runs/" + runId;
  const articleUrl = "https://example.org/lokal";
  const nextId = "cd".repeat(16);
  const nextPath = "/api/runs/" + nextId;
  const comparison = {
    source_id: "comparison-1", version_id: "v1",
    title: "Vergleichsbericht", url: "https://example.org/vergleich",
  };
  const passage = "Die Erhebung erfasst die erste Woche des Monats.";
  const question = "Was sagt der Artikel?";
  const claimText = "Die Steuersenkung wurde an allen Tankstellen vollständig weitergegeben.";
  const record = {
    run_id: runId, article_url: articleUrl, started_at: "2026-11-20T08:00:00Z",
    status: "running", stage: "capture", has_report: false,
  };
  let stage = "capture";
  let payload;
  let draft;
  let studySearches = 0;
  const report = {
    case_id: runId,
    status: "partial",
    retrievals: [{ status: "failed", requested_url: "https://example.org/missing", detail: "HTTP 403" }],
    model_calls: [
      { model: "local-model-a", task: "DraftArticleExtraction", status: "succeeded",
        wall_time_ms: 1450, prompt_tokens: 210, output_tokens: 64, eval_duration_ns: 1200000000 },
      { model: "local-model-a", task: "DraftReview", status: "failed",
        wall_time_ms: 480, prompt_tokens: null, output_tokens: null, eval_duration_ns: null },
    ],
    review: {
      article_source_id: "article",
      sources: [{ source_id: "article", title: "Lokaler Prüfbericht", url: articleUrl }, comparison],
      question, status: "partial",
      claims: [{
        claim_id: "claim-1",
        review: {
          claim: claimText, status: "partial",
          source_diff: {
            sources: [{ source: comparison, judgments: [{ relation: "qualifies", evidence_ids: ["quote"] }] }],
            evidence: [{
              evidence_id: "quote", text: passage,
              citations: [{ source_id: comparison.source_id, version_id: comparison.version_id }],
            }],
          },
        },
        source_comparison: [],
      }],
      interests: { status: "no_evidence", sources: [] },
      editorial: {
        status: "partial",
        claims: [{ claim_id: "claim-1", assigned_findings: [
          { finding_id: "finding-1", source_id: comparison.source_id, relation: "qualifies", evidence_ids: ["quote"] },
        ], unresolved_finding_ids: ["finding-1"] }],
        assessments: [{ agent_id: "model-1", status: "succeeded", claims: [
          { claim_id: "claim-1", assessment: "Die Quellen sind unvollständig.",
            findings: [{ finding_id: "finding-1", outcome: "unclear", reasoning: "Zeitpunkt offen." }] },
        ] }],
      },
    },
  };
  const nextReport = {
    ...report, case_id: nextId,
    review: {
      ...report.review,
      sources: [{ ...report.review.sources[0], title: "Neue lokale Prüfung" }, comparison],
    },
  };
  const digest = createHash("sha256").update(JSON.stringify(report)).digest("hex");
  const approvedAt = "2026-11-20T08:30:00Z";
  await page.route(origin + "/**", async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === "/api/runs" && route.request().method() === "POST") {
      payload = route.request().postDataJSON();
      return route.fulfill({ status: 202, json: record });
    }
    if (pathname === "/api/runs") {
      const next = { ...record, run_id: nextId, status: "partial", has_report: true };
      return route.fulfill({ json: payload ? [record, next] : [] });
    }
    if (pathname === runPath) {
      if (stage) {
        record.stage = stage;
      } else {
        record.status = "partial";
        record.has_report = true;
      }
      return route.fulfill({ json: record });
    }
    if (pathname === runPath + "/report") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(report) });
    }
    if (pathname === nextPath + "/report") return route.fulfill({ json: nextReport });
    if (pathname === nextPath + "/claims/claim-1/studies") return route.fulfill({ json: null });
    if (pathname === runPath + "/claims/claim-1/studies") {
      if (route.request().method() === "POST") studySearches += 1;
      const note = { value: "300 Tankstellen in Deutschland", quote: "300 German filling stations" };
      const paper = { title: "Studie zur Weitergabe", url: "https://doi.org/10.1234/fuel",
        access: "full_text", excerpt_only: true,
        assessment: { population: note, period: { value: "Juni bis August 2022", quote: "June to August 2022" },
          measured: { value: "Zapfsäulenpreise", quote: "We measured pump prices" },
          finding: { value: "Weitergabe variierte nach Kraftstoff", quote: "Pass-through varied by fuel type" },
          rationale: { value: "Vollständige Weitergabe nur für Diesel", quote: "Full pass-through was observed only for diesel" },
          relation: "qualifies", review_status: "confirmed" } };
      return route.fulfill({ json: studySearches ? { status: "complete", papers: [paper,
        { title: "Studie mit abweichender Einordnung", access: "abstract",
          url: "https://doi.org/10.1234/legacy", assessment: {
            relation: "supports", finding: { value: "Im letzten Monat 50 Prozent." },
            rationale: { value: "Belegt vollständige Weitergabe." },
          } },
        { title: "Nur indexierte Studie", url: "https://doi.org/10.1234/index", access: "metadata" }] } : null });
    }
    if (pathname === nextPath + "/editorial-draft") return route.fulfill({ json: null });
    if (pathname === runPath + "/editorial-draft") {
      if (route.request().method() === "GET") {
        return route.fulfill({ contentType: "application/json", body: JSON.stringify(draft ?? null) });
      }
      const update = route.request().postDataJSON();
      assert.equal(update.review_sha256, digest);
      assert.equal(update.revision, draft?.revision || 0);
      const approved = update.action === "approve";
      if (approved) {
        assert.equal(update.text, draft.text);
        assert.equal(update.sources_checked, true);
        assert.equal(update.open_findings_addressed, true);
      }
      draft = { review_sha256: digest, revision: update.revision + 1, text: update.text,
        approved_at: approved ? approvedAt : null };
      return route.fulfill({ json: draft });
    }
    if (pathname === "/") return route.fulfill({ path: join(repo, "web/index.html") });
    return route.fulfill({ path: join(repo, "web", pathname.slice(1)) });
  });
  try {
    await page.goto(origin);
    const start = page.getByRole("button", { name: "Analyse starten", exact: true });
    await start.waitFor();
    const workflow = page.locator("#agent-workflow");
    const roles = workflow.locator("#agent-roles > li");
    assert.equal(await roles.count(), 5);
    assert.equal(await roles.nth(3).locator(".agent-status").textContent(), "Kein Ergebnis");
    await page.locator("#urls").fill(articleUrl + "\nhttps://example.org/missing");
    await page.locator("#question").fill(question);
    const intake = await recorder.open("local-analysis.gif", page);
    await intake.hold(1.3);
    await start.click();
    const agents = await recorder.open("agent-workflow.gif", page);
    const current = workflow.locator('[aria-current="step"]');
    await workflow.locator('[data-role="article"][aria-current="step"]').waitFor();
    await workflow.getByText("Lauf für " + articleUrl, { exact: true }).waitFor();
    await agents.scrollTo(workflow, 1);
    await agents.hold();
    stage = "provenance";
    await workflow.locator('[data-role="research"][aria-current="step"]').waitFor();
    await agents.hold();
    stage = "comparison";
    await workflow.locator('[data-role="comparison"][aria-current="step"]').waitFor();
    await page.getByText("Aussagen werden mit den Belegen verglichen …", { exact: true }).waitFor();
    assert.equal(await current.count(), 1);
    assert.equal(await start.isDisabled(), true);
    await intake.scrollTo("#intake-heading", 1);
    await intake.hold(1);
    await agents.scrollTo(workflow, 1);
    await agents.hold(1.1);
    stage = "interests";
    await workflow.locator('[data-role="interests"][aria-current="step"]').waitFor();
    await captureSection(page, workflow, "agent-workflow.png");
    await agents.hold(1.1);
    stage = "editorial";
    await workflow.locator('[data-role="editorial"][aria-current="step"]').waitFor();
    await agents.hold(1.1);
    stage = null;
    await page.getByRole("heading", { name: "Lokaler Prüfbericht", exact: true }).waitFor();
    assert.equal(await current.count(), 0);
    assert.ok(await page.locator("#agent-run-source").isHidden());
    assert.equal(await workflow.getByRole("link", { name: "Behauptungsanalyse" }).getAttribute("href"),
      "#claims-heading");
    assert.deepEqual(await roles.locator(".agent-status").allTextContents(),
      ["Ergebnis", "Teilbericht", "Teilbericht", "Keine Belege", "Teilbericht"]);
    await agents.scrollTo(workflow);
    await agents.hold(1.5);
    const inspector = workflow.locator("#agent-inspector");
    const auditClip = await recorder.open("agent-inspector.gif", page);
    const researchAudit = workflow.locator('[data-role="research"]').getByRole("button", { name: "Einzelbeiträge" });
    await researchAudit.click();
    await inspector.getByRole("heading", { name: "Quellenrecherche" }).waitFor();
    await inspector.getByText("Code, kein KI-Modell", { exact: false }).waitFor();
    await auditClip.scrollTo(inspector);
    await auditClip.hold(1.5);
    const editorialAudit = workflow.locator('[data-role="editorial"]').getByRole("button", { name: "Einzelbeiträge" });
    await editorialAudit.click();
    await inspector.getByText("model-1", { exact: false }).waitFor();
    assert.equal(await inspector.locator(".agent-audit-row").count(), 1);
    await auditClip.scrollTo(inspector);
    await auditClip.hold(1.5);
    await captureSection(page, workflow, "agent-inspector.png");
    await page.setViewportSize({ width: 390, height: 960 });
    await page.waitForFunction(() => document.documentElement.scrollWidth === window.innerWidth);
    await captureSection(page, workflow, "agent-inspector-mobile.png");
    await page.setViewportSize({ width: 1280, height: 960 });
    const metrics = page.locator("#model-metrics");
    assert.equal(await metrics.isHidden(), false);
    await metrics.locator("summary").click();
    assert.equal(await metrics.locator("tbody tr").count(), 2);
    await metrics.getByText("53,3", { exact: true }).waitFor();
    await metrics.getByText("Nicht erfasst", { exact: true }).first().waitFor();
    const metricsClip = await recorder.open("model-metrics.gif", page);
    await metricsClip.scrollTo(metrics);
    await metricsClip.hold(1.6);
    await captureSection(page, metrics, "model-metrics.png");
    await page.setViewportSize({ width: 390, height: 960 });
    await page.waitForFunction(() => document.documentElement.scrollWidth === window.innerWidth);
    await captureSection(page, metrics, "model-metrics-mobile.png");
    await page.setViewportSize({ width: 1280, height: 960 });
    const interests = workflow.getByRole("link", { name: "Interessenprüfung" });
    await interests.focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.locator(":focus").getAttribute("id"), "interests-heading");
    assert.ok(await page.locator("#interests-heading").evaluate((summary) => summary.parentElement.open));
    await agents.hold(1.5);
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 960 });
      await page.waitForFunction(() => document.documentElement.scrollWidth === window.innerWidth);
      assert.equal(await roles.count(), 5);
      if (width === 390) await captureSection(page, workflow, "agent-workflow-mobile.png");
    }
    await page.setViewportSize({ width: 1280, height: 960 });
    assert.equal(payload.article_url, articleUrl);
    assert.equal(payload.question, question);
    assert.deepEqual(payload.comparison_urls, ["https://example.org/missing"]);
    await page.locator("#retrieval-issues > summary").click();
    await page.locator("#retrieval-issues-list").getByText("HTTP 403", { exact: false }).waitFor();
    assert.equal(await start.isEnabled(), true);
    const issues = page.locator("#retrieval-issues");
    await intake.scrollTo(issues);
    await captureSection(page, issues, "local-analysis.png");
    await intake.hold(1.4);
    const studies = page.locator("#claim-studies");
    const papers = await recorder.open("studies.gif", page);
    await papers.scrollTo(studies, 1);
    await papers.hold();
    assert.equal(studySearches, 0);
    await studies.getByRole("button", { name: "Studien suchen", exact: true }).click();
    await studies.getByText("Volltext abgerufen · Auszüge ausgewertet", { exact: true }).waitFor();
    await studies.getByText("Nur Metadaten · Relevanz ungeprüft", { exact: true }).waitFor();
    await studies.getByText("Juni bis August 2022", { exact: true }).waitFor();
    await studies.getByText("Zapfsäulenpreise", { exact: true }).waitFor();
    await studies.getByText("Weitergabe variierte nach Kraftstoff", { exact: true }).waitFor();
    await studies.getByText("Vollständige Weitergabe nur für Diesel", { exact: true }).waitFor();
    await studies.getByText("Im letzten Monat 50 Prozent.", { exact: true }).waitFor();
    assert.equal(await studies.getByText("Belegt vollständige Weitergabe.", { exact: true }).count(), 0);
    await papers.scrollTo(studies);
    await papers.hold(1.5);
    await studies.getByText("Textbelege", { exact: true }).click();
    await studies.getByText("300 German filling stations", { exact: true }).waitFor();
    assert.equal(await studies.getByRole("link", { name: "Studie zur Weitergabe", exact: true }).getAttribute("href"), "https://doi.org/10.1234/fuel");
    await papers.scrollTo(studies.getByText("Textbelege", { exact: true }).first());
    await papers.hold(1.5);
    for (const [width, filename] of [[1280, "studies.png"], [390, "studies-mobile.png"]]) {
      await page.setViewportSize({ width, height: 1120 });
      await page.evaluate(() => document.fonts.ready);
      // The source graph repositions its nodes in a ResizeObserver.
      await page.waitForFunction(() => document.documentElement.scrollWidth === window.innerWidth);
      await studies.evaluate((panel) => panel.scrollIntoView({ block: "start" }));
      assert.ok(await studies.getByRole("link", { name: "Studie zur Weitergabe" }).isVisible());
      await page.screenshot({ ...screenshotOptions, path: join(output, filename) });
    }
    await page.setViewportSize({ width: 1280, height: 960 });
    const text = page.getByLabel("Redaktioneller Text für die Veröffentlichung");
    const save = page.getByRole("button", { name: "Entwurf speichern", exact: true });
    const approve = page.getByRole("button", { name: "Freigabe erteilen", exact: true });
    const exportText = page.getByRole("button", { name: "Freigegebenen Text exportieren", exact: true });
    const preview = page.getByRole("button", { name: "Leservorschau öffnen" });
    const statement = "Die Quelle nennt einen unklaren Zeitpunkt.\n\nGrenzwert: <5 % & nur für die erste Woche.";
    const editorial = await recorder.open("editorial-review.gif", page);
    await editorial.scrollTo("#release-form", 1);
    await text.fill(statement);
    await editorial.hold();
    assert.ok(await save.isEnabled());
    assert.ok(await approve.isDisabled());
    assert.ok(await preview.isDisabled());
    await save.click();
    await page.getByText("Entwurf gespeichert.", { exact: true }).waitFor();
    assert.ok(await approve.isDisabled());

    await page.getByText("Gespeicherte Analysen", { exact: true }).click();
    await intake.hold(1.5);
    await page.locator('#run-list a[href="?run=' + runId + '"]').click();
    await page.getByText("Entwurf gespeichert.", { exact: true }).waitFor();
    await studies.getByText("Juni bis August 2022", { exact: true }).waitFor();
    assert.equal(studySearches, 1);
    assert.equal(await text.inputValue(), statement);
    assert.ok(await approve.isDisabled());
    await intake.scrollTo("#review", 1);
    await intake.hold(1.4);
    for (const checkbox of await page.locator("#release-checks").getByRole("checkbox").all()) {
      await checkbox.check();
    }
    await editorial.scrollTo("#release-form");
    await editorial.hold();
    await approve.click();
    await page.getByText(/Freigabe erteilt ·/).waitFor();
    await editorial.hold();
    const [download] = await Promise.all([page.waitForEvent("download"), exportText.click()]);
    const exported = JSON.parse(await readFile(await download.path(), "utf8"));
    assert.equal(exported.text, statement);
    assert.equal(exported.review_sha256, digest);
    assert.equal(exported.reviewed_at, approvedAt);
    assert.equal(exported.article_url, articleUrl);
    assert.equal(exported.editorial, undefined);

    await preview.click();
    const dialog = page.getByRole("dialog", { name: "Leservorschau" });
    const frame = dialog.frameLocator("iframe");
    await frame.getByRole("heading", { name: "Redaktionelle Einordnung" }).waitFor();
    assert.equal(await frame.locator(".statement").textContent(), statement);
    assert.equal(await frame.getByRole("link", { name: "Geprüften Artikel öffnen" }).getAttribute("href"), articleUrl);
    await frame.getByText("Freigabedaten", { exact: true }).click();
    assert.equal(await frame.locator("time").getAttribute("datetime"), approvedAt);
    assert.equal(await frame.locator("code").textContent(), digest);
    assert.equal(await frame.getByText("Zeitpunkt offen.", { exact: false }).count(), 0);
    const themeColors = () => frame.locator("html").evaluate((node) => {
      const style = getComputedStyle(node);
      return [style.color, style.backgroundColor];
    });
    await page.emulateMedia({ colorScheme: "light" });
    assert.deepEqual(await themeColors(), ["rgb(35, 26, 49)", "rgb(250, 247, 255)"]);
    await page.emulateMedia({ colorScheme: "dark" });
    assert.deepEqual(await themeColors(), ["rgb(241, 234, 250)", "rgb(23, 19, 32)"]);
    await page.screenshot({ ...screenshotOptions, path: join(output, "reader-preview.png") });
    await editorial.hold(1.8);

    const htmlButton = dialog.getByRole("button", { name: "HTML herunterladen" });
    const [htmlFile] = await Promise.all([page.waitForEvent("download"), htmlButton.click()]);
    assert.equal(htmlFile.suggestedFilename(), "quellenlot-lesefassung.html");
    const html = await readFile(await htmlFile.path(), "utf8");
    assert.equal(html, await dialog.locator("iframe").getAttribute("srcdoc"));
    assert.match(html, /Grenzwert: &lt;5 % &amp; nur/);
    assert.doesNotMatch(html, /<script|finding-1|Vergleichsbericht|Zeitpunkt offen\./);

    const approved = draft;
    draft = { ...draft, revision: draft.revision + 1, approved_at: null };
    await htmlButton.click();
    await dialog.getByText("Die Freigabe hat sich geändert. Öffne den Bericht erneut.").waitFor();
    draft = approved;
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });

    const review = page.locator("#private-review");
    await review.getByText(claimText, { exact: true }).click();
    const evidence = review.locator(".editorial-evidence");
    await evidence.getByText("Belege zum Befund", { exact: true }).click();
    const source = evidence.getByRole("link", { name: comparison.title, exact: true });
    assert.match(await source.getAttribute("href"), /^https:\/\/example\.org\/vergleich#:~:text=/);
    await evidence.getByText(passage, { exact: true }).waitFor();
    await review.getByText("In der Schlussprüfung umstritten oder unklar.").waitFor();
    await captureSection(page, review, "editorial-draft.png");

    await page.goto(origin + "?run=" + nextId);
    await page.getByRole("heading", { name: "Neue lokale Prüfung", exact: true }).waitFor();
    assert.equal(await text.inputValue(), "");
    assert.ok(await approve.isDisabled());
    assert.ok(await exportText.isDisabled());
    assert.ok(await preview.isDisabled());
    for (const checkbox of await page.locator("#release-checks").getByRole("checkbox").all()) {
      assert.equal(await checkbox.isChecked(), false);
    }

    await page.goto(origin + "?run=" + runId);
    await page.getByText(/Freigabe erteilt ·/).waitFor();
    assert.equal(await text.inputValue(), statement);
    assert.ok(await exportText.isEnabled());
    await text.fill("Eine korrigierte Einordnung.");
    assert.ok(await exportText.isDisabled());
    assert.ok(await preview.isDisabled());
    await save.click();
    await page.getByText("Entwurf gespeichert.", { exact: true }).waitFor();
    assert.ok(await approve.isDisabled());
    assert.equal(draft.approved_at, null);
    assert.deepEqual(errors, []);
  } finally {
    await page.close();
  }
}

async function checkParliament(browser, record) {
  for (const width of [1280, 390, 320]) {
    const { page, errors } = await openDemo(browser, { width, height: 960 });
    try {
      await page.getByRole("link", { name: "Programme & Abstimmungen", exact: true }).click();
      await page.getByRole("heading", { name: "Schuldenbremse und Investitionen", exact: true }).waitFor();
      const programmes = page.locator("#programme-comparisons");
      const clip = width === 1280 ? await record.open("parliament.gif", page) : null;
      await clip?.hold();
      await programmes.getByText("An der grundgesetzlichen Schuldenbremse festhalten.", { exact: false }).waitFor();
      await programmes.getByText("Spannung zur Ankündigung", { exact: true }).waitFor();
      await page.getByRole("radio", { name: "Stimme zu", exact: true }).check();
      assert.deepEqual(await programmes.getByRole("status").allTextContents(), [
        "Das Programm legt sich zu dieser Frage nicht eindeutig fest.",
        "Deine Position und die Programmaussage zeigen in dieselbe Richtung.",
      ]);
      await page.getByRole("radio", { name: "Stimme nicht zu", exact: true }).check();
      await programmes.getByText("Deine Position und die Programmaussage gehen in unterschiedliche Richtungen.").waitFor();
      await page.getByRole("radio", { name: "Stimme zu", exact: true }).check();

      await clip?.scrollTo(programmes);
      await clip?.hold(1.5);
      const final = page.locator("#schuldenbremse-schluss");
      const amendment = page.locator("#schuldenbremse-aenderung");
      await programmes.getByRole("link", { name: "Schlussabstimmung", exact: true }).first().click();
      assert.equal(await page.locator(":focus").evaluate((node) => node.parentElement.id), "schuldenbremse-schluss");
      await final.getByText("Die Stimmen gelten dem gesamten Paket.", { exact: false }).waitFor();
      assert.deepEqual(await final.getByRole("row").nth(1).getByRole("cell").allTextContents(), ["512", "206", "0", "15"]);
      assert.match(await final.getByRole("link", { name: /Namentliche Stimmen/ }).getAttribute("href"), /id=951$/);
      assert.match(await final.getByRole("link", { name: /Wortlaut/ }).getAttribute("href"), /2015117\.pdf#page=10$/);
      await clip?.hold(1.5);
      await clip?.scrollTo(amendment);
      await amendment.locator("summary").click();
      await amendment.getByText("einmalig bis zu 300 Milliarden Euro", { exact: false }).waitFor();
      assert.deepEqual(await amendment.getByRole("row").nth(1).getByRole("cell").allTextContents(), ["85", "630", "2", "16"]);
      assert.match(await amendment.getByRole("link", { name: /Namentliche Stimmen/ }).getAttribute("href"), /id=950$/);
      await clip?.hold();
      await programmes.getByRole("link", { name: "Spätere Umsetzung", exact: true }).click();
      const later = page.locator("#schuldenbremse-svikg");
      await later.getByRole("link", { name: /SVIKG/ }).waitFor();
      await clip?.hold(1.5);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width);
      assert.deepEqual(errors, []);
      if (width === 1280) {
        const skip = page.getByRole("link", { name: "Zum Inhalt", exact: true });
        assert.equal(await skip.evaluate((link) => getComputedStyle(link).clipPath), "inset(50%)");
        await skip.focus();
        assert.equal(await skip.evaluate((link) => getComputedStyle(link).clipPath), "none");
        await skip.blur();
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.evaluate(() => document.fonts.ready);
        await page.screenshot({ ...screenshotOptions, fullPage: true, path: join(output, "parliament.png") });
      }
      await page.getByRole("link", { name: "Artikel prüfen", exact: true }).click();
      await page.getByRole("heading", { name: "Kam der Tankrabatt an?" }).waitFor();
    } finally {
      await page.close();
    }
  }
}

async function checkTopicTrends(browser, record) {
  const origin = "http://127.0.0.1:8765";
  const captureTime = new Date("2026-11-20T12:00:00Z");
  const date = (daysAgo) => new Date(captureTime.getTime() - daysAgo * 86400000).toISOString().slice(0, 10);
  const [start, gap, neighbor, peak, after, end] = [16, 15, 14, 13, 12, 11].map(date);
  const lead = { title: "Bericht aus dem Suchfenster", url: "https://example.org/zeitung", indexed_date: after };
  const news = {
    label: "Tankrabatt",
    source_url: "https://api.gdeltproject.org/api/v2/doc/doc?query=Tankrabatt",
    points: [
      { date: start, value: 0 },
      { date: neighbor, value: 0.02 },
      { date: peak, value: 0.12 },
      { date: after, value: 0.04 },
    ],
  };
  const publication = {
    source_id: "article", title: "Beispielbericht", url: "https://example.org/artikel",
    published_at: { value: start },
  };
  const csv = `Kategorie: Alle Kategorien\n\nTag,Tankrabatt: (Deutschland)\n${start},10\n${gap},<1\n${neighbor},20\n${peak},100\n${after},25\n`;
  for (const [width, name] of [[1280, "desktop"], [390, "mobile"]]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: 1 });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    let attempts = 0;
    let suggestions = 0;
    await page.route(origin + "/**", async (route) => {
      const { pathname } = new URL(route.request().url());
      if (pathname === "/api/news-trend") {
        assert.equal(route.request().method(), "POST");
        assert.deepEqual(route.request().postDataJSON(), { topic: "Tankrabatt", days: 30, language: "german" });
        if (attempts++ > 0) return route.fulfill({ status: 502, json: { error: "GDELT ist nicht verfügbar." } });
        return route.fulfill({ json: news });
      }
      if (pathname === "/api/trend-events") {
        assert.equal(route.request().method(), "POST");
        const topic = suggestions++ === 0 ? "Tankrabatt" : "Tankrabatt Suche";
        assert.deepEqual(route.request().postDataJSON(), { topic, language: "german", peak_date: peak });
        return route.fulfill({ json: {
          peak_date: peak, window_start: gap, window_end: end, articles: [lead],
        } });
      }
      if (pathname === "/api/runs") return route.fulfill({ json: [] });
      if (pathname === "/") return route.fulfill({ path: join(repo, "web/index.html") });
      return route.fulfill({ path: join(repo, "web", pathname.slice(1)) });
    });
    try {
      await page.goto(origin);
      await page.clock.setFixedTime(captureTime);
      await page.getByText("Thementrends und Ereignisse", { exact: true }).click();
      const clip = width === 1280 ? await record.open("topic-trends.gif", page) : null;
      await clip?.scrollTo("#topic-trends", 1);
      await clip?.hold();
      await page.getByLabel("Suchbegriff", { exact: true }).fill("Tankrabatt");
      await page.getByRole("button", { name: "GDELT abfragen" }).click();
      await page.getByText("Medienzeitreihe geladen.", { exact: true }).waitFor();
      const newsPanel = page.locator('[data-kind="news"].trend-series-panel');
      assert.equal((await newsPanel.locator(".trend-line").getAttribute("d")).split("M").length - 1, 2);

      await page.getByLabel("Google-Trends-CSV", { exact: true }).setInputFiles({
        name: "multiTimeline.csv", mimeType: "text/csv", buffer: Buffer.from(csv),
      });
      await page.getByText("CSV geladen.", { exact: true }).waitFor();
      const search = page.locator('[data-kind="search"].trend-series-panel');
      assert.equal((await search.locator(".trend-line").getAttribute("d")).split("M").length - 1, 2);
      assert.equal(await search.locator("tbody tr").count(), 5);
      assert.equal(await search.locator("tbody tr").nth(1).locator("td").last().textContent(), "<1");
      await clip?.scrollTo(newsPanel);
      await clip?.hold(1.5);

      await page.locator("#report-file").setInputFiles({
        name: "report.json", mimeType: "application/json",
        buffer: Buffer.from(JSON.stringify({
          status: "no_claims", article_source_id: "article", sources: [publication], claims: [],
        })),
      });
      const markers = page.locator("#trend-events");
      await markers.getByText("Veröffentlichung", { exact: true }).waitFor();
      assert.equal(await markers.getByRole("link", { name: "Beispielbericht" }).getAttribute("href"), publication.url);

      await page.getByRole("button", { name: "Medienausschlag untersuchen" }).click();
      const suggestion = page.locator("#trend-suggestion-panel");
      const reference = suggestion.getByRole("link", { name: lead.title });
      assert.equal(await reference.getAttribute("href"), lead.url);
      await suggestion.getByText(/GDELT erfasst am/).waitFor();
      await clip?.scrollTo(suggestion);
      await clip?.hold();
      assert.equal(await markers.getByRole("link", { name: lead.title }).count(), 0);
      await suggestion.getByRole("button", { name: "Beleg übernehmen: " + lead.title }).click();
      assert.equal(await page.getByLabel("Ereignis", { exact: true }).inputValue(), lead.title);
      assert.equal(await page.getByLabel("Beleglink", { exact: true }).inputValue(), lead.url);
      assert.equal(await page.getByLabel("Ereignisdatum", { exact: true }).inputValue(), "");
      await page.getByLabel("Suchbegriff", { exact: true }).fill("Tankrabatt Suche");
      await page.getByRole("button", { name: "Suchausschlag untersuchen" }).click();
      await reference.waitFor();
      assert.equal(suggestions, 2);
      await page.getByLabel("Suchbegriff", { exact: true }).fill("Tankrabatt");

      await page.getByLabel("Ereignisdatum", { exact: true }).fill(gap);
      await page.getByLabel("Ereignis", { exact: true }).fill("Beispielbeschluss");
      await page.getByLabel("Beleglink", { exact: true }).fill("https://example.org/beschluss");
      await page.getByRole("button", { name: "Ereignis hinzufügen" }).click();
      await markers.getByRole("link", { name: "Beispielbeschluss" }).waitFor();
      assert.equal(await page.locator(".trend-marker.active").count(), 2);
      if (clip) {
        await clip.scrollTo(markers);
        await captureSection(page, suggestion, "trend-events.png");
        await clip.hold(1.6);
      }
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width);
      await page.locator("#topic-trends").screenshot({ ...screenshotOptions, path: join(output, "trends-" + name + ".png") });
      await page.getByRole("button", { name: "GDELT abfragen" }).click();
      await page.getByText("GDELT ist nicht verfügbar.", { exact: true }).waitFor();
      assert.ok(await newsPanel.isVisible());
      assert.deepEqual(errors, []);
    } finally {
      await page.close();
    }
  }
}

function encodeGif(directory, name, width) {
  execFileSync(commands.ffmpeg, [
    "-hide_banner", "-loglevel", "error", "-y", "-filter_complex_threads", "1",
    "-framerate", String(gifFps), "-i", join(directory, "frame-%d.png"),
    "-filter_complex", `scale=${width}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=none:diff_mode=rectangle`,
    "-loop", "0", join(output, name),
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
    assert.ok(Math.abs(Number(format.duration) - expectedFrames / gifFps) <= 0.1, "GIF plays at the target frame rate");
  }
  const bytes = await readFile(path);
  assert.ok(bytes.length > 10_000 && bytes.length < 2_000_000, `${name} has ${bytes.length} bytes`);
  return {
    file: name,
    width: stream.width,
    height: stream.height,
    frames: expectedFrames,
    ...(name.endsWith(".gif") ? { fps: gifFps } : {}),
    bytes: bytes.length,
    sha256: createHash("sha256").update(bytes).digest("hex"),
  };
}

async function main() {
  await mkdir(output, { recursive: true });
  const frames = await mkdtemp(join(tmpdir(), "quellenlot-preview-"));
  try {
    const browser = await chromium.launch();
    const record = createRecorder(frames);
    try {
      await captureOverview(browser, 1280, 960, "desktop.png");
      await captureOverview(browser, 390, 844, "mobile.png", record);
      await captureWalkthrough(browser, record);
      await checkImportOutcomes(browser, record);
      await checkLocalRun(browser, record);
      await checkTopicTrends(browser, record);
      await checkTheme(browser);
      await checkClaimDiff(browser, record);
      await checkParliament(browser, record);
    } finally {
      await browser.close();
    }
    const media = [];
    for (const [name, width] of Object.entries(gallery)) {
      if (name.endsWith(".gif")) {
        const { directory, frame } = record.get(name);
        encodeGif(directory, name, width);
        media.push(await inspectMedia(name, width, frame));
      } else {
        media.push(await inspectMedia(name, width));
      }
    }
    const { GITHUB_SHA, GITHUB_SERVER_URL, GITHUB_REPOSITORY, GITHUB_RUN_ID } = process.env;
    const manifest = {
      source_commit: GITHUB_SHA || null,
      workflow_run: GITHUB_RUN_ID ? `${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}` : null,
      scenario: "Tankrabatt demo, fixture-backed analyses and trends, and curated Bundestag records",
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
