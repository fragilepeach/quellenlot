"use strict";

const relationLabels = {
  supports: "Stützt",
  contextualizes: "Liefert Kontext",
  qualifies: "Schränkt ein",
  contradicts: "Widerspricht",
  omits: "Nicht behandelt",
  not_assessable: "Nicht beurteilbar",
};

const interestLabels = {
  ownership: "Eigentümerschaft",
  funding: "Finanzierung",
  author_affiliation: "Verbindungen der Autor*innen",
  political_affiliation: "Politische Verbindungen",
};

const outcomeLabels = {
  agrees: "Zustimmung",
  challenges: "Einwand",
  unclear: "Unklar",
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
  meta: "Beispiel · Fiktiver Artikel · Deutschland 2022",
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
  claims: [
    {
      text: "Der Tankrabatt wurde im Durchschnitt vollständig weitergegeben.",
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
      quote: "Auch regional wurde der Tankrabatt überall gleichermaßen weitergegeben.",
      evidence: [
        demoEvidence("rwi", "contradicts", "regional sehr unterschiedlich ausgefallen",
          "Das RWI berichtet eine geringere Weitergabe in Regionen mit weniger Wettbewerb im Umfeld der Tankstellen."),
      ],
    },
  ],
};

const $ = (id) => document.getElementById(id);
const state = { report: demo, claimIndex: 0, sourceId: null, graph: null };
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

const agentRoles = [
  ["article", "Behauptungsanalyse", "Aussagen aus dem Artikel erfassen", "summary-heading"],
  ["research", "Quellenrecherche", "Vergleichsquellen und Verweise finden", "graph-heading"],
  ["comparison", "Quellenvergleich", "Belege vergleichen und im KI-Plenum gegenprüfen", "evidence-heading"],
  ["interests", "Interessenprüfung", "Eigentümerschaft, Finanzierung und Verbindungen prüfen", "interests-heading"],
  ["editorial", "Redaktionelle Schlussprüfung", "Befunde einordnen und offene Fragen festhalten", "editorial-result"],
];

const agentPhases = new Map([
  ["capture", "article"], ["extraction", "article"], ["provenance", "research"],
  ["comparison", "comparison"], ["interests", "interests"], ["editorial", "editorial"],
]);
const agentOutcome = {
  complete: "Ergebnis",
  partial: "Teilbericht",
  failed: "Fehlgeschlagen",
  no_claims: "Keine Aussagen",
  no_evidence: "Keine Belege",
  no_comparison_evidence: "Keine Vergleichsbelege",
  absent: "Kein Ergebnis",
};

const agentCards = agentRoles.map(([role, title, description, anchor]) => {
  const item = element("li", "agent-role");
  item.dataset.role = role;
  const heading = element("h3");
  const link = element("a", "agent-result-link", title);
  link.href = "#" + anchor;
  link.addEventListener("click", (event) => {
    const target = $(link.hash.slice(1));
    if (!target) return;
    event.preventDefault();
    const details = target.closest("details");
    if (details) details.open = true;
    target.focus({ preventScroll: true });
    target.scrollIntoView({ block: "start" });
  });
  const label = element("span", "", title);
  heading.append(label, link);
  const status = element("span", "agent-status");
  const inspect = button("Einzelbeiträge", "agent-inspect-button");
  inspect.setAttribute("aria-controls", "agent-inspector");
  inspect.addEventListener("click", () => inspectAgent(role));
  item.append(heading, element("p", "", description), status, inspect);
  $("agent-roles").append(item);
  return { item, label, link, status, anchor, role, inspect };
});


function agentAudit(report, retrieval) {
  const audit = Object.fromEntries(agentRoles.map(([role]) => [role, []]));
  const add = (role, record) => audit[role].push(record);
  for (const attempt of report?.extraction_attempts || []) {
    add("article", {
      name: attempt.agent_id || "Unbekannt", model: attempt.model || "",
      state: attempt.status, context: "Aussagenextraktion",
      detail: attempt.error_code ? "Fehlercode: " + attempt.error_code : "Modellantwort und Zitate validiert",
    });
  }
  for (const item of retrieval?.retrievals || []) {
    if (String(item.source_id).startsWith("interest-evidence-")) continue;
    add("research", {
      name: item.snapshot?.title || item.requested_url || item.source_id || "Quellenabruf",
      state: item.status, context: "Abruf · Code, kein KI-Modell",
      detail: item.detail || "",
    });
  }
  for (const query of retrieval?.discovery?.queries || []) {
    add("research", {
      name: query.query || "Suchanfrage", state: query.status,
      context: "SearXNG-Suche · Code, kein KI-Modell",
      detail: "Treffer: " + (query.result_count ?? "unbekannt"),
    });
  }
  for (const claim of report?.claims || []) {
    const review = claim.review;
    const claimLabel = claim.claim_id || "Aussage";
    for (const item of review?.analyses || []) {
      add("comparison", {
        name: item.agent_id || "Unbekannt", model: item.model || "", state: item.status,
        context: claimLabel + " · unabhängiger Quellenvergleich",
        detail: item.error_code ? "Fehlercode: " + item.error_code :
          (item.summary || "") + " · " + (item.findings?.length || 0) + " Einzelbefunde",
      });
    }
    for (const item of review?.reviews || []) {
      const results = (item.findings || []).reduce((counts, finding) => {
        counts[finding.outcome] = (counts[finding.outcome] || 0) + 1;
        return counts;
      }, {});
      add("comparison", {
        name: item.reviewer_agent_id || "Unbekannt", state: item.status,
        context: claimLabel + " · Peer-Review von " + (item.reviewed_agent_id || "unbekannt"),
        detail: item.error_code ? "Fehlercode: " + item.error_code :
          "Zustimmung " + (results.agrees || 0) + " · Einwände " + (results.challenges || 0) +
          " · unklar " + (results.unclear || 0) + (item.summary ? " · " + item.summary : ""),
      });
    }
  }
  for (const source of report?.interests?.sources || []) {
    for (const item of source.assessments || []) {
      add("interests", {
        name: item.agent_id || "Unbekannt", model: item.model || "", state: item.status,
        context: source.source?.title || source.source?.source_id || "Quelle",
        detail: item.error_code ? "Fehlercode: " + item.error_code :
          (item.findings?.length || 0) + " dokumentierte Beziehungen; " +
          (item.unknown_categories?.length || 0) + " offene Kategorien",
      });
    }
  }
  for (const item of report?.editorial?.assessments || []) {
    add("editorial", {
      name: item.agent_id || "Unbekannt", model: item.model || "", state: item.status,
      context: "Redaktionelle Schlussprüfung",
      detail: item.error_code ? "Fehlercode: " + item.error_code :
        (item.claims?.length || 0) + " geprüfte Aussagen",
    });
  }
  return audit;
}

function inspectAgent(role) {
  const item = agentRoles.find(([id]) => id === role);
  if (!item) return;
  const panel = $("agent-inspector");
  const heading = $("agent-inspector-title");
  const list = $("agent-inspector-records");
  const records = state.report?.agentAudit?.[role] || [];
  heading.textContent = item[1];
  list.replaceChildren();
  if (!records.length) {
    list.append(element("li", "agent-audit-empty",
      state.report === demo ? "Demo ohne Modellprotokolle. Öffne einen gespeicherten Prüfbericht." :
        "Keine Einzelbeiträge für diese Rolle im gespeicherten Bericht."));
  }
  for (const record of records) {
    const row = element("li", "agent-audit-row");
    const header = element("div", "agent-audit-row-heading");
    header.append(element("strong", "", record.name));
    if (record.model) header.append(element("code", "", record.model));
    const status = element("span", "agent-audit-state", record.state || "unbekannt");
    status.dataset.state = record.state || "absent";
    header.append(status);
    row.append(header, element("p", "agent-audit-context", record.context));
    if (record.detail) row.append(element("p", "", record.detail));
    list.append(row);
  }
  const context = $("agent-inspector-context");
  context.textContent = records.length + " protokollierte Einträge · " +
    "Modellurteile sind keine Wahrheitsbelege. Vollständige Zitate und Begründungen im KI-Plenum.";
  panel.hidden = false;
  panel.open = true;
  heading.focus({ preventScroll: true });
  panel.scrollIntoView({ block: "start" });
}

function agentResults(report, retrieval) {
  const claims = report?.claims || [];
  const discovery = retrieval?.discovery;
  const failedDiscovery = discovery && (discovery.queries?.some((query) => query.status === "failed") ||
    discovery.candidates?.every((candidate) => candidate.status !== "included"));
  const originalId = report?.article_source_id ?? "article";
  const captureGaps = retrieval?.retrievals.some((item) => item.source_id !== originalId &&
    !String(item.source_id).startsWith("interest-evidence-") && item.status !== "captured");
  const hasSources = report?.sources.length > 1 || retrieval?.provenance?.citations?.length;
  const claimStatus = claims.every((claim) => claim.review.status === "complete") ? "complete" :
    claims.every((claim) => claim.review.status === "failed") ? "failed" : "partial";
  return {
    article: claims.length ? "complete" : report?.status === "no_claims" ? "no_claims" :
      (report?.status === "failed" || retrieval?.status === "failed" ? "failed" : "absent"),
    research: failedDiscovery || captureGaps ? "partial" : hasSources ? "complete" : "absent",
    comparison: claims.length ? claimStatus : "absent",
    interests: report?.interests?.status,
    editorial: report?.editorial?.status,
  };
}

