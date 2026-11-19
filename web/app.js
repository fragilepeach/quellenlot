"use strict";

const relationLabels = {
  supports: "Stützt",
  contextualizes: "Liefert Kontext",
  qualifies: "Schränkt ein",
  contradicts: "Widerspricht",
  omits: "Nicht behandelt",
  not_assessable: "Nicht beurteilbar",
};

const demoSources = {
  ifo: {
    id: "ifo",
    name: "Freitas & Syga",
    type: "Studie · ifo Dresden berichtet",
    url: "https://www.ifo.de/publikationen/2022/aufsatz-zeitschrift/35-cent-weniger-fuer-benzin-und-17-cent-weniger-fuer-diesel",
    published: "2022-10-18",
  },
  rwi: {
    id: "rwi",
    name: "RWI",
    type: "Pressemitteilung zur RWI-Studie",
    url: "https://www.rwi-essen.de/presse/wissenschaftskommunikation/pressemitteilungen/detail/rwi-weitergabe-des-tankrabatts-im-jahr-2022-nahm-ueber-die-zeit-stark-ab-und-fiel-je-nach-region-sehr-unterschiedlich-aus",
    published: "2024-07-18",
  },
  tu: {
    id: "tu",
    name: "TU Dresden",
    type: "Hochschulmeldung",
    url: "https://tu-dresden.de/bu/wirtschaft/die-fakultaet/news/tankrabatt-steuersenkung-kam-im-august-nicht-mehr-vollstaendig-an?set_language=de",
    published: "2022-10-19",
    updated: "2022-10-20",
    cites: ["ifo"],
  },
};

function demoEvidence(source, relation, passage, reason) {
  return { source: demoSources[source], judgments: [{ relation, passage, reason }] };
}

const demo = {
  meta: "Beispielfall · Deutschland 2022",
  title: "Kam der Tankrabatt an?",
  question: "Wie viel von der Steuersenkung haben Tankstellen an Verbraucher*innen weitergegeben?",
  summary: [
    "Der Beispielartikel zieht eine positive Bilanz. Er behauptet, der Tankrabatt sei ",
    { claim: 0, text: "im Durchschnitt vollständig weitergegeben worden" },
    ", habe ",
    { claim: 1, text: "in allen drei Monaten gleich stark gewirkt" },
    " und sei ",
    { claim: 2, text: "in allen Regionen gleichermaßen angekommen" },
    ".",
  ],
  summaryNote: "Redaktionelles Beispiel mit fiktivem Eingabeartikel und realen Belegquellen.",
  graphNote: "Die TU-Meldung verweist auf die Studie von Freitas & Syga. Beide beziehen sich auf dieselbe Auswertung.",
  claims: [
    {
      text: "Der Tankrabatt wurde im Durchschnitt vollständig weitergegeben.",
      status: "Studien kommen zu unterschiedlichen Schätzungen",
      quote: "Über alle drei Monate betrachtet wurde die Steuersenkung im Durchschnitt vollständig an die Kundschaft weitergegeben.",
      evidence: [
        demoEvidence("ifo", "supports", "durchschnittlich 35 Cent weniger pro Liter Benzin und 17 Cent weniger pro Liter Diesel",
          "Die Schätzung vergleicht deutsche Zapfsäulenpreise mit denen europäischer Nachbarländer über den gesamten Zeitraum."),
        demoEvidence("rwi", "qualifies", "87 Prozent bei Diesel und 71 Prozent bei Superbenzin E10",
          "Die spätere RWI-Auswertung schätzt für beide Kraftstoffarten eine geringere durchschnittliche Weitergabe."),
        demoEvidence("tu", "contextualizes", "durchschnittlich tatsächlich weniger  pro Liter Benzin und pro Liter Diesel gezahlt",
          "Die Meldung verweist auf Freitas & Syga. Der Ausschnitt bestätigt die Entlastung, die Höhe steht in der Studie."),
      ],
    },
    {
      text: "Der Tankrabatt wirkte in allen drei Monaten gleich stark.",
      status: "Quellen beschreiben Schwankungen über die Zeit",
      quote: "In allen drei Monaten wirkte der Tankrabatt gleich stark.",
      evidence: [
        demoEvidence("ifo", "contradicts", "wurde der Steuernachlass nur teilweise weitergegeben",
          "Die Studie beschreibt eine geringere Weitergabe zu Beginn und Ende des Tankrabatts. Im Juli lag die geschätzte Weitergabe höher."),
        demoEvidence("tu", "contradicts", "Anfang Juni und im August kam der Tankrabatt nicht vollständig an.",
          "Die Hochschulmeldung berichtet über dieselbe Auswertung von Freitas & Syga."),
        demoEvidence("rwi", "contradicts", "im Verlauf der Monate Juli und August 2022 stark geschrumpft",
          "Auch das RWI beschreibt eine Veränderung im Verlauf des Sommers."),
      ],
    },
    {
      text: "Der Tankrabatt kam in allen Regionen gleichermaßen an.",
      status: "RWI berichtet regionale Unterschiede",
      quote: "Auch regional wurde der Tankrabatt überall gleichermaßen weitergegeben.",
      evidence: [
        demoEvidence("rwi", "contradicts", "regional sehr unterschiedlich ausgefallen",
          "Das RWI berichtet eine geringere Weitergabe in Regionen mit weniger Wettbewerb im Umfeld der Tankstellen."),
      ],
    },
  ],
};

