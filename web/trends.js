"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  const series = new Map();
  const events = new Map();
  const publications = new Map();
  let selected = null;
  let fileVersion = 0;
  let localNews = false;
  let suggestionRequest = null;
  const dayMs = 86_400_000;
  const dateFormat = new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeZone: "UTC" });
  const numberFormat = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 4 });
  const months = new Intl.DateTimeFormat("de-DE", { month: "short", year: "numeric", timeZone: "UTC" });

  function dayNumber(value) {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return NaN;
    const result = Date.parse(value + "T00:00:00Z");
    return Number.isFinite(result) && new Date(result).toISOString().slice(0, 10) === value ? result : NaN;
  }

  function status(id, message, error = false) {
    const node = byId(id);
    node.textContent = message;
    node.classList.toggle("error", error);
  }

  // Google Trends exports a category line followed by a single dated series.
  function parseSearchCsv(text) {
    const row = /^\s*("(?:[^"]|"")*"|[^",;\t]*)\s*[,;\t]\s*("(?:[^"]|"")*"|[^",;\t]*)\s*$/;
    const rows = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter((line) => line.trim());
    const columns = (line) => row.exec(line)?.slice(1).map((value) =>
      value.trim().replace(/^"(.*)"$/, "$1").replaceAll('""', '"')
    );
    const cadences = new Map([
      ["day", [1, "Tag"]], ["tag", [1, "Tag"]],
      ["week", [7, "Woche"]], ["woche", [7, "Woche"]],
      ["month", [31, "Monat"]], ["monat", [31, "Monat"]],
    ]);
    const header = rows.findIndex((line) => cadences.has(columns(line)?.[0].toLowerCase()));
    const heading = header < 0 ? null : columns(rows[header]);
    if (!heading?.[1] || rows.length - header - 1 > 600) {
      throw Error("Wähle eine Google-Trends-Zeitreihe mit genau einem Suchbegriff und höchstens 600 Werten.");
    }
    const [step, interval] = cadences.get(heading[0].toLowerCase());
    const points = rows.slice(header + 1).map((line) => {
      const fields = columns(line);
      const timestamp = fields?.[0];
      const raw = fields?.[1];
      const date = step === 31 && /^\d{4}-\d{2}$/.test(timestamp) ? timestamp + "-01" : timestamp;
      if (!Number.isFinite(dayNumber(date)) || (step === 31 && !date.endsWith("-01")) ||
          !/^(?:100|[0-9]{1,2}|<1)$/.test(raw)) {
        throw Error("Die CSV enthält ein ungültiges Datum oder einen ungültigen Indexwert.");
      }
      return { date, value: raw === "<1" ? null : Number(raw) };
    });
    return {
      label: heading[1], points, step, interval, max: 100,
      heading: "Suchinteresse",
      note: "Google Trends · Relativer Index (0–100) innerhalb des Exports. „<1“ bleibt als Lücke sichtbar.",
      source: "https://support.google.com/trends/answer/4365538?hl=de",
    };
  }

  function prepare(dataset) {
    const points = dataset.points.map(({ date, value }) => ({ date, time: dayNumber(date), value }));
    if (!points.length) throw Error("Für den gewählten Zeitraum liegen keine Daten vor.");
    if (points.some(({ time, value }) => !Number.isFinite(time) ||
        (value !== null && (!Number.isFinite(value) || value < 0 || value > 100)))) {
      throw Error("Die Zeitreihe enthält ungültige Messwerte.");
    }
    points.sort((a, b) => a.time - b.time);
    if (points.some((point, index) => index && point.time === points[index - 1].time)) {
      throw Error("Die Zeitreihe enthält mehrere Werte pro Datum.");
    }
    return { ...dataset, points };
  }

  // Require measured values on both adjacent days. Missing days and tied peaks
  // cannot establish a local spike. Rank eligible peaks by height above neighbors.
  function strongestSpike(dataset) {
    const today = Math.floor(Date.now() / dayMs) * dayMs;
    let spike = null;
    let prominence = 0;
    for (let index = 1; index < dataset.points.length - 1; index += 1) {
      const [before, point, after] = dataset.points.slice(index - 1, index + 2);
      if (point.time < today - 89 * dayMs || point.time > today ||
          point.time - before.time !== dayMs || after.time - point.time !== dayMs ||
          before.value === null || point.value === null || after.value === null ||
          point.value <= Math.max(before.value, after.value)) continue;
      const baseline = (before.value + after.value) / 2;
      const increase = point.value - baseline;
      if (point.value >= 1.25 * baseline && increase > prominence) {
        spike = point;
        prominence = increase;
      }
    }
    return spike;
  }

  function resetSuggestions() {
    suggestionRequest?.abort();
    suggestionRequest = null;
    byId("trend-suggestion-list").replaceChildren();
    status("trend-suggestion-status", "");
    const hasNews = series.has("news");
    const dailyCsv = series.get("search")?.step === 1;
    byId("trend-suggestion-panel").hidden = !localNews || (!hasNews && !dailyCsv);
    byId("suggest-news-events").hidden = !hasNews;
    byId("suggest-search-events").hidden = !dailyCsv;
    byId("suggest-news-events").disabled = false;
    byId("suggest-search-events").disabled = false;
  }

  async function suggestEvents(kind) {
    resetSuggestions();
    const dataset = series.get(kind);
    const peak = dataset?.step === 1 && strongestSpike(dataset);
    if (!peak) {
      status("trend-suggestion-status", "Kein klarer Tagesausschlag in den letzten 90 Tagen gefunden.");
      return;
    }
    const topic = kind === "news" ? dataset.topic : byId("trend-topic").value.trim();
    const language = kind === "news" ? dataset.language : byId("trend-language").value;
    if (topic.length < 3 || topic.length > 120) {
      status("trend-suggestion-status", "Gib oben einen Suchbegriff mit 3 bis 120 Zeichen ein.", true);
      byId("trend-topic").focus();
      return;
    }
    const request = new AbortController();
    suggestionRequest = request;
    byId("suggest-news-events").disabled = true;
    byId("suggest-search-events").disabled = true;
    status("trend-suggestion-status", "Suche nach Artikeln zum Ausschlag am " + dateFormat.format(peak.time) + " …");
    try {
      const response = await fetch("/api/trend-events", {
        method: "POST", headers: { "Content-Type": "application/json" },
        signal: request.signal, body: JSON.stringify({ topic, language, peak_date: peak.date }),
      });
      const data = await response.json();
      if (request !== suggestionRequest) return;
      if (!response.ok) throw Error(data.error || "Die Ereignisvorschläge konnten nicht geladen werden.");
      const start = dayNumber(data.window_start);
      const end = dayNumber(data.window_end);
      if (!Number.isFinite(start) || !Number.isFinite(end) || data.peak_date !== peak.date ||
          start > peak.time || end < peak.time || !Array.isArray(data.articles)) {
        throw Error("GDELT hat ein ungültiges Suchfenster geliefert.");
      }
      const items = data.articles.flatMap((article) => {
        const url = safeUrl(article?.url);
        const indexed = dayNumber(article?.indexed_date);
        if (!url || !Number.isFinite(indexed) || indexed < start || indexed > end ||
            typeof article.title !== "string" || !article.title.trim()) return [];
        const item = element("li");
        const link = sourceLink({ url: url.href }, null, article.title);
        const use = button("Beleg übernehmen", "quiet-button");
        use.disabled = url.href.length > 2000;
        use.setAttribute("aria-label", "Beleg übernehmen: " + article.title);
        use.addEventListener("click", () => {
          byId("trend-event-title").value = article.title.slice(0, 180);
          byId("trend-event-url").value = url.href;
          byId("trend-event-date").value = "";
          status("trend-event-status", "Prüfe den Beleg und trage das Ereignisdatum ein.");
          byId("trend-event-date").focus();
        });
        item.append(link, element("p", "trend-note", "GDELT erfasst am " + dateFormat.format(indexed)), use);
        return [item];
      });
      byId("trend-suggestion-list").replaceChildren(...items);
      const windowLabel = dateFormat.format(start) + " bis " + dateFormat.format(end);
      status("trend-suggestion-status", "Ausschlag am " + dateFormat.format(peak.time) + " · " +
        windowLabel + " · " + (items.length ? items.length + " Artikel gefunden." : "Keine passenden Artikel gefunden."));
    } catch (error) {
      if (request === suggestionRequest) status("trend-suggestion-status", error.message, true);
    } finally {
      if (request === suggestionRequest) {
        suggestionRequest = null;
        byId("suggest-news-events").disabled = false;
        byId("suggest-search-events").disabled = false;
      }
    }
  }

  function svgNode(tag, attrs) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
    return node;
  }

  function drawPlot(dataset, markers, start, end) {
    const max = dataset.max ?? (Math.max(...dataset.points.map(({ value }) => value)) || 1);
    const chart = svgNode("svg", { viewBox: "0 0 720 168", preserveAspectRatio: "none", "aria-hidden": "true", class: "trend-plot" });
    const x = (time) => start === end ? 360 : 10 + 700 * (time - start) / (end - start);
    const y = (value) => 150 - 140 * value / max;
    for (const value of [0, max / 2, max]) {
      chart.append(svgNode("line", { x1: 10, x2: 710, y1: y(value), y2: y(value), class: "trend-grid" }));
    }

    let path = "";
    let previous = null;
    for (const point of dataset.points) {
      if (point.value === null) {
        previous = null;
        continue;
      }
      const connected = previous !== null && point.time - previous <= dataset.step * dayMs;
      path += (connected ? "L" : "M") + x(point.time) + "," + y(point.value);
      if (!connected || dataset.points.length <= 1) {
        chart.append(svgNode("circle", { cx: x(point.time), cy: y(point.value), r: 2.5, class: "trend-point" }));
      }
      previous = point.time;
    }
    chart.append(svgNode("path", { d: path, class: "trend-line" }));
    for (const time of new Set(markers.map(({ time }) => time))) {
      if (time < start || time > end) continue;
      const active = time === selected;
      chart.append(svgNode("line", {
        x1: x(time), x2: x(time), y1: 9, y2: 158,
        class: active ? "trend-marker active" : "trend-marker",
      }));
    }
    const axis = element("div", "trend-axis");
    axis.append(element("span", "", dateFormat.format(start)));
    if (end !== start) axis.append(element("span", "", dateFormat.format(end)));
    const scale = element("div", "trend-scale", "Skala 0–" + numberFormat.format(max) +
      (dataset.heading === "Medienberichterstattung" ? " %" : ""));
    const wrapper = element("div");
    wrapper.append(scale, chart, axis);
    return wrapper;
  }

  function trendTable(dataset) {
    const details = element("details", "trend-data");
    details.append(element("summary", "", "Datenwerte"));
    const table = element("table");
    const header = table.createTHead().insertRow();
    header.append(element("th", "", dataset.interval), element("th", "", "Wert"));
    const body = table.createTBody();
    for (const point of dataset.points) {
      const row = body.insertRow();
      row.insertCell().textContent = (dataset.step === 31 ? months : dateFormat).format(point.time);
      row.insertCell().textContent = point.value === null ? "<1" : numberFormat.format(point.value);
    }
    details.append(table);
    return details;
  }

  function allMarkers() {
    return [...events.values(), ...publications.values()].sort((a, b) => a.time - b.time);
  }

  function drawSeries(markers = allMarkers()) {
    const datasets = [...series.values()];
    const domains = datasets.map(({ points }) => [points[0].time, points.at(-1).time]);
    const overlap = domains.length === 2 && Math.max(domains[0][0], domains[1][0]) <= Math.min(domains[0][1], domains[1][1]);
    const shared = overlap ? [Math.min(...domains.map(([start]) => start)), Math.max(...domains.map(([, end]) => end))] : null;
    byId("trend-series").replaceChildren(...datasets.map((dataset, index) => {
      const panel = element("section", "trend-series-panel");
      panel.dataset.kind = dataset.heading === "Suchinteresse" ? "search" : "news";
      panel.append(element("h3", "", dataset.heading + " · " + dataset.label));
      const note = element("p", "trend-note", dataset.note + " ");
      const link = element("a", "", panel.dataset.kind === "search" ? "Zum CSV-Export" : "Quelle öffnen");
      link.href = dataset.source;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      note.append(link);
      const [start, end] = shared || domains[index];
      panel.append(note, drawPlot(dataset, markers, start, end), trendTable(dataset));
      return panel;
    }));
  }

  function render() {
    const markers = allMarkers();
    drawSeries(markers);
    const list = byId("trend-events");
    list.replaceChildren();
    for (const marker of markers) {
      const item = element("li");
      const day = button(dateFormat.format(marker.time), "outline-button trend-date");
      day.dataset.time = String(marker.time);
      day.setAttribute("aria-pressed", String(marker.time === selected));
      const link = element("a", "", marker.title);
      link.href = marker.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      day.addEventListener("click", () => {
        selected = selected === marker.time ? null : marker.time;
        for (const control of list.querySelectorAll("button[data-time]")) {
          control.setAttribute("aria-pressed", String(Number(control.dataset.time) === selected));
        }
        drawSeries();
      });
      item.append(day, element("span", "trend-event-kind", marker.kind), link);
      if (marker.key) {
        const remove = button("Entfernen", "quiet-button");
        remove.setAttribute("aria-label", "Ereignis entfernen: " + marker.title);
        remove.addEventListener("click", () => {
          events.delete(marker.key);
          render();
          byId("trend-event-title").focus();
        });
        item.append(remove);
      }
      list.append(item);
    }
  }

  byId("search-trend-file").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    event.target.value = "";
    if (!file) return;
    const version = ++fileVersion;
    try {
      if (file.size > 200_000) throw Error("Die CSV-Datei ist größer als 200 kB.");
      const loaded = prepare(parseSearchCsv(await file.text()));
      if (version !== fileVersion) return;
      series.set("search", loaded);
      resetSuggestions();
      render();
      status("search-trend-status", "CSV geladen.");
    } catch (error) {
      if (version === fileVersion) status("search-trend-status", error.message, true);
    }
  });

  byId("news-trend-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = byId("load-trends");
    if (submit.disabled) return;
    submit.disabled = true;
    status("news-trend-status", "Medienberichterstattung wird geladen …");
    const topic = byId("trend-topic").value.trim();
    const days = Number(byId("trend-days").value);
    const language = byId("trend-language").value;
    try {
      const response = await fetch("/api/news-trend", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, days, language }),
      });
      const data = await response.json();
      if (!response.ok) throw Error(data.error || "Die Medienzeitreihe konnte nicht geladen werden.");
      const source = safeUrl(data.source_url);
      if (!source) throw Error("Der Quellenlink der Zeitreihe ist ungültig.");
      series.set("news", prepare({
        label: data.label, points: data.points, step: 1, interval: "Tag",
        heading: "Medienberichterstattung",
        note: "GDELT · Anteil aller von GDELT erfassten Artikel pro UTC-Tag · " +
          (language === "german" ? "Treffer auf Deutsch." : "Treffer in allen Sprachen."),
        source: source.href, topic, language,
      }));
      resetSuggestions();
      render();
      status("news-trend-status", "Medienzeitreihe geladen.");
    } catch (error) {
      status("news-trend-status", error.message, true);
    } finally {
      submit.disabled = false;
    }
  });

  byId("suggest-news-events").addEventListener("click", () => suggestEvents("news"));
  byId("suggest-search-events").addEventListener("click", () => suggestEvents("search"));

  byId("trend-event-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const time = dayNumber(byId("trend-event-date").value);
    const title = byId("trend-event-title").value.trim();
    const url = safeUrl(byId("trend-event-url").value);
    if (!Number.isFinite(time) || !title || !url) {
      status("trend-event-status", "Gib ein Datum, ein Ereignis und einen gültigen HTTP(S)-Beleglink ein.", true);
      return;
    }
    const key = JSON.stringify([time, title, url.href]);
    events.set(key, { time, title, url: url.href, kind: "Ereignis", key });
    selected = time;
    render();
    event.currentTarget.reset();
    status("trend-event-status", "Ereignis eingetragen.");
  });

  window.quellenlotTrends = {
    enableNews() {
      localNews = true;
      byId("news-trend-form").hidden = false;
      resetSuggestions();
    },
    setPublications(snapshots) {
      publications.clear();
      for (const snapshot of snapshots) {
        const declared = snapshot?.published_at?.value;
        const time = dayNumber(typeof declared === "string" ? declared.slice(0, 10) : null);
        const url = safeUrl(snapshot?.url);
        if (!Number.isFinite(time) || !url || typeof snapshot.title !== "string" || !snapshot.title) continue;
        const key = JSON.stringify([time, url.href]);
        publications.set(key, { time, url: url.href, title: snapshot.title, kind: "Veröffentlichung" });
      }
      render();
    },
  };
})();