function renderAgentWorkflow(report, run = report?.runProgress) {
  const running = run?.status === "running";
  const phase = agentCards.findIndex(({ role }) => role === agentPhases.get(run?.stage));
  const stopped = run?.status === "interrupted" || Boolean(run?.error) ||
    (run?.status === "failed" && !report);
  const runSource = $("agent-run-source");
  const sourceLabel = (running || stopped) && run.article_url ? "Lauf für " + run.article_url : "";
  if (runSource.textContent !== sourceLabel) runSource.textContent = sourceLabel;
  runSource.hidden = !sourceLabel;
  agentCards.forEach(({ item, label, link, status, anchor, role, inspect }, index) => {
    const active = running && index === phase;
    const interrupted = stopped && index === phase;
    const outcome = report?.agentResults?.[role] || "absent";
    const example = report === demo && index < 3;
    const progress = index < phase && role !== "interests" ? "Phase beendet" :
      role === "interests" ? "Optional" : "Ausstehend";
    const value = active ? "Läuft" : interrupted ? runLabels[run.status] : running ? progress :
      example ? "Beispiel" : (Object.hasOwn(agentOutcome, outcome) ? agentOutcome[outcome] : agentOutcome.absent);
    if (status.textContent !== value) status.textContent = value;
    item.dataset.state = active ? "active" : interrupted ? "stopped" : running ? "pending" : outcome;
    if (active) item.setAttribute("aria-current", "step");
    else item.removeAttribute("aria-current");

    const target = role === "article" && report !== demo && !report?.generatedSummary ?
      $("claims-heading") : $(anchor);
    const resultTarget = target && !target.closest("[hidden]") ? target :
      role === "research" && !$("retrieval-issues").hidden ? $("retrieval-issues").querySelector("summary") : null;
    link.hidden = !(example || outcome !== "absent") || running || !resultTarget;
    label.hidden = !link.hidden;
    if (!link.hidden) link.href = "#" + resultTarget.id;
    inspect.disabled = running || stopped;
  });
  if (running || stopped) $("agent-inspector").hidden = true;
}

function renderReport(report) {
  state.report = report;
  $("agent-inspector").hidden = true;
  window.quellenlotTrends.setPublications(report.timelineSources || []);
  state.claimIndex = 0;
  $("selection-status").textContent = "";
  $("case-meta").textContent = report.meta;
  $("case-title").textContent = report.title;
  $("case-question").textContent = report.question || "";
  $("empty-report").textContent = report.empty || "";
  $("empty-report").hidden = !report.empty;
  $("retrieval-issues-list").replaceChildren(...(report.retrievalIssues || []).map((record) =>
    element("li", "", [record.requested_url, record.detail].filter(Boolean).join(" · "))
  ));
  $("retrieval-issues").hidden = !report.retrievalIssues?.length;
  $("retrieval-issues").open = Boolean(report.empty && report.retrievalIssues?.length);
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
  $("summary-heading").textContent = report.generatedSummary ? "KI-Zusammenfassung" : "Artikelzusammenfassung";
  $("claim-count").textContent = String(report.claims.length);
  $("claim-list").replaceChildren(...report.claims.map((claim, index) => {
    const control = button("", "claim-button");
    control.dataset.claim = String(index);
    control.setAttribute("aria-controls", "evidence-panel");
    const number = element("span", "claim-id", String(index + 1).padStart(2, "0"));
    number.setAttribute("aria-hidden", "true");
    const text = element("span");
    text.append(element("span", "claim-label", claim.text));
    if (claim.status) text.append(element("span", "claim-status", claim.status));
    control.append(number, text);
    return control;
  }));
  if (report.claims.length) selectClaim(0);
  else {
    renderGraph();
    renderClaimStudies();
  }
  renderSourceSimilarities(report.sourceSimilarities || []);
  renderPrivateReview(report);
  renderAgentWorkflow(report);
}

function renderSourceSimilarities(pairs) {
  const panel = $("source-similarity");
  panel.hidden = !pairs.length;
  panel.open = false;
  const number = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 });
  $("source-similarity-rows").replaceChildren(...pairs.map(({ first, second, score }) => {
    const row = element("tr");
    for (const source of [first, second]) {
      const cell = element("td");
      const title = source.name || source.id;
      cell.append(sourceLink(source, null, title) || document.createTextNode(title));
      if (source.complete === false) cell.append(element("small", "", "Vollständigkeit ungeprüft"));
      row.append(cell);
    }
    row.append(element("td", "", score === null ? "Zu wenig Text" : number.format(score) + " %"));
    return row;
  }));
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
  renderClaimDiff(claim);
  renderClaimStudies();
  renderPlenum(claim);
  renderGraph(claim, number);
  selectSource(claim.evidence.find(({ source }) => !source.original)?.source.id || claim.evidence[0]?.source.id);
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

function relationBadge(value) {
  const relation = element("span", "relation", relationLabels[value] || "Ohne Einordnung");
  relation.dataset.kind = value;
  return relation;
}

function byPublication(left, right) {
  const day = (source) => /^\d{4}-\d{2}-\d{2}(?=T|$)/.exec(source.published)?.[0] || "9999-99-99";
  return day(left).localeCompare(day(right));
}

function evidenceLink(excerpt) {
  const link = element("a", "diff-reference", excerpt.label);
  link.href = "#" + excerpt.anchor;
  return link;
}

function renderDiffSource({ source, judgments }) {
  const row = element("li", "diff-source");
  const title = sourceButton(source, "source-button diff-source-title");
  const dates = element("div", "diff-dates");
  dates.append(element("span", "", source.published ? "Veröffentlicht " + formatDate(source.published) : "Veröffentlichung unbekannt"));
  if (source.updated) dates.append(element("span", "", "Aktualisiert " + formatDate(source.updated)));
  const findings = element("div", "diff-tags");
  for (const relation of new Set(judgments.map((judgment) => judgment.relation))) {
    findings.append(relationBadge(relation));
  }
  if (!judgments.length) findings.append(element("span", "diff-note", "Keine Modellbeurteilung"));
  row.append(title, dates, findings);
  if (source.original || source.complete === false) {
    const labels = [source.original && "Eingabeartikel", source.complete === false && "Nur Auszug"].filter(Boolean);
    row.append(element("p", "diff-note", labels.join(" · ")));
  }
  const references = new Set(judgments.flatMap((judgment) => judgment.excerpts || []));
  if (references.size) {
    const links = element("div", "diff-tags");
    links.append(...Array.from(references, evidenceLink));
    row.append(links);
  } else if (judgments[0]?.passage) {
    row.append(element("blockquote", "diff-quote", judgments[0].passage));
  }
  return row;
}

function renderDiffExcerpt(excerpt) {
  const row = element("div", "diff-excerpt");
  if (excerpt.anchor) {
    row.id = excerpt.anchor;
    row.tabIndex = -1;
  }
  row.append(element("h5", "", excerpt.label + (excerpt.citations.length > 1 ? " · Gemeinsamer Wortlaut" : "")));
  row.append(element("blockquote", "diff-quote", excerpt.text));
  const occurrences = element("ul", "diff-occurrences");
  for (const { source, locators } of excerpt.citations) {
    const item = element("li");
    item.append(sourceLink(source, excerpt.text, sourceName(source)) || document.createTextNode(sourceName(source)));
    if (locators.length) item.append(document.createTextNode(" · " + locators.join(" · ")));
    occurrences.append(item);
  }
  row.append(occurrences);
  return row;
}

function wordingDiff(before, after) {
  const tokens = (text) => text.match(/[\p{L}\p{M}\p{N}_]+|\s+|[^\s]/gu) || [];
  const left = tokens(before);
  const right = tokens(after);
  if (left.length > 600 || right.length > 600) return [before, after];
  const width = right.length + 1;
  const common = new Uint16Array((left.length + 1) * width);
  for (let i = left.length - 1; i >= 0; i -= 1) {
    for (let j = right.length - 1; j >= 0; j -= 1) {
      common[i * width + j] = left[i] === right[j]
        ? common[(i + 1) * width + j + 1] + 1
        : Math.max(common[(i + 1) * width + j], common[i * width + j + 1]);
    }
  }
  const render = (parts, tag) => {
    const fragment = document.createDocumentFragment();
    for (const { text, changed } of parts) {
      const last = fragment.lastChild;
      if (changed && last?.nodeName === tag.toUpperCase()) last.append(text);
      else fragment.append(changed ? element(tag, "", text) : document.createTextNode(text));
    }
    return fragment;
  };
  const removed = [];
  const added = [];
  let i = 0;
  let j = 0;
  while (i < left.length || j < right.length) {
    if (i < left.length && left[i] === right[j]) {
      removed.push({ text: left[i], changed: false });
      added.push({ text: right[j], changed: false });
      i += 1;
      j += 1;
    } else if (j === right.length || (i < left.length && common[(i + 1) * width + j] >= common[i * width + j + 1])) {
      removed.push({ text: left[i], changed: true });
      i += 1;
    } else {
      added.push({ text: right[j], changed: true });
      j += 1;
    }
  }
  return [render(removed, "del"), render(added, "ins")];
}

