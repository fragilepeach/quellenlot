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

    await page.locator("#source-controls").getByRole("button", { name: "TU Dresden" }).click();
    assert.match(await evidence.locator("blockquote").textContent(), /Anfang Juni/);
    await evidence.getByText("Datum und Version", { exact: true }).click();
    assert.match(await evidence.locator("dl").textContent(), /19\.10\.2022.*20\.10\.2022/);
    await graph.getByText("verweist auf", { exact: true }).waitFor();
    await shot("#evidence-panel");

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