const $ = (id) => document.getElementById(id);
const state = { report: demo, claimIndex: 0, sourceId: null };
const dateFormatter = new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeZone: "UTC" });

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function safeUrl(value) {
  try {
    const url = new URL(value);
    if (["http:", "https:"].includes(url.protocol) && !url.username && !url.password) {
      return url;
    }
  } catch {
    return null;
  }
  return null;
}

function sourceName(source) {
  return source.name || "Quelle";
}

function button(label, className) {
  const node = element("button", className, label);
  node.type = "button";
  return node;
}

function sourceButton(source, className) {
  const control = button(sourceName(source), className);
  control.dataset.source = source.id;
  control.setAttribute("aria-controls", "source-detail");
  return control;
}

function selectedClaim() {
  return state.report.claims[state.claimIndex];
}

function updateSelection(root, key, selected) {
  for (const control of root.querySelectorAll("[data-" + key + "]")) {
    const attribute = control.tagName === "A" ? "aria-current" : "aria-pressed";
    control.setAttribute(attribute, String(control.dataset[key] === selected));
  }
}

function renderReport(report) {
  state.report = report;
  state.claimIndex = 0;
  $("selection-status").textContent = "";
  $("case-meta").textContent = report.meta;
  $("case-title").textContent = report.title;
  $("case-question").textContent = report.question || "";
  $("empty-report").textContent = report.empty || "";
  $("empty-report").hidden = !report.empty;
  $("workspace").hidden = Boolean(report.empty);
  $("summary-text").replaceChildren(...report.summary.map((part) => {
    if (typeof part === "string") return document.createTextNode(part);
    const control = element("a", "highlight", part.text);
    control.href = "#evidence-panel";
    control.dataset.claim = String(part.claim);
    control.setAttribute("aria-controls", "evidence-panel");
    const number = element("sup", "", String(part.claim + 1).padStart(2, "0"));
    number.setAttribute("aria-hidden", "true");
    control.append(number);
    return control;
  }));
  $("summary-note").textContent = report.summaryNote || "";
  $("claim-count").textContent = String(report.claims.length);
  $("claim-list").replaceChildren(...report.claims.map((claim, index) => {
    const control = button("", "claim-button");
    control.dataset.claim = String(index);
    control.setAttribute("aria-controls", "evidence-panel");
    const number = element("span", "claim-id", String(index + 1).padStart(2, "0"));
    number.setAttribute("aria-hidden", "true");
    const text = element("span");
    text.append(element("span", "claim-label", claim.text), element("span", "claim-status", claim.status));
    control.append(number, text);
    return control;
  }));
  if (report.claims.length) selectClaim(0);
}