function renderWordingMatch({ passages, similarity }, excerpts) {
  const [first, second] = [...passages].sort((a, b) => byPublication(a.source, b.source));
  const exact = first.text === second.text;
  const details = element("details", "diff-match");
  const names = [first, second].map(({ source }) => sourceName(source)).join(" · ");
  const score = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }).format(similarity);
  details.append(element("summary", "", names + " · " + score + " / 100"));
  if (exact) {
    const cited = excerpts.find(({ text, citations }) => text === first.text &&
      passages.every(({ source }) => citations.some((citation) => citation.source === source)));
    details.append(cited ? evidenceLink(cited) : element("blockquote", "diff-quote", first.text));
  } else {
    details.append(element("p", "diff-note diff-legend", "− Durchgestrichen im ersten Ausschnitt · + Unterstrichen im zweiten Ausschnitt"));
  }
  const sides = element("div", "diff-pair");
  const diff = exact ? [] : wordingDiff(first.text, second.text);
  for (const [index, { source, text }] of [first, second].entries()) {
    const side = element("div", "diff-side");
    const prefix = exact ? "" : index === 0 ? "− " : "+ ";
    side.append(element("h6", "", prefix + sourceName(source)));
    if (!exact) {
      const quote = element("blockquote", "diff-quote");
      quote.append(diff[index]);
      side.append(quote);
    }
    const link = sourceLink(source, text);
    if (link) side.append(link);
    sides.append(side);
  }
  details.append(sides);
  return details;
}

function renderClaimDiff(claim) {
  $("claim-diff").hidden = !claim.evidence.length;
  const rows = [...claim.evidence].sort((a, b) => byPublication(a.source, b.source));
  $("diff-sources").replaceChildren(...rows.map(renderDiffSource));
  const { excerpts, matches, limited } = claim.diff || { excerpts: [], matches: [] };
  $("diff-evidence").replaceChildren(...excerpts.map(renderDiffExcerpt));
  const wording = $("diff-wording");
  wording.replaceChildren();
  if (!matches.length && !limited) return;
  wording.append(element("h5", "", "Mögliche Textübernahme"));
  if (matches.length) {
    wording.append(element("p", "diff-note", "RapidFuzz misst Textähnlichkeit. Die Herkunft muss separat belegt werden."));
    wording.append(...matches.map((match) => renderWordingMatch(match, excerpts)));
  }
  if (limited) wording.append(element("p", "diff-note", "Die automatische Suche nach ähnlichen Passagen war begrenzt."));
}

function renderPlenum(claim) {
  const panel = $("claim-plenum");
  const content = $("plenum-content");
  panel.hidden = !claim.plenum;
  panel.open = false;
  content.replaceChildren();
  if (!claim.plenum) return;

  const { analyses, reviews, dissent, sources } = claim.plenum;
  const analysisByAgent = new Map(analyses.map((record) => [record.agent_id, record]));
  const sourceByVersion = new Map(sources.map((source) => [
    JSON.stringify([source.source_id, source.version_id]), source,
  ]));
  $("plenum-count").textContent = [
    analyses.length + (analyses.length === 1 ? " Analyse" : " Analysen"),
    reviews.length + (reviews.length === 1 ? " Gegenprüfung" : " Gegenprüfungen"),
  ].join(" · ");
  if (dissent.length) {
    const unresolved = element("section", "plenum-dissent");
    unresolved.append(element("h5", "", "Offene Einwände"), reviewList(dissent));
    content.append(unresolved);
  }

  content.append(element("h5", "", "Eigenständige Analysen"));
  if (!analyses.length) content.append(element("p", "", "Keine Analysen im Bericht."));
  for (const analysis of analyses) {
    const entry = element("div", "plenum-entry");
    entry.append(element("h6", "", [analysis.agent_id, analysis.model].filter(Boolean).join(" · ")));
    if (analysis.status === "failed") entry.append(element("p", "", "Analyse fehlgeschlagen."));
    if (analysis.summary) entry.append(element("p", "", analysis.summary));
    if (Array.isArray(analysis.open_questions) && analysis.open_questions.length) {
      entry.append(reviewList(analysis.open_questions));
    }
    content.append(entry);
  }

  content.append(element("h5", "", "Gegenprüfungen"));
  if (!reviews.length) content.append(element("p", "", "Keine Gegenprüfungen im Bericht."));
  for (const review of reviews) {
    const entry = element("section", "plenum-entry");
    entry.append(element("h6", "", review.reviewer_agent_id + " prüft " + review.reviewed_agent_id));
    if (review.summary) entry.append(element("p", "", review.summary));
    if (review.status === "failed") entry.append(element("p", "", "Gegenprüfung fehlgeschlagen."));
    const target = analysisByAgent.get(review.reviewed_agent_id);
    if (review.status === "succeeded" && Array.isArray(review.findings)) {
      for (const result of review.findings) {
        const finding = target?.findings?.[result.finding_index];
        if (!finding) {
          entry.append(element("p", "", "Der geprüfte Befund fehlt im Bericht."));
          continue;
        }
        const source = sourceByVersion.get(JSON.stringify([finding.source_id, finding.version_id]));
        const item = element("div", "plenum-finding");
        const heading = element("div", "source-caption");
        heading.append(element("strong", "", source?.title || finding.source_id),
          relationBadge(finding.relation));
        item.append(heading);
        if (finding.reasoning) item.append(element("p", "", finding.reasoning));
        const outcome = element("strong", "plenum-outcome", outcomeLabels[result.outcome] || "Unklar");
        outcome.dataset.outcome = result.outcome;
        item.append(outcome);
        if (result.reasoning) item.append(element("p", "", result.reasoning));
        const quote = result.quote;
        if (quote?.verified === true && source && quote.source_id === source.source_id &&
            quote.version_id === source.version_id && typeof quote.text === "string" && quote.text.trim()) {
          item.append(element("blockquote", "diff-quote", quote.text));
          const link = sourceLink(source, quote.text, "Beleg öffnen");
          if (link) item.append(link);
        }
        entry.append(item);
      }
    }
    content.append(entry);
  }
}

function renderJudgment(judgment) {
  const container = element("div", "judgment");
  const heading = element("div", "source-caption");
  if (judgment.agent) heading.append(element("span", "judgment-meta", "Modell " + judgment.agent));
  heading.append(relationBadge(judgment.relation));
  container.append(heading);
  if (judgment.passage) {
    container.append(element("blockquote", "", "„" + judgment.passage + "“"));
  } else if (judgment.excerpts?.length) {
    const links = element("div", "diff-tags");
    links.append(...judgment.excerpts.map(evidenceLink));
    container.append(links);
  } else {
    container.append(element("p", "source-reason", "Kein exakt abgeglichener Beleg im Bericht."));
  }
  if (judgment.reason) container.append(element("p", "source-reason", judgment.reason));
  return container;
}

function selectSource(id) {
  const evidence = selectedClaim().evidence.find(({ source }) => source.id === id);
  state.sourceId = evidence?.source.id;
  updateSelection($("diff-sources"), "source", state.sourceId);
  state.graph?.select(state.sourceId);
  $("graph-selection").hidden = true;

  const detail = $("source-detail");
  detail.replaceChildren();
  if (!evidence) {
    detail.append(element("p", "source-reason", "Zu dieser Aussage liegen keine Quellenbeurteilungen vor."));
    return;
  }
  const { source, judgments } = evidence;
  detail.append(element("h4", "", "Beurteilungen zu " + sourceName(source)));
  if (source.type) detail.append(element("p", "source-type", source.type));
  detail.append(...judgments.map(renderJudgment));
  if (!judgments.length) detail.append(element("p", "source-reason", "Für diese Quelle liegt keine Modellbeurteilung vor."));
  detail.append(sourceMetadata(source));
  const link = sourceLink(source, judgments.find((judgment) => judgment.passage)?.passage);
  if (link) detail.append(link);
}

