"use strict";

const parliamentPicker = document.getElementById("parliament-case");
const parliamentStance = document.getElementById("parliament-stance");
const programmeComparisons = document.getElementById("programme-comparisons");
const dateFormat = new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeZone: "UTC" });

function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text) result.textContent = text;
  if (className) result.className = className;
  return result;
}

function recordDate(value) {
  const time = node("time", dateFormat.format(new Date(value)), "record-date");
  time.dateTime = value;
  return time;
}

function recordSource({ label, url }) {
  const anchor = node("a", label);
  anchor.href = url;
  return anchor;
}

function quoteText(text) {
  return node("blockquote", "„" + text + "“");
}

function voteTable(rows) {
  const table = node("table", "", "vote-table");
  const caption = node("caption", "Gesamt und ausgewählte Fraktionen");
  const header = table.createTHead().insertRow();
  for (const column of ["Fraktion", "Ja", "Nein", "Enth.", "Nicht abgest."]) {
    const heading = node("th", column);
    heading.scope = "col";
    if (column === "Enth.") heading.setAttribute("aria-label", "Enthalten");
    if (column === "Nicht abgest.") heading.setAttribute("aria-label", "Nicht abgestimmt");
    header.append(heading);
  }
  table.prepend(caption);
  const body = table.createTBody();
  for (const { group, counts } of rows) {
    const row = body.insertRow();
    const label = node("th", group);
    label.scope = "row";
    row.append(label, ...counts.map((count) => node("td", String(count))));
  }
  return table;
}

function timelineRecord(record, isOpen) {
  const item = node("li");
  const panel = node("details", "", "card timeline-record");
  panel.open = isOpen;
  panel.id = record.id;
  const summary = node("summary");
  const metadata = node("span", "", "record-meta");
  metadata.append(recordDate(record.date), node("span", record.type));
  summary.append(metadata, node("span", record.title, "record-title"));
  const content = node("div", "", "record-body");
  content.append(node("p", record.text));
  if (record.quote) content.append(quoteText(record.quote));
  if (record.context) content.append(node("p", record.context, "record-context"));
  if (record.tally) {
    content.append(node("p", record.result, "vote-result"), voteTable(record.tally));
  }
  const sources = node("div", "", "record-links");
  sources.append(...record.sources.map(recordSource));
  content.append(sources);
  panel.append(summary, content);
  item.append(panel);
  return item;
}

function programmeCard(programme, records) {
  const item = node("article", "", "card programme-card");
  const heading = node("div", "", "programme-heading");
  heading.append(node("h3", programme.party), recordDate(programme.date));
  const assessment = node("h4", programme.assessment, "programme-assessment");
  assessment.dataset.position = programme.position;
  const match = node("p", "", "programme-match");
  match.dataset.position = programme.position;
  match.setAttribute("role", "status");
  const sources = node("div", "", "record-links");
  sources.append(recordSource(programme.source));
  const references = node("div", "", "record-links");
  for (const id of programme.records) {
    const record = records.find((entry) => entry.id === id);
    if (!record) continue;
    const link = node("a", record.shortTitle || record.title);
    link.href = "#" + id;
    link.addEventListener("click", (event) => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      const panel = document.getElementById(id);
      panel.open = true;
      if (location.hash !== link.hash) history.pushState(null, "", link.hash);
      panel.scrollIntoView();
      panel.querySelector("summary").focus({ preventScroll: true });
    });
    references.append(link);
  }
  item.append(heading, quoteText(programme.quote), sources, assessment,
    node("p", programme.explanation), references, match);
  return item;
}

function renderStance() {
  const response = parliamentStance.querySelector("input:checked")?.value;
  for (const match of programmeComparisons.querySelectorAll(".programme-match")) {
    const position = match.dataset.position;
    match.textContent = !response || response === "neutral" ? "" :
      position === "open" ? "Das Programm legt sich zu dieser Frage nicht eindeutig fest." :
      position === response ? "Deine Position und die Programmaussage zeigen in dieselbe Richtung." :
      "Deine Position und die Programmaussage gehen in unterschiedliche Richtungen.";
  }
}

function renderParliamentCase(record) {
  document.getElementById("parliament-scope").textContent = record.scope;
  document.getElementById("parliament-title").textContent = record.title;
  document.getElementById("parliament-proposition").textContent = record.proposition;
  const context = document.getElementById("parliament-context");
  context.replaceChildren(record.context.text + " ", recordSource(record.context.source));
  for (const input of parliamentStance.querySelectorAll("input")) input.checked = false;
  programmeComparisons.replaceChildren(...record.programmes.map((entry) => programmeCard(entry, record.records)));
  const currentHash = location.hash.slice(1);
  document.getElementById("parliament-records").replaceChildren(...record.records.map((entry) =>
    timelineRecord(entry, entry.id === currentHash || entry.id === record.featuredRecord)
  ));
}

parliamentPicker.replaceChildren(...parliamentaryCases.map((entry) => new Option(entry.title, entry.id)));
document.getElementById("parliament-case-picker").hidden = parliamentaryCases.length < 2;
parliamentPicker.addEventListener("change", () => {
  const record = parliamentaryCases.find((entry) => entry.id === parliamentPicker.value);
  if (record) renderParliamentCase(record);
});
parliamentStance.addEventListener("change", renderStance);
renderParliamentCase(parliamentaryCases[0]);