function selectClaim(index) {
  state.claimIndex = index;
  const claim = selectedClaim();
  const number = String(index + 1).padStart(2, "0");
  updateSelection($("workspace"), "claim", String(index));
  $("active-claim").textContent = "Aussage " + number;
  $("claim-description").textContent = claim.text;
  $("original-quote").textContent = claim.quote || "Kein geprüfter Wortlaut verfügbar.";
  const originalLink = sourceLink(state.report.article || {}, claim.quote, "Eingabeartikel öffnen");
  $("original-link").replaceChildren(...(originalLink ? [originalLink] : []));
  $("source-controls").replaceChildren(...claim.evidence.map(({ source }) => sourceButton(source, "source-button")));
  renderGraph(claim, number);
  selectSource(claim.evidence[0]?.source.id);
}

function formatDate(value) {
  if (!value) return "Unbekannt";
  const datePart = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return datePart ? dateFormatter.format(date) : value;
}

function sourceMetadata(source) {
  const details = element("details", "source-metadata");
  const list = element("dl");
  for (const [label, value] of [
    ["Veröffentlicht", formatDate(source.published)],
    ["Aktualisiert", formatDate(source.updated)],
    ["Erfasst", source.captured ? formatDate(source.captured) : "Nicht protokolliert"],
    ["Version", source.version],
  ]) {
    if (value) list.append(element("dt", "", label), element("dd", "", value));
  }
  details.append(element("summary", "", "Datum und Version"), list);
  return details;
}