function renderGraph(claim, number) {
  state.graph?.dispose();
  state.graph = null;
  $("graph").replaceChildren();
  $("graph-provenance").replaceChildren();
  $("graph-selection").hidden = true;

  const provenance = state.report.provenance;
  const sources = new Map();
  const citations = new Map();
  const edges = [];
  const claimId = Symbol("claim");
  function addSource(source, kind, relation, note) {
    if (!sources.has(source.id)) {
      sources.set(source.id, { id: source.id, label: sourceName(source), source, kind, relation,
        note: kind === "source" ? sourceAvailability(source) : note });
    }
  }
  function addCitation(from, to) {
    if (!sources.has(from) || !sources.has(to) || from === to) return;
    if (!citations.has(from)) citations.set(from, new Set());
    const linked = citations.get(from);
    if (linked.has(to)) return;
    linked.add(to);
    edges.push({ from, to, kind: "citation" });
  }
  for (const { source, judgments } of claim?.evidence || []) {
    const labels = new Set(judgments.map(({ relation }) => relation));
    const relation = labels.size === 1 ? judgments[0].relation : null;
    const note = labels.size > 1 ? "Gemischte Befunde" : labels.size === 0 ? "Keine Beurteilung" : null;
    addSource(source, "evidence", relation, note);
    edges.push({ from: claimId, to: source.id, kind: relation || "assessment" });
  }
  for (const { target, incoming } of provenance?.groups || []) {
    addSource(target, "source");
    for (const { source } of incoming) {
      addSource(source, "source");
      addCitation(source.id, target.id);
    }
  }
  for (const { source } of claim?.evidence || []) {
    for (const target of source.cites || []) addCitation(source.id, target);
  }

  $("graph-card").hidden = !sources.size && !provenance?.limited;
  if (sources.size) {
    const nodes = [...sources.values()];
    if (claim) nodes.unshift({ id: claimId, kind: "claim", label: "Aussage " + number });
    state.graph = createEvidenceGraph(nodes, edges, selectGraphNode);
    $("graph").append(state.graph.canvas);
    if (citations.size) $("graph").append(element("p", "graph-legend", "→ Verweist auf"));
  }
  renderSourceProvenance(provenance, $("graph-provenance"));
}

function sourceAvailability(source) {
  if (source.status === "partial") return "Teilweise erfasst";
  if (source.status === "failed") return "Nicht abrufbar";
  return "";
}

function selectGraphNode(node) {
  const details = $("graph-selection");
  const title = element("strong", "", node.label);
  details.replaceChildren(title);

  if (node.kind === "claim") {
    $("original-quote").closest("details").open = true;
    const link = element("a", "", "Wortlaut ansehen");
    link.href = "#original-quote";
    details.append(link);
  } else if (node.kind === "evidence") {
    selectSource(node.id);
    const link = element("a", "", "Beurteilungen ansehen");
    link.href = "#source-detail";
    details.append(link);
  } else {
    const link = sourceLink(node.source, null);
    if (link) details.append(link);
    const status = sourceAvailability(node.source);
    if (status) details.append(element("span", "graph-node-note", status));
  }
  details.hidden = false;
  state.graph.select(node.id);
  $("selection-status").textContent = node.label + " ausgewählt.";
}

function renderSourceProvenance(provenance, container) {
  if (!provenance) return;
  const { groups, limited } = provenance;
  if (!groups.length && !limited) return;
  const section = element("details", "source-provenance");
  section.append(element("summary", "", "Verweise in den Artikeln"));
  const targets = element("ul", "provenance-targets");
  for (const { target, incoming } of groups) {
    const item = element("li");
    item.append(sourceLink(target, null, target.name) || element("strong", "", target.name));
    const count = new Set(incoming.map(({ source }) => source.id)).size;
    if (count > 1) item.append(element("p", "graph-note", `${count} Quellen verlinken dieses Ziel.`));
    const status = sourceAvailability(target);
    if (status) {
      item.append(element("p", "graph-note", status + (target.detail ? ` · ${target.detail}` : "")));
    }
    if (target.captured) item.append(sourceMetadata(target));
    const links = element("ul", "provenance-links");
    for (const { source, anchor } of incoming) {
      const row = element("li");
      const label = `${source.name} · „${anchor}“`;
      row.append(sourceLink(source, anchor, label) || element("span", "", label));
      links.append(row);
    }
    item.append(links);
    targets.append(item);
  }
  section.append(targets);
  if (limited) section.append(element("p", "graph-note", "Die Verfolgung der Links war begrenzt."));
  container.append(section);
}

function readSourceProvenance(data) {
  if (!Array.isArray(data.provenance?.citations)) return null;
  const retrievals = new Map(data.retrievals.map((item) => [item.source_id, item]));
  const groups = new Map();
  const asSource = (item) => ({
    id: item.source_id,
    name: item.snapshot?.title || safeUrl(item.requested_url)?.hostname || item.source_id,
    url: item.snapshot?.url || item.requested_url,
    published: item.snapshot?.published_at?.value,
    updated: item.snapshot?.updated_at?.value,
    captured: item.snapshot?.captured_at,
    version: item.snapshot?.version_id,
    status: item.status,
    detail: item.detail,
  });
  for (const citation of data.provenance.citations) {
    const from = retrievals.get(citation?.citing_source_id);
    const to = retrievals.get(citation?.cited_source_id);
    const anchor = citation?.link?.anchor;
    if (!from || !to || from === to || !anchor || typeof anchor !== "string" ||
        !from.snapshot || from.snapshot.version_id !== citation.citing_version_id ||
        typeof from.snapshot.text !== "string" || !from.snapshot.text.includes(anchor)) continue;
    if (!groups.has(to.source_id)) groups.set(to.source_id, { target: asSource(to), incoming: [] });
    groups.get(to.source_id).incoming.push({ source: asSource(from), anchor });
  }
  return { groups: [...groups.values()], limited: data.provenance.limited === true };
}

function normalizedSource(source, originalId) {
  return {
    id: source.source_id,
    name: source.title,
    url: source.url,
    published: source.published_at?.value,
    updated: source.updated_at?.value,
    captured: source.captured_at,
    version: source.version_id,
    complete: source.text_is_complete,
    original: source.source_id === originalId,
  };
}

function normalizedSourceSimilarities(report) {
  const pairs = report.shared_wording?.source_similarities;
  if (!Array.isArray(pairs)) return [];
  const sources = new Map(report.sources.filter((source) => source?.source_id && source.version_id)
    .map((source) => [source.source_id, normalizedSource(source, report.article_source_id)]));
  const resolve = (reference) => {
    const source = sources.get(reference?.source_id);
    return source?.version === reference?.version_id ? source : null;
  };
  return pairs.flatMap((pair) => {
    const first = resolve(pair?.first);
    const second = resolve(pair?.second);
    const score = pair?.score;
    if (!first || !second || first === second ||
      (score !== null && (!Number.isFinite(score) || score < 0 || score > 100))) return [];
    return [{ first, second, score }];
  }).sort((left, right) => (right.score ?? -1) - (left.score ?? -1));
}

function normalizedEvidence(comparisons, originalId) {
  return comparisons
    .filter(({ source, judgments }) => source?.source_id !== originalId && judgments?.length)
    .map(({ source, judgments }) => ({
      source: normalizedSource(source, originalId),
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

function normalizedDiff(diff, wording, originalId) {
  if (!Array.isArray(diff?.sources) || !diff.sources.length || !Array.isArray(diff.evidence)) return null;
  const rows = diff.sources.filter(({ source, judgments }) => typeof source?.source_id === "string" &&
    typeof source.version_id === "string" && Array.isArray(judgments));
  if (!rows.length) return null;
  const sources = new Map(rows.map(({ source }) => [source.source_id, normalizedSource(source, originalId)]));
  const resolveSource = ({ source_id, version_id }) => {
    const source = sources.get(source_id);
    return source?.version === version_id ? source : null;
  };
  const excerpts = new Map();
  const matchIndexes = new Set();
  for (const item of diff.evidence) {
    if (typeof item?.evidence_id !== "string" || excerpts.has(item.evidence_id) ||
      typeof item.text !== "string" || !item.text.trim() || !Array.isArray(item.citations)) continue;
    const citations = [];
    for (const citation of item.citations) {
      const source = resolveSource(citation);
      if (!source) continue;
      const locators = (citation.locators || []).filter((locator) => typeof locator === "string" && locator);
      citations.push({ source, locators });
      for (const index of citation.shared_wording_match_indexes || []) {
        const match = wording?.matches?.[index];
        if ([match?.first, match?.second].some((passage) => passage && resolveSource(passage) === source)) {
          matchIndexes.add(index);
        }
      }
    }
    if (!citations.length) continue;
    const number = excerpts.size + 1;
    excerpts.set(item.evidence_id, { id: item.evidence_id, label: "Zitat " + number, anchor: "claim-quote-" + number, text: item.text, citations });
  }
  const matches = [];
  for (const index of matchIndexes) {
    const { first, second, similarity } = wording.matches[index];
    if (!first || !second || first.source_id === second.source_id || !Number.isFinite(similarity)) continue;
    const passages = [first, second].map((passage) => ({ source: resolveSource(passage), text: passage.text }));
    if (passages.every(({ source, text }) => source && typeof text === "string" && text.trim())) {
      matches.push({ passages, similarity });
    }
  }
  const evidence = rows.map(({ source, judgments }) => ({
    source: sources.get(source.source_id),
    judgments: judgments.map((judgment) => ({
      relation: judgment.relation,
      agent: judgment.agent_id,
      reason: judgment.reasoning,
      excerpts: (judgment.evidence_ids || []).map((id) => excerpts.get(id))
        .filter((excerpt) => excerpt?.citations.some((citation) => citation.source.id === source.source_id)),
    })),
  }));
  return { evidence, snippets: { excerpts: [...excerpts.values()], matches, limited: wording?.limited === true } };
}

function reviewList(items) {
  const list = element("ul");
  for (const item of items) list.append(element("li", "", item));
  return list;
}

function renderInterests(interests) {
  const details = element("details");
  const summary = element("summary", "", "Eigentümerschaft, Finanzierung und Verbindungen");
  summary.id = "interests-heading";
  details.append(summary);
  if (!interests?.sources?.length) {
    details.append(element("p", "", "Keine Interessenprüfung mit Quellen im Bericht."));
    return details;
  }

  for (const entry of interests.sources) {
    const source = entry.source;
    details.append(element("h4", "", source.title || source.source_id));
    if (source.publisher) details.append(element("p", "", "Herausgeber: " + source.publisher));
    if (source.authors?.length) {
      details.append(element("p", "", "Autor*innen: " + source.authors.join(", ")));
    }
    const unknown = (entry.unresolved_categories || []).map((category) => interestLabels[category] || category);
    if (unknown.length) details.append(element("p", "", "Offen: " + unknown.join(", ")));
    for (const assessment of entry.assessments || []) {
      if (assessment.status === "failed") {
        details.append(element("p", "", assessment.agent_id + " · Interessenprüfung fehlgeschlagen"));
      }
      for (const finding of assessment.findings || []) {
        const quote = finding.evidence;
        const snapshot = (entry.evidence_sources || []).find((item) =>
          item.source_id === quote?.source_id && item.version_id === quote?.version_id
        );
        const category = interestLabels[finding.category] || finding.category;
        details.append(element("p", "", assessment.agent_id + " · " + category + " · " + finding.relationship));
        if (snapshot && quote.verified === true) {
          details.append(element("blockquote", "", quote.text));
          const link = sourceLink(snapshot, quote.text, "Beleg der Verbindung öffnen");
          if (link) details.append(link);
        }
      }
    }
    const gaps = (entry.retrievals || []).filter((item) => item.status !== "captured");
    if (gaps.length) details.append(reviewList(gaps.map((item) => "Abruflücke: " + item.requested_url)));
  }
  return details;
}

function renderFindingEvidence(finding, excerpts) {
  const evidenceIds = new Set(Array.isArray(finding.evidence_ids) ? finding.evidence_ids : []);
  if (!evidenceIds.size) return null;
  const details = element("details", "editorial-evidence");
  details.append(element("summary", "", "Belege zum Befund"));
  for (const excerpt of excerpts) {
    if (!evidenceIds.has(excerpt.id)) continue;
    const citations = excerpt.citations.filter(({ source }) => source.id === finding.source_id);
    if (!citations.length) continue;
    details.append(renderDiffExcerpt({ ...excerpt, citations, anchor: null }));
    evidenceIds.delete(excerpt.id);
  }
  if (evidenceIds.size) {
    details.append(element("p", "diff-note", "Zugewiesene Belege fehlen für diese Quelle im Bericht."));
  }
  return details;
}

function renderEditorial(editorial, claims) {
  const section = element("div");
  const notes = editorial?.assessments || [];
  const succeeded = notes.filter((note) => note.status === "succeeded").length;
  const result = element("p", "", "Abgeschlossene Schlussprüfungen: " + succeeded + " von " + notes.length);
  result.id = "editorial-result";
  result.tabIndex = -1;
  section.append(result);
  const failed = notes.filter((note) => note.status === "failed");
  if (failed.length) {
    section.append(reviewList(failed.map((note) => note.agent_id + " · Schlussprüfung unvollständig")));
  }
  if (editorial?.retrieval_gaps?.length) {
    section.append(reviewList(editorial.retrieval_gaps.map((gap) => "Abruflücke: " + gap.requested_url)));
  }
  if (editorial?.incomplete_source_ids?.length) {
    section.append(element("p", "", "Unvollständige Quellen: " + editorial.incomplete_source_ids.join(", ")));
  }
  if (editorial?.discovery_incomplete) {
    section.append(element("p", "", "Die Vergleichsquellensuche war unvollständig."));
  }
  for (const coverage of editorial?.claims || []) {
    const index = claims.findIndex((item) => item.id === coverage.claim_id);
    const claim = claims[index];
    const details = element("details");
    details.append(element("summary", "", claim?.text || coverage.claim_id));
    if (claim) {
      const inspect = button("Quellenvergleich zur Aussage öffnen", "quiet-button");
      inspect.addEventListener("click", () => {
        selectClaim(index);
        $("evidence-heading").focus();
      });
      details.append(inspect);
    }
    if (coverage.comparison_sources_without_quotes?.length) {
      details.append(element("p", "", "Vergleichsquellen ohne bestätigtes Zitat: " +
        coverage.comparison_sources_without_quotes.join(", ")));
    }
    const assigned = coverage.assigned_findings || [];
    details.append(element("p", "", assigned.length + " Befunde zugewiesen, " +
      (coverage.unassigned_finding_count || 0) + " weitere Befunde im Quellenvergleich."));
    const dissent = coverage.unresolved_dissent?.length ? coverage.unresolved_dissent : claim?.dissent;
    if (dissent?.length) {
      details.append(element("h4", "", "Offene Einwände aus der Quellenprüfung"));
      details.append(reviewList(dissent));
    }
    const unresolved = new Set(coverage.unresolved_finding_ids || []);
    for (const finding of assigned) {
      const relation = relationLabels[finding.relation] || finding.relation;
      details.append(element("h4", "", finding.finding_id + " · " + finding.source_id + " · " + relation));
      if (finding.reasoning) details.append(element("p", "", finding.reasoning));
      if (unresolved.has(finding.finding_id)) {
        details.append(element("p", "", "In der Schlussprüfung umstritten oder unklar."));
      }
      const evidence = renderFindingEvidence(finding, claim?.diff?.excerpts || []);
      if (evidence) details.append(evidence);
      const outcomes = [];
      for (const note of notes) {
        const result = note.claims?.find((item) => item.claim_id === coverage.claim_id)
          ?.findings?.find((item) => item.finding_id === finding.finding_id);
        if (result) {
          outcomes.push(note.agent_id + " · " + (outcomeLabels[result.outcome] || result.outcome) +
            " · " + result.reasoning);
        }
      }
      if (outcomes.length) details.append(reviewList(outcomes));
    }
    for (const note of notes) {
      const result = note.claims?.find((item) => item.claim_id === coverage.claim_id);
      if (result) {
        details.append(element("p", "", note.agent_id + " · " + result.assessment));
        if (result.next_check) details.append(element("p", "", "Nächste Prüfung: " + result.next_check));
      }
    }
    section.append(details);
  }
  return section;
}

function exactlyCovers(ids, assigned) {
  return ids.length === assigned.size &&
    new Set(ids).size === ids.length &&
    ids.every((id) => assigned.has(id));
}

function canPrepareRelease(editorial) {
  if (!["complete", "partial"].includes(editorial?.status)) return false;
  const assigned = new Map();
  for (const claim of editorial.claims || []) {
    if (!claim.assigned_findings?.length) continue;
    const ids = claim.assigned_findings.map((finding) => finding.finding_id);
    if (assigned.has(claim.claim_id) || new Set(ids).size !== ids.length) return false;
    assigned.set(claim.claim_id, new Set(ids));
  }
  const reviewers = (editorial.assessments || []).filter((item) => item.status === "succeeded");
  const claimIds = new Set(assigned.keys());
  return assigned.size > 0 && reviewers.length > 0 && reviewers.every((item) =>
    Array.isArray(item.claims) && exactlyCovers(item.claims.map((claim) => claim.claim_id), claimIds) &&
    item.claims.every((claim) => Array.isArray(claim.findings) &&
      exactlyCovers(claim.findings.map((finding) => finding.finding_id), assigned.get(claim.claim_id)))
  );
}

function renderPrivateReview(report) {
  if ($("release-preview").open) $("release-preview").close();
  const panel = $("private-review");
  const form = $("release-form");
  form.reset();
  const review = report.privateReview;
  panel.hidden = !review;
  form.hidden = true;
  $("save-release").disabled = true;
  setReleaseStatus("");
  const managed = Boolean(review?.runId);
  $("save-release").textContent = managed ? "Entwurf speichern" : "Freigabeentwurf speichern";
  $("release-check-title").textContent = managed ? "Vor der Freigabe prüfen" : "Vor dem Export prüfen";
  $("approve-release").hidden = !managed;
  $("export-release").hidden = !managed;
  $("preview-release").hidden = !managed;
  const content = $("private-review-content");
  content.replaceChildren();
  if (!review) return;
  content.append(renderInterests(review.interests), renderEditorial(review.editorial, report.claims));
  form.hidden = !canPrepareRelease(review.editorial) || !review.digest || review.readOnly;
  if (form.hidden) {
    content.append(element("p", "", "Für einen Freigabeentwurf ist ein abgeschlossener, auswertbarer Prüfbericht erforderlich."));
    return;
  }
  $("release-text").value = review.draft?.text || "";
  if (review.draft?.approved_at) {
    $("release-sources-checked").checked = true;
    $("release-findings-checked").checked = true;
  }
  setReleaseStatus(review.draftError || draftLabel(review.draft), Boolean(review.draftError));
  updateReleaseControls();
}

function normalizedSummary(items, claims) {
  if (!Array.isArray(items) || !items.length || items.length > 3) return [];
  const summary = [];
  const used = new Set();
  for (const item of items) {
    if (typeof item?.text !== "string" || !item.text.trim() || typeof item.claim_id !== "string") {
      return [];
    }
    const claim = claims.findIndex(({ id, quote }) => id === item.claim_id && quote);
    if (claim < 0 || used.has(claim)) return [];
    if (summary.length) summary.push(" ");
    summary.push({ claim, text: item.text.trim() });
    used.add(claim);
  }
  return summary;
}

function readReport(data) {
  const retrievalReport = Array.isArray(data?.retrievals);
  const report = retrievalReport ? data.review : data;
  const retrievalIssues = retrievalReport
    ? data.retrievals.filter((item) => item.status === "failed" || item.status === "partial")
    : [];
  if (retrievalReport && !report && ["failed", "partial"].includes(data.status)) {
    const failed = data.status === "failed";
    const original = data.retrievals.find((item) => item.source_id === "article");
    return {
      meta: failed ? "Importierter Bericht · Abruf fehlgeschlagen" : "Importierter Bericht · Teilbericht",
      title: original?.snapshot?.title || "Artikel konnte nicht gelesen werden",
      question: data.question,
      summary: [],
      claims: [],
      retrievalIssues,
      timelineSources: data.retrievals.flatMap((item) => item.snapshot ? [item.snapshot] : []),
      provenance: readSourceProvenance(data),
      agentResults: agentResults(null, data),
      agentAudit: agentAudit(null, data),
      empty: failed
        ? "Der Bericht enthält keinen auswertbaren Artikel."
        : "Die Quellen wurden erfasst. Für diesen Lauf liegt noch kein Aussagenvergleich vor.",
    };
  }
  if (typeof report?.article_source_id !== "string" || !Array.isArray(report?.sources) || !Array.isArray(report?.claims)) {
    throw new Error("Kein Quellenlot-Artikelbericht. Wähle die JSON-Ausgabe eines Artikel- oder URL-Laufs.");
  }
  const article = report.sources.find((source) => source.source_id === report.article_source_id);
  const claims = report.claims.map((claim) => {
    const diff = normalizedDiff(claim.review?.source_diff, report.shared_wording, report.article_source_id);
    if (typeof claim.review?.claim !== "string" || (!diff && !Array.isArray(claim.source_comparison))) {
      throw new Error("Der Bericht enthält eine unvollständige Aussage.");
    }
    const quote = claim.article_quote;
    return {
      id: claim.claim_id,
      text: claim.review.claim,
      dissent: claim.review.unresolved_dissent,
      plenum: Array.isArray(claim.review.analyses) || Array.isArray(claim.review.reviews) ? {
        analyses: Array.isArray(claim.review.analyses) ? claim.review.analyses : [],
        reviews: Array.isArray(claim.review.reviews) ? claim.review.reviews : [],
        dissent: Array.isArray(claim.review.unresolved_dissent) ? claim.review.unresolved_dissent : [],
        sources: Array.isArray(claim.review.sources) ? claim.review.sources : report.sources,
      } : null,
      status: claim.review.status === "complete" ? "" : "Modellprüfung unvollständig",
      quote: quote?.verified === true && typeof quote.text === "string" && article &&
        quote.source_id === article.source_id &&
        quote.version_id === article.version_id ? quote.text : null,
      evidence: diff?.evidence ?? normalizedEvidence(claim.source_comparison, report.article_source_id),
      diff: diff?.snippets,
    };
  });
  const failed = data.status === "failed" || report.status === "failed";
  const partial = data.status === "partial" || report.status === "partial";
  const runStatus = failed ? " · Analyse fehlgeschlagen" : partial ? " · Teilbericht" : "";
  const summary = normalizedSummary(report.article_summary, claims);
  const empty = failed
    ? "Die Analyse konnte keine Aussagen ermitteln, weil die Extraktion fehlgeschlagen ist."
    : "Der Bericht enthält keine prüfbaren Aussagen.";
  return {
    meta: "Importierter Bericht" + runStatus,
    title: article?.title || "Artikelprüfung",
    question: report.question,
    article,
    privateReview: report.interests || report.editorial ? {
      interests: report.interests,
      editorial: report.editorial,
    } : null,
    summary: summary.length
      ? summary
      : ["Dieser Agentenbericht enthält keine ausformulierte Artikelzusammenfassung."],
    generatedSummary: summary.length > 0,
    claims,
    sourceSimilarities: normalizedSourceSimilarities(report),
    agentResults: agentResults(report, retrievalReport ? data : null),
    agentAudit: agentAudit(report, retrievalReport ? data : null),
    retrievalIssues,
    timelineSources: [...report.sources, ...(retrievalReport
      ? data.retrievals.flatMap((item) => item.snapshot ? [item.snapshot] : []) : [])],
    provenance: retrievalReport ? readSourceProvenance(data) : null,
    empty: claims.length ? "" : empty,
  };
}

for (const help of document.querySelectorAll(".help-button")) {
  const control = help.parentElement;
  const close = () => help.setAttribute("aria-expanded", "false");
  help.addEventListener("click", () => {
    const opening = help.getAttribute("aria-expanded") === "false";
    control.classList.toggle("dismissed", !opening);
    help.setAttribute("aria-expanded", String(opening));
  });
  control.addEventListener("pointerleave", () => control.classList.remove("dismissed"));
  help.addEventListener("blur", close);
  help.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    control.classList.add("dismissed");
    close();
  });
}

$("workspace").addEventListener("click", (event) => {
  const reference = event.target.closest(".diff-reference");
  if (reference && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
    event.preventDefault();
    $(reference.hash.slice(1))?.focus();
    return;
  }
  const control = event.target.closest("[data-claim], button[data-source]");
  if (!control) return;
  const index = control.dataset.claim;
  if (index !== undefined) {
    event.preventDefault();
    selectClaim(Number(index));
    if (state.report.article && control.classList.contains("highlight")) {
      $("original-quote").closest("details").open = true;
    }
    if (matchMedia("(max-width: 820px)").matches) {
      $("evidence-heading").focus();
    } else {
      $("selection-status").textContent = $("active-claim").textContent + " ausgewählt. Belege aktualisiert.";
    }
  } else {
    selectSource(control.dataset.source);
    $("selection-status").textContent = "Beleg geöffnet: " + control.textContent;
    $("source-detail").focus();
  }
});

$("back-to-claim").addEventListener("click", () => {
  $("claim-list").children[state.claimIndex]?.focus();
});

let latestImport = 0;

async function showReportBytes(bytes, importId, run) {
  if (bytes.byteLength > 50_000_000) throw new Error("Die Datei ist größer als 50 MB.");
  let data;
  try {
    data = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    throw new Error("Die Datei enthält kein lesbares JSON.");
  }
  const report = readReport(data);
  if (run) {
    report.runId = run.run_id;
    report.runProgress = run;
  }
  if (report.privateReview && globalThis.crypto?.subtle) {
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    const review = report.privateReview;
    review.digest = Array.from(new Uint8Array(digest), (value) =>
      value.toString(16).padStart(2, "0")
    ).join("");
    review.readOnly = run && !["complete", "partial"].includes(run.status);
    if (run && !review.readOnly && canPrepareRelease(review.editorial)) {
      review.runId = run.run_id;
      try {
        const response = await localRequest(draftPath(review));
        const draft = await response.json();
        if (draft && draft.review_sha256 !== review.digest) {
          throw new Error("Der Prüfbericht hat sich geändert. Öffne ihn erneut.");
        }
        review.draft = draft;
      } catch (error) {
        review.draftError = error.message;
      }
    }
  }
  if (importId !== latestImport) return;
  renderReport(report);
  $("case-title").focus();
}

$("demo").addEventListener("click", () => {
  latestImport += 1;
  $("file-feedback").textContent = "";
  renderReport(demo);
  $("case-title").focus();
});

$("open-report").addEventListener("click", () => $("report-file").click());
$("report-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const importId = ++latestImport;
  $("release-form").hidden = true;
  const feedback = $("file-feedback");
  event.target.value = "";
  feedback.classList.remove("error");
  try {
    if (file.size > 50_000_000) throw new Error("Die Datei ist größer als 50 MB.");
    await showReportBytes(await file.arrayBuffer(), importId);
    if (importId !== latestImport) return;
    feedback.textContent = "Bericht geöffnet.";
  } catch (error) {
    if (importId !== latestImport) return;
    feedback.classList.add("error");
    feedback.textContent = error.message || "Der Bericht konnte nicht gelesen werden.";
    $("open-report").focus();
  }
});

function downloadJson(payload, filename) {
  downloadFile(new Blob([JSON.stringify(payload, null, 2) + "\n"], { type: "application/json" }), filename);
}

function downloadFile(blob, filename) {
  const href = URL.createObjectURL(blob);
  const link = element("a");
  link.href = href;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}

function draftPath(review) {
  return "/api/runs/" + encodeURIComponent(review.runId) + "/editorial-draft";
}

function draftLabel(draft) {
  if (draft?.approved_at) {
    return "Freigabe erteilt · " + new Date(draft.approved_at).toLocaleString("de-DE");
  }
  return draft ? "Entwurf gespeichert." : "";
}

function setReleaseStatus(message, error = false) {
  $("release-status").classList.toggle("error", error);
  $("release-status").textContent = message;
}

function releaseInput() {
  return {
    text: $("release-text").value.trim(),
    sources_checked: $("release-sources-checked").checked,
    open_findings_addressed: $("release-findings-checked").checked,
  };
}

function updateReleaseControls() {
  const review = state.report.privateReview;
  if (!review || $("release-form").hidden) return;
  const { text, sources_checked, open_findings_addressed } = releaseInput();
  const unavailable = Boolean(review.pending || review.draftError);
  const matchingDraft = Boolean(review.draft && text === review.draft.text);
  $("release-text").readOnly = unavailable;
  $("release-checks").disabled = unavailable;
  $("save-release").disabled = unavailable || !text || (review.runId
    ? matchingDraft
    : !sources_checked || !open_findings_addressed);
  $("approve-release").disabled = unavailable || !matchingDraft || Boolean(review.draft?.approved_at)
    || !sources_checked || !open_findings_addressed;
  const releaseUnavailable = unavailable || !matchingDraft || !review.draft?.approved_at;
  $("export-release").disabled = releaseUnavailable;
  $("preview-release").disabled = releaseUnavailable;
  $("download-preview").disabled = releaseUnavailable;
}

function releasePayload(review, text, reviewedAt) {
  return {
    format: "quellenlot-public-draft-v1",
    review_sha256: review.digest,
    reviewed_at: reviewedAt,
    article_url: safeUrl(state.report.article?.url)?.href || null,
    text,
  };
}

function exportRelease(release) {
  downloadJson(release, "quellenlot-freigabeentwurf.json");
}

function readerHtml(release) {
  const title = "Redaktionelle Einordnung";
  const reader = document.implementation.createHTMLDocument(title + " · Quellenlot");
  reader.documentElement.lang = "de";
  const charset = reader.createElement("meta");
  charset.charset = "utf-8";
  reader.head.prepend(charset);
  for (const [name, content] of [
    ["viewport", "width=device-width, initial-scale=1"],
    ["referrer", "no-referrer"],
  ]) {
    const meta = reader.createElement("meta");
    meta.name = name;
    meta.content = content;
    reader.head.append(meta);
  }
  const policy = reader.createElement("meta");
  policy.httpEquiv = "Content-Security-Policy";
  policy.content = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'";
  const style = reader.createElement("style");
  style.textContent = `
    :root { color-scheme: light dark; font: 100%/1.65 system-ui, sans-serif; color: #231a31; background: #faf7ff; }
    body { margin: 0; border-block-start: 4px solid #9867df; }
    main { max-inline-size: 66ch; margin-inline: auto; padding: clamp(1rem, 5vw, 3rem); }
    h1, summary, code { font-family: "IBM Plex Mono", ui-monospace, monospace; }
    h1 { font-size: clamp(1.5rem, 5vw, 2.25rem); line-height: 1.2; }
    .statement { white-space: pre-wrap; overflow-wrap: anywhere; }
    a { color: #6333a7; text-underline-offset: .2em; }
    details { margin-block-start: 2rem; border-block-start: 1px solid; padding-block-start: .8rem; }
    summary { cursor: pointer; }
    code { display: block; font-size: .875rem; overflow-wrap: anywhere; }
    @media (prefers-color-scheme: dark) {
      :root { color: #f1eafa; background: #171320; }
      a { color: #cda2ff; }
    }
  `;
  reader.head.append(policy, style);

  const main = reader.createElement("main");
  const heading = reader.createElement("h1");
  heading.textContent = title;
  const statement = reader.createElement("p");
  statement.className = "statement";
  statement.textContent = release.text;
  main.append(heading, statement);

  if (release.article_url) {
    const original = reader.createElement("a");
    original.href = release.article_url;
    original.target = "_blank";
    original.rel = "noopener noreferrer";
    original.textContent = "Geprüften Artikel öffnen";
    main.append(original);
  }
  const metadata = reader.createElement("details");
  const caption = reader.createElement("summary");
  caption.textContent = "Freigabedaten";
  const time = reader.createElement("time");
  time.dateTime = release.reviewed_at;
  time.textContent = new Date(release.reviewed_at).toLocaleString("de-DE");
  const approved = reader.createElement("p");
  approved.append("Freigegeben am ", time);
  const digest = reader.createElement("code");
  digest.textContent = release.review_sha256;
  const version = reader.createElement("p");
  version.append("SHA-256 des Prüfberichts ", digest);
  metadata.append(caption, approved, version);
  main.append(metadata);
  reader.body.append(main);
  return "<!doctype html>\n" + reader.documentElement.outerHTML;
}

async function changeDraft(review, action) {
  const input = releaseInput();
  review.pending = true;
  updateReleaseControls();
  setReleaseStatus(action === "approve" ? "Freigabe wird gespeichert …" : "Entwurf wird gespeichert …");
  try {
    const response = await localRequest(draftPath(review), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...input, action, review_sha256: review.digest,
        revision: review.draft?.revision || 0 }),
    });
    review.draft = await response.json();
    if (state.report.privateReview !== review) return;
    setReleaseStatus(draftLabel(review.draft));
  } catch (error) {
    if (state.report.privateReview === review) setReleaseStatus(error.message, true);
  } finally {
    review.pending = false;
    if (state.report.privateReview === review) updateReleaseControls();
  }
}