function sourceLink(source, passage, label = "Originalquelle öffnen") {
  const url = safeUrl(source.url);
  if (!url) return null;
  if (passage) {
    const encoded = encodeURIComponent(passage.trim().replace(/\s+/g, " ")).replaceAll("-", "%2D");
    url.hash = url.hash + ":~:text=" + encoded;
  }
  const link = element("a", "source-link", label);
  link.href = url.href;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

function renderJudgment(judgment) {
  const container = element("div", "judgment");
  const heading = element("div", "source-caption");
  const relation = element("span", "relation", relationLabels[judgment.relation] || "Ohne Einordnung");
  relation.dataset.kind = judgment.relation;
  if (judgment.agent) heading.append(element("span", "judgment-meta", "Modell " + judgment.agent));
  heading.append(relation);
  container.append(heading);
  if (judgment.passage) {
    container.append(element("blockquote", "", "„" + judgment.passage + "“"));
  } else {
    container.append(element("p", "source-reason", "Kein exakt abgeglichener Beleg im Bericht."));
  }
  if (judgment.reason) container.append(element("p", "source-reason", judgment.reason));
  return container;
}

function selectSource(id) {
  const evidence = selectedClaim().evidence.find(({ source }) => source.id === id);
  state.sourceId = evidence?.source.id;
  updateSelection($("source-controls"), "source", state.sourceId);
  updateSelection($("graph"), "source", state.sourceId);

  const detail = $("source-detail");
  detail.replaceChildren();
  if (!evidence) {
    detail.append(element("p", "source-reason", "Zu dieser Aussage liegen keine Quellenbeurteilungen vor."));
    return;
  }
  const { source, judgments } = evidence;
  detail.append(element("p", "source-type", source.type || source.name));
  detail.append(...judgments.map(renderJudgment), sourceMetadata(source));
  const link = sourceLink(source, judgments.find((judgment) => judgment.passage)?.passage);
  if (link) detail.append(link);
}

function renderGraph(claim, number) {
  const graph = element("div", "graph");
  const branches = element("ul", "graph-branches");
  graph.append(element("div", "graph-root", "Aussage " + number), branches);

  for (const { source, judgments } of claim.evidence) {
    const branch = element("li", "graph-branch");
    const labels = new Set(judgments.map(({ relation }) => relation));
    const label = labels.size === 1 ? relationLabels[judgments[0].relation] : "Uneinheitliche Einordnung";
    branch.append(element("span", "graph-edge", label || "Bezug"), sourceButton(source, "source-button graph-node"));
    for (const originId of source.cites || []) {
      const origin = claim.evidence.find((item) => item.source.id === originId);
      if (origin) {
        const path = element("div", "graph-origin");
        path.append(element("span", "graph-edge", "verweist auf"), sourceButton(origin.source, "source-button graph-node"));
        branch.append(path);
      }
    }
    branches.append(branch);
  }
  $("graph").replaceChildren(graph);
  const hasCitation = claim.evidence.some(({ source }) => source.cites?.length);
  $("graph-note").textContent = hasCitation
    ? state.report.graphNote
    : "Für diese Aussage sind keine Verweise zwischen den Quellen dokumentiert.";
}

function normalizedEvidence(comparisons, originalId) {
  return comparisons
    .filter(({ source, judgments }) => source?.source_id !== originalId && judgments?.length)
    .map(({ source, judgments }) => ({
      source: {
        id: source.source_id,
        name: source.title,
        url: source.url,
        published: source.published_at?.value,
        updated: source.updated_at?.value,
        captured: source.captured_at,
        version: source.version_id,
      },
      judgments: judgments.flatMap((judgment) => {
        const quotes = judgment.citations?.filter((quote) =>
          quote.verified === true && quote.source_id === source.source_id &&
          quote.version_id === source.version_id && typeof quote.text === "string"
        );
        return (quotes?.length ? quotes : [null]).map((quote) => ({
          relation: judgment.relation,
          agent: judgment.agent_id,
          reason: judgment.reasoning,
          passage: quote?.text,
        }));
      }),
    }));
}

function readReport(data) {
  const retrievalReport = Array.isArray(data?.retrievals);
  const report = retrievalReport ? data.review : data;
  if (retrievalReport && data.status === "failed" && !report) {
    const failure = data.retrievals.find((item) => item.status === "failed");
    return {
      meta: "Importierter Bericht · Abruf fehlgeschlagen",
      title: "Artikel konnte nicht gelesen werden",
      question: data.question,
      summary: [],
      claims: [],
      empty: failure?.requested_url
        ? "Der angegebene Artikel konnte nicht abgerufen werden: " + failure.requested_url
        : "Der Bericht enthält keinen auswertbaren Artikel.",
    };
  }
  if (typeof report?.article_source_id !== "string" || !Array.isArray(report?.sources) || !Array.isArray(report?.claims)) {
    throw new Error("Kein Quellenlot-Artikelbericht. Wähle die JSON-Ausgabe eines Artikel- oder URL-Laufs.");
  }
  const article = report.sources.find((source) => source.source_id === report.article_source_id);
  const claims = report.claims.map((claim) => {
    if (typeof claim.review?.claim !== "string" || !Array.isArray(claim.source_comparison)) {
      throw new Error("Der Bericht enthält eine unvollständige Aussage.");
    }
    const quote = claim.article_quote;
    return {
      text: claim.review.claim,
      status: claim.review.status === "complete" ? "Modellbefunde verfügbar" : "Modellprüfung unvollständig",
      quote: quote?.verified === true && article && quote.source_id === article.source_id &&
        quote.version_id === article.version_id ? quote.text : null,
      evidence: normalizedEvidence(claim.source_comparison, report.article_source_id),
    };
  });
  const failed = data.status === "failed" || report.status === "failed";
  const partial = data.status === "partial" || report.status === "partial";
  const runStatus = failed ? " · Analyse fehlgeschlagen" : partial ? " · Teilbericht" : "";
  const empty = failed
    ? "Die Analyse konnte keine Aussagen ermitteln, weil die Extraktion fehlgeschlagen ist."
    : "Der Bericht enthält keine prüfbaren Aussagen.";
  return {
    meta: "Importierter Bericht" + runStatus,
    title: article?.title || "Artikelprüfung",
    question: report.question,
    article,
    summary: ["Dieser Agentenbericht enthält keine ausformulierte Artikelzusammenfassung."],
    claims,
    empty: claims.length ? "" : empty,
  };
}

$("workspace").addEventListener("click", (event) => {
  const control = event.target.closest("[data-claim], button[data-source]");
  if (!control) return;
  const index = control.dataset.claim;
  if (index !== undefined) {
    event.preventDefault();
    selectClaim(Number(index));
    if (matchMedia("(max-width: 820px)").matches) {
      $("evidence-heading").focus();
    } else {
      $("selection-status").textContent = $("active-claim").textContent + " ausgewählt. Belege aktualisiert.";
    }
  } else {
    selectSource(control.dataset.source);
    $("selection-status").textContent = "Beleg geöffnet: " + control.textContent;
    if (control.closest("#graph")) {
      const sourceTab = [...$("source-controls").children].find((item) => item.dataset.source === state.sourceId);
      sourceTab?.focus();
    }
  }
});

$("back-to-claim").addEventListener("click", () => {
  $("claim-list").children[state.claimIndex]?.focus();
});

$("demo").addEventListener("click", () => {
  $("file-feedback").textContent = "";
  renderReport(demo);
  $("case-title").focus();
});

$("open-report").addEventListener("click", () => $("report-file").click());
$("report-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const feedback = $("file-feedback");
  event.target.value = "";
  feedback.classList.remove("error");
  try {
    if (file.size > 5_000_000) throw new Error("Die Datei ist größer als 5 MB.");
    let data;
    try {
      data = JSON.parse(await file.text());
    } catch {
      throw new Error("Die Datei enthält kein lesbares JSON.");
    }
    renderReport(readReport(data));
    feedback.textContent = "Bericht geöffnet.";
    $("case-title").focus();
  } catch (error) {
    feedback.classList.add("error");
    feedback.textContent = error.message || "Der Bericht konnte nicht gelesen werden.";
    $("open-report").focus();
  }
});