$("release-form").addEventListener("input", (event) => {
  const review = state.report.privateReview;
  if (review?.draft?.approved_at && event.target === $("release-text")) {
    const before = $("export-release").disabled;
    $("release-sources-checked").checked = false;
    $("release-findings-checked").checked = false;
    if (!before) setReleaseStatus("Speichere die Änderung als Entwurf und prüfe ihn erneut.");
  }
  updateReleaseControls();
});

$("release-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const { privateReview } = state.report;
  const { text } = releaseInput();
  if ($("release-form").hidden || !privateReview?.digest || $("save-release").disabled) return;
  if (privateReview.runId) {
    changeDraft(privateReview, "save");
    return;
  }
  exportRelease(releasePayload(privateReview, text, new Date().toISOString()));
  setReleaseStatus("Freigabeentwurf gespeichert. Die Veröffentlichung erfolgt separat.");
});

$("approve-release").addEventListener("click", () => {
  const review = state.report.privateReview;
  if (review?.runId && !$("release-form").hidden && !$("approve-release").disabled) {
    changeDraft(review, "approve");
  }
});

async function withApprovedRelease(control, present, onError) {
  const review = state.report.privateReview;
  if (!review?.draft?.approved_at || $("release-form").hidden || control.disabled) return;
  review.pending = true;
  updateReleaseControls();
  try {
    const response = await localRequest(draftPath(review));
    const current = await response.json();
    if (state.report.privateReview !== review || $("release-form").hidden) return;
    if (current?.review_sha256 !== review.digest || current?.revision !== review.draft.revision || !current?.approved_at) {
      throw new Error("Die Freigabe hat sich geändert. Öffne den Bericht erneut.");
    }
    present(releasePayload(review, current.text, current.approved_at));
  } catch (error) {
    if (state.report.privateReview === review) onError(error.message);
  } finally {
    review.pending = false;
    if (state.report.privateReview === review) updateReleaseControls();
  }
}

$("export-release").addEventListener("click", (event) => {
  withApprovedRelease(event.currentTarget, (release) => {
    exportRelease(release);
    setReleaseStatus("Freigegebener Text exportiert.");
  }, (message) => setReleaseStatus(message, true));
});

$("preview-release").addEventListener("click", (event) => {
  withApprovedRelease(event.currentTarget, (release) => {
    $("release-preview-frame").srcdoc = readerHtml(release);
    $("release-preview-status").classList.remove("error");
    $("release-preview-status").textContent = "";
    $("release-preview").showModal();
  }, (message) => setReleaseStatus(message, true));
});

$("release-preview").addEventListener("close", () => {
  $("release-preview-frame").removeAttribute("srcdoc");
  const opener = $("preview-release");
  if (document.activeElement === document.body && !$("release-form").hidden && !opener.disabled) {
    opener.focus();
  }
});

$("download-preview").addEventListener("click", (event) => {
  const status = $("release-preview-status");
  status.classList.remove("error");
  status.textContent = "";
  withApprovedRelease(event.currentTarget, (release) => {
    if (!$("release-preview").open) return;
    downloadFile(new Blob([readerHtml(release)], { type: "text/html;charset=utf-8" }), "quellenlot-lesefassung.html");
    status.textContent = "Lesefassung heruntergeladen.";
  }, (message) => {
    status.classList.add("error");
    status.textContent = message;
  });
});

$("urls").addEventListener("input", () => {
  $("urls").removeAttribute("aria-invalid");
  if ($("submit-case").disabled) return;
  $("form-feedback").classList.remove("error");
  $("form-feedback").textContent = "";
});