$("urls").addEventListener("input", () => {
  $("urls").removeAttribute("aria-invalid");
  $("form-feedback").classList.remove("error");
  $("form-feedback").textContent = "Der lokale Quellenlot-Agent liest die gespeicherte Anfrage.";
});

$("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  const lines = $("urls").value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const urls = lines.map(safeUrl);
  const feedback = $("form-feedback");
  const invalid = urls.findIndex((url) => url === null);
  const unique = new Set(urls.map((url) => url?.href));
  if (!urls.length || invalid !== -1 || unique.size > 20) {
    feedback.classList.add("error");
    feedback.textContent = invalid !== -1
      ? "Link " + (invalid + 1) + " ist ungültig. Verwende eine vollständige HTTP- oder HTTPS-Adresse."
      : "Füge zwischen 1 und 20 verschiedene Links ein.";
    $("urls").setAttribute("aria-invalid", "true");
    $("urls").focus();
    return;
  }
  const [article_url, ...comparison_urls] = unique;
  const question = $("question").value.trim();
  const payload = { case_id: "artikel-" + Date.now(), article_url, comparison_urls };
  if (question) payload.question = question;
  const blob = new Blob([JSON.stringify(payload, null, 2) + "\n"], { type: "application/json" });
  const href = URL.createObjectURL(blob);
  const link = element("a");
  link.href = href;
  link.download = "case.json";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
  feedback.classList.remove("error");
  feedback.textContent = "case.json gespeichert. Lade hier anschließend den Bericht des lokalen Agenten.";
});

renderReport(demo);