$("composer").addEventListener("submit", async (event) => {
  event.preventDefault();
  if ($("submit-case").disabled) return;
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
  if (localRuns) {
    $("submit-case").disabled = true;
    try {
      const run = await startLocalRun(payload);
      followLocalRun(run);
    } catch (error) {
      $("submit-case").disabled = false;
      localRunFeedback(error.message, true);
    }
    return;
  }
  downloadJson(payload, "case.json");
  feedback.classList.remove("error");
  feedback.textContent = "case.json gespeichert. Lade hier anschließend den Bericht des lokalen Agenten.";
});

let localRuns = false;
const runStages = {
  capture: "Quellen werden abgerufen …",
  extraction: "Aussagen werden aus dem Artikel ermittelt …",
  provenance: "Vergleichsquellen und Verweise werden ermittelt …",
  comparison: "Aussagen werden mit den Belegen verglichen …",
  interests: "Eigentümerschaft, Finanzierung und Verbindungen werden geprüft …",
  editorial: "Die redaktionelle Prüfung wird erstellt …",
};
const runLabels = {
  running: "Läuft",
  complete: "Abgeschlossen",
  partial: "Teilbericht",
  no_claims: "Keine prüfbaren Aussagen",
  failed: "Fehlgeschlagen",
  interrupted: "Unterbrochen",
};

function localRunFeedback(message, isError = false) {
  const feedback = $("form-feedback");
  feedback.classList.toggle("error", isError);
  if (feedback.textContent !== message) feedback.textContent = message;
}

async function localRequest(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.json();
    throw new Error(body.error || "Der lokale Lauf konnte nicht geladen werden.");
  }
  return response;
}

async function startLocalRun(payload) {
  localRunFeedback("Analyse wird gestartet …");
  const response = await localRequest("/api/runs", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  const run = await response.json();
  const address = new URL(location.href);
  address.searchParams.set("run", run.run_id);
  history.replaceState(null, "", address);
  return run;
}

function listLocalRuns(runs) {
  $("run-list").replaceChildren(...runs.map((run) => {
    const item = element("li");
    const date = new Date(run.started_at).toLocaleString("de-DE");
    const link = element("a", "source-link", [date, runLabels[run.status], run.article_url].join(" · "));
    link.href = "?run=" + encodeURIComponent(run.run_id);
    item.append(link);
    return item;
  }));
  $("run-history").hidden = !runs.length;
}

async function followLocalRun(run) {
  if (run.status === "running") {
    $("submit-case").disabled = true;
    localRunFeedback(runStages[run.stage] || "Analyse läuft …");
    renderAgentWorkflow(null, run);
    setTimeout(async () => {
      try {
        const response = await localRequest("/api/runs/" + encodeURIComponent(run.run_id));
        followLocalRun(await response.json());
      } catch {
        setTimeout(() => followLocalRun(run), 2000);
      }
    }, 1000);
    return;
  }

  $("submit-case").disabled = false;
  const outcome = run.error || `Analyse: ${runLabels[run.status] || run.status}.`;
  localRunFeedback(outcome, run.status === "failed" || run.status === "interrupted");
  const importId = ++latestImport;
  try {
    if (run.has_report) {
      const response = await localRequest("/api/runs/" + encodeURIComponent(run.run_id) + "/report");
      await showReportBytes(await response.arrayBuffer(), importId, run);
    } else {
      renderAgentWorkflow(null, run);
    }
  } catch (error) {
    renderAgentWorkflow(null, run);
    localRunFeedback(error.message, true);
  }
  try {
    listLocalRuns(await (await localRequest("/api/runs")).json());
  } catch {
    // The loaded report stays open if the history cannot be refreshed.
  }
}

async function initializeLocalRuns() {
  if (location.protocol !== "http:" || location.hostname !== "127.0.0.1") return;
  try {
    const runs = await (await localRequest("/api/runs")).json();
    if (!Array.isArray(runs)) return;
    localRuns = true;
    window.quellenlotTrends.enableNews();
    $("submit-case").textContent = "Analyse starten";
    localRunFeedback("");
    listLocalRuns(runs);
    const requestedId = new URLSearchParams(location.search).get("run");
    const run = runs.find((item) => item.run_id === requestedId) || runs.find((item) => item.status === "running");
    if (run) followLocalRun(run);
  } catch {
    // Plain static hosting continues to offer the JSON download and import workflow.
  }
}

let studyView = 0;
let activeStudy = null;

function studyPath() {
  const runId = state.report.runId;
  const claimId = state.report.claims[state.claimIndex]?.id;
  return runId && claimId
    ? "/api/runs/" + encodeURIComponent(runId) + "/claims/" + encodeURIComponent(claimId) + "/studies"
    : null;
}

function studyCard(paper) {
  const row = element("article", "study-result");
  const title = element("h5");
  const link = sourceLink({ url: paper.url }, null, paper.title);
  title.append(link || document.createTextNode(paper.title));
  row.append(title);
  const access = {
    metadata: "Nur Metadaten · Relevanz ungeprüft",
    abstract: "Abstract abgerufen",
    full_text: "Volltext abgerufen",
  };
  const labels = [paper.year ? "Publiziert " + paper.year : null,
    paper.publication_type === "posted-content" ? "Vorabveröffentlichung" : null,
    access[paper.access], paper.excerpt_only ? "Auszüge ausgewertet" : null];
  row.append(element("p", "study-access", labels.filter(Boolean).join(" · ")));
  const assessment = paper.assessment;
  if (!assessment) {
    if (paper.assessment_status === "failed") row.append(element("p", "", "Die KI-Auswertung ist fehlgeschlagen."));
    return row;
  }
  const confirmed = assessment.review_status === "confirmed";
  const relation = confirmed ? assessment.relation : "unclear";
  const badge = element("span", "relation", relationLabels[relation] || "Unklar");
  badge.dataset.kind = relation;
  const judgement = element("p", "study-judgement", "KI-Einordnung ");
  judgement.append(badge);
  row.append(judgement);
  if (!confirmed) {
    const message = assessment.review_status === "unavailable" ? "Zweitprüfung fehlgeschlagen."
      : assessment.review_status === "withheld" ? "Der Bezug zur Aussage konnte nicht bestätigt werden."
      : "Älteres Ergebnis ohne Zweitprüfung. Suche erneut, um den Bezug zu prüfen.";
    row.append(element("p", "study-access", message));
  }
  const fields = [
    ["Untersucht", assessment.measured], ["Population und Ort", assessment.population],
    ["Untersuchungszeitraum", assessment.period], ["Ergebnis", assessment.finding],
  ];
  if (confirmed) fields.push(["Bezug zur Aussage", assessment.rationale]);
  const facts = element("dl", "study-facts");
  const quotes = element("details", "study-quotes");
  quotes.append(element("summary", "", "Textbelege"));
  const material = sourceLink({ url: paper.material_url }, null, "Textgrundlage öffnen");
  if (material) quotes.append(material);
  let hasQuote = false;
  for (const [label, note] of fields) {
    facts.append(element("dt", "", label), element("dd", "", note?.value || "Nicht aus dem Text belegt"));
    if (note?.quote) {
      hasQuote = true;
      quotes.append(element("p", "", label), element("blockquote", "", note.quote));
    }
  }
  row.append(facts);
  if (hasQuote) row.append(quotes);
  return row;
}

async function loadStudies(path, view, search) {
  const feedback = $("studies-status");
  try {
    const response = await localRequest(path, search ? { method: "POST" } : undefined);
    const result = await response.json();
    if (view !== studyView) return;
    if (!result) {
      feedback.textContent = "Die Aussage wird bei der Suche an Crossref gesendet.";
      return;
    }
    $("study-results").replaceChildren(...result.papers.map(studyCard));
    feedback.textContent = result.status === "failed" ? "Die Studiensuche ist fehlgeschlagen."
      : result.status === "partial" ? "Suche oder Auswertung war unvollständig."
      : result.papers.length ? "" : "Keine passenden Studien in den geprüften Treffern gefunden.";
    $("find-studies").textContent = "Erneut suchen";
  } catch (error) {
    if (view === studyView) feedback.textContent = error.message;
  }
}

function renderClaimStudies() {
  const view = ++studyView;
  const path = studyPath();
  $("claim-studies").hidden = !path;
  $("study-results").replaceChildren();
  $("studies-status").textContent = activeStudy === path && path ? "Studien werden gesucht und geprüft …" : "";
  $("find-studies").textContent = "Studien suchen";
  $("find-studies").disabled = Boolean(activeStudy);
  if (path && path !== activeStudy) loadStudies(path, view, false);
}

$("find-studies").addEventListener("click", async () => {
  const path = studyPath();
  if (!path || activeStudy) return;
  activeStudy = path;
  $("find-studies").disabled = true;
  $("studies-status").textContent = "Studien werden gesucht und geprüft …";
  const view = ++studyView;
  try {
    await loadStudies(path, view, true);
  } finally {
    activeStudy = null;
    $("find-studies").disabled = false;
    if (view !== studyView && path === studyPath()) renderClaimStudies();
  }
});

renderReport(demo);
initializeLocalRuns();
