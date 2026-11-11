"use strict";
// ML-04 climate anomaly dashboard (tab #anom). Uses helpers from app.js ($, fmt, esc, getJSON, LABEL, showLayer, state, period),
// which are resolved at call time. Reads /api/ml04/* and /layers/anom/*; no external dependencies.
const VNAME = { t2m: "temperature", slp: "sea-level pressure", wspd: "wind speed", rhum: "humidity", prate: "precipitation",
  tcdc: "cloud cover", z500: "500 hPa height", sic: "sea-ice conc.", dsic: "sea-ice change", multivariate: "multivariate" };
const anom = { month: null, products: [], summary: [], records: [] };

function svgLine(series, { w = 600, h = 170, ymin, ymax, mark, ref, label } = {}) {
  const all = series.flat().filter((p) => p.y != null && Number.isFinite(p.y));
  if (!all.length) return "<p class='note'>no data</p>";
  const x0 = Math.min(...all.map((p) => +p.x)), x1 = Math.max(...all.map((p) => +p.x));
  const lo = ymin ?? Math.min(...all.map((p) => p.y)), hi = ymax ?? Math.max(...all.map((p) => p.y));
  const L = 36, R = 6, T = 6, B = 18, d = hi - lo < 1 ? 2 : 1;
  const X = (x) => L + ((+x - x0) / Math.max(x1 - x0, 1)) * (w - L - R);
  const Y = (y) => T + (1 - (Math.min(Math.max(y, lo), hi) - lo) / Math.max(hi - lo, 1e-9)) * (h - T - B);
  const path = (s) => s.filter((p) => p.y != null && Number.isFinite(p.y)).map((p, i) => `${i ? "L" : "M"}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join("");
  const years = [];
  for (let y = new Date(x0).getFullYear(); y <= new Date(x1).getFullYear(); y++) years.push(y);
  const step = Math.ceil(years.length / 8);
  return `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label || "time series")}">
    <line class="axis" x1="${L}" y1="${h - B}" x2="${w - R}" y2="${h - B}"/><line class="axis" x1="${L}" y1="${T}" x2="${L}" y2="${h - B}"/>
    <text x="2" y="${T + 8}">${fmt(hi, d)}</text><text x="2" y="${h - B}">${fmt(lo, d)}</text>
    ${years.filter((_, i) => i % step === 0).map((y) => `<text x="${X(new Date(y, 0, 1)).toFixed(1)}" y="${h - 4}">${y}</text>`).join("")}
    ${ref != null && ref >= lo && ref <= hi ? `<line class="mark" x1="${L}" x2="${w - R}" y1="${Y(ref)}" y2="${Y(ref)}"/>` : ""}
    ${mark && +mark >= x0 && +mark <= x1 ? `<line class="mark" x1="${X(mark)}" x2="${X(mark)}" y1="${T}" y2="${h - B}"/>` : ""}
    ${series.map((s, i) => `<path class="${i ? "line2" : "line"}" d="${path(s)}"/>`).join("")}</svg>`;
}

function svgBars(items, { w = 600, h = 150 } = {}) {
  const m = Math.max(...items.map((d) => d.v), 0.06), bw = (w - 40) / items.length, H = h - 34;
  const ref = h - 20 - (0.05 / m) * H;
  return `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="flagged area by variable">
    ${items.map((d, i) => { const bh = (d.v / m) * H, x = 40 + i * bw; return `<rect class="bar" x="${x + 4}" y="${h - 20 - bh}" width="${bw - 8}" height="${bh}"><title>${esc(d.k)}: ${fmt(100 * d.v, 1)} %</title></rect>
      <text x="${x + bw / 2}" y="${h - 6}" text-anchor="middle">${esc(d.k)}</text><text x="${x + bw / 2}" y="${h - 24 - bh}" text-anchor="middle">${fmt(100 * d.v, 0)}%</text>`; }).join("")}
    <line class="mark" x1="40" x2="${w}" y1="${ref}" y2="${ref}"/><text x="2" y="${ref + 3}">5 %</text></svg>`;
}

async function loadAnom(month) {
  try {
    const lat = await getJSON("/api/ml04/latest");
    anom.products = lat.available_products;
    anom.month = month || anom.month || (lat.latest_multivariate || lat.latest_any).month;
    const d = await getJSON(`/layers/anom/anom_${anom.month}/manifest`);
    state.data = d;
    const s = d.summary || {};
    const sel = `<select id="monthsel" aria-label="month">${anom.products.map((m) => `<option ${m === anom.month ? "selected" : ""}>${m}</option>`).join("")}</select>`;
    $("meta").innerHTML = `<h2>Monthly anomaly product</h2><dl><dt>Month</dt><dd>${sel}</dd><dt>Period</dt><dd>${esc(period(s.period))}</dd>
      <dt>Detector</dt><dd>${esc((s.selected_method || "").replace(/_/g, " "))}</dd><dt>Model</dt><dd>${esc(d.model_version)}</dd>
      <dt>Baselines</dt><dd>maps 1991–2020 · detector 1981–2010</dd></dl>`
      + (s.atmosphere_available ? "" : "<p class='warn'>⚠ Sea-ice data only for this month: the NCEP R1 atmospheric record ends 2026-03-17.</p>")
      + "<p class='note'>Statistical anomalies are not confirmed extreme events and imply no cause.</p>";
    $("monthsel").addEventListener("change", (e) => loadAnom(e.target.value));
    const rasters = d.layers.filter((l) => l.png_url);
    $("layers").innerHTML = rasters.map((l) => `<li><button data-id="${esc(l.id)}"><span class="badge ${esc(l.data_type)}">`
      + `${esc(LABEL[l.data_type] || l.data_type)}</span>${esc(l.title)}</button><a href="${esc(l.tif_url)}" download>GeoTIFF</a></li>`).join("");
    $("layers").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => showLayer(rasters.find((l) => l.id === b.dataset.id))));
    showLayer(rasters.find((l) => l.id === "multivariate_severity") || rasters.find((l) => l.id === "sic_anomaly_native") || rasters[0]);
    const st = s.statistics || {};
    const regs = (s.regions || []).slice().sort((a, b) => b.flagged / b.cells - a.flagged / a.cells);
    $("summary").innerHTML = (st.multivariate_flag_cells != null ? `<table><tr><th>2.5° cells</th><th>count</th></tr>
      <tr><td>flagged (≥ moderate, multivariate)</td><td>${fmt(st.multivariate_flag_cells, 0)}</td></tr>
      <tr><td>strong or extreme</td><td>${fmt(st.strong_or_extreme_cells, 0)}</td></tr></table>` : "")
      + (regs.length ? `<table><tr><th>Region</th><th>flagged</th><th>cells</th></tr>${regs.map((r) =>
        `<tr><td>${esc(r.region.replace(/_/g, " "))}</td><td>${r.flagged}</td><td>${r.cells}</td></tr>`).join("")}</table>` : "")
      + `<table><tr><th>Area-weighted mean z (1991–2020)</th><th>z</th></tr>${Object.entries(st).filter(([k]) => k.endsWith("_mean_z"))
        .map(([k, v]) => `<tr><td>${esc(VNAME[k.split("_")[0]] || k)}</td><td>${fmt(v, 2)}</td></tr>`).join("")}</table>`;
    $("limits").innerHTML = (s.limitations || []).map((x) => `<li>${esc(x)}</li>`).join("");
  } catch (e) {
    $("meta").innerHTML = `<p class="warn">No ML-04 anomaly products available (${esc(e.message)}).</p>`;
    $("layers").innerHTML = ""; $("summary").innerHTML = "";
    return;
  }
  anomMetrics(); anomTrend(); anomSeasonal(); anomExtent(); anomEvents(); anomClusters();
}

async function anomMetrics() {
  try {
    const m = await getJSON("/api/ml04/metrics");
    const t = m.test || m.validation, which = m.test ? "Test 2018–2025" : "Validation 2011–2017";
    $("metrics").innerHTML = `<table><tr><th>method</th><th>PR-AUC</th><th>compound</th><th>cov. break</th></tr>${Object.entries(t).map(([n, x]) =>
      `<tr><td>${esc(n.replace(/_/g, " "))}${n === m.decision.selected_multivariate ? " ★" : ""}</td><td>${fmt(x.pr_auc)}</td>`
      + `<td>${fmt(x.pr_auc_compound_moderate)}</td><td>${fmt(x.pr_auc_covariance_break)}</td></tr>`).join("")}</table>
      <p class="note">${which}: recovery of SYNTHETIC injected anomalies (no labelled real anomalies exist). ★ = selected on validation.</p>`;
  } catch (e) { $("metrics").textContent = "Metrics unavailable."; }
}

async function anomTrend() {
  try {
    if (!anom.summary.length) anom.summary = (await getJSON("/api/ml04/monthly-summary")).rows;
    const rows = anom.summary, pts = rows.map((r) => ({ x: new Date(r.month + "-01"), y: r.multivariate_flag_area_fraction }));
    const run = pts.map((p, i) => { const w = pts.slice(Math.max(0, i - 11), i + 1).map((q) => q.y); return { x: p.x, y: w.length === 12 ? w.reduce((a, b) => a + b) / 12 : null }; });
    $("trend").innerHTML = svgLine([pts, run], { ymin: 0, mark: new Date(anom.month + "-01"), ref: 0.05, label: "flagged area fraction" });
    $("trendnote").textContent = "Teal: monthly fraction of the domain area flagged (≥ moderate); orange: 12-month mean; dashed: 5 % expected under the 1979–2010 climate.";
    const r = rows.find((x) => x.month === anom.month);
    $("varbars").innerHTML = r ? svgBars(["t2m", "slp", "wspd", "rhum", "prate", "tcdc", "z500", "sic"].map((v) => ({ k: v, v: r[`${v}_flag_area_fraction`] || 0 })))
      + "<p class='note'>Fraction of the domain area with |z| ≥ moderate (training base rate 5 %, dashed).</p>"
      : "<p class='note'>No multivariate data for this month.</p>";
  } catch (e) { $("trend").textContent = "Summary unavailable."; }
}

async function anomSeasonal() {
  try {
    const rows = (await getJSON("/api/ml04/seasonal-summary?region=all")).rows;
    const keys = [...new Set(rows.map((r) => `${r.season_year} ${r.season}`))].slice(-8).reverse(), vars = ["t2m", "slp", "z500", "sic"];
    const val = (k, v) => rows.find((r) => `${r.season_year} ${r.season}` === k && r.variable === v)?.mean_z;
    $("seasonal").innerHTML = `<table><tr><th>season</th>${vars.map((v) => `<th>${VNAME[v]}</th>`).join("")}</tr>${keys.map((k) =>
      `<tr><td>${k}</td>${vars.map((v) => `<td>${fmt(val(k, v), 2)}</td>`).join("")}</tr>`).join("")}</table>
      <p class="note">Seasonal means vs the 1991–2020 seasonal climatology (DJF belongs to the year of its February).</p>`;
  } catch (e) { $("seasonal").textContent = "Seasonal summary unavailable."; }
}

async function anomExtent() {
  try {
    const y = Number(anom.month.slice(0, 4));
    const rows = (await getJSON(`/api/ml04/sea-ice-extent?start=${y - 3}-01-01`)).rows;
    $("extent").innerHTML = svgLine([rows.map((r) => ({ x: new Date(r.date), y: r.total_anomaly_mkm2 }))], { ref: 0, mark: new Date(anom.month + "-15"), label: "extent anomaly" })
      + "<p class='note'>Daily total extent anomaly (10⁶ km²) vs the 1991–2020 day-of-year mean (NOAA/NSIDC CDR v6); dashed vertical line = selected month.</p>";
  } catch (e) { $("extent").textContent = "Extent unavailable."; }
}

async function anomEvents() {
  try {
    const r = await getJSON(`/api/ml04/anomalies?start=${anom.month}&end=${anom.month}&severity=strong&limit=60`);
    anom.records = r.records;
    $("details").innerHTML = "<p class='note'>Select a row to see its details.</p>";
    $("events").innerHTML = r.records.length ? `<div class="scroll"><table><tr><th>variable</th><th>type</th><th>severity</th><th>score</th><th>lat</th><th>lon</th><th>region</th><th>evidence</th></tr>
      ${r.records.map((x, i) => `<tr data-i="${i}" tabindex="0"><td>${esc(VNAME[x.variable] || x.variable)}</td><td>${esc(x.anomaly_type)}</td><td class="sev-${esc(x.severity)}">${esc(x.severity)}</td>
        <td>${fmt(x.anomaly_score, 2)}</td><td>${fmt(x.latitude, 1)}</td><td>${fmt(x.longitude, 1)}</td><td>${esc((x.region || "").replace(/_/g, " "))}</td><td>${esc(x.confidence)}</td></tr>`).join("")}</table></div>
      <p class="note">${r.total} strong/extreme records this month (showing ${r.records.length}). Univariate scores are z (1991–2020); multivariate scores are detector scores (1981–2010).</p>`
      : "<p class='note'>No strong or extreme anomalies recorded for this month.</p>";
    $("events").querySelectorAll("tr[data-i]").forEach((tr) => {
      const f = () => anomDetail(Number(tr.dataset.i), tr);
      tr.addEventListener("click", f); tr.addEventListener("keydown", (e) => { if (e.key === "Enter") f(); });
    });
  } catch (e) { $("events").textContent = "Anomaly records unavailable."; }
}

function anomDetail(i, tr) {
  document.querySelectorAll("#events tr").forEach((r) => r.removeAttribute("aria-selected"));
  tr.setAttribute("aria-selected", "true");
  const x = anom.records[i];
  const rows = [["Variable", VNAME[x.variable] || x.variable], ["Date", x.observation_timestamp.slice(0, 7) + " (monthly mean)"],
    ["Location", `${fmt(x.latitude, 2)}°, ${fmt(x.longitude, 2)}° · ${(x.region || "").replace(/_/g, " ")}`]];
  if (x.variable !== "multivariate") {
    rows.push(["Observed value", fmt(x.observed_value, 2)], ["Historical mean (1991–2020)", fmt(x.baseline_mean, 2)],
      ["Anomaly magnitude", fmt(x.observed_value - x.baseline_mean, 2)], ["Percentile", fmt(x.percentile, 1)], ["z-score", fmt(x.anomaly_score, 2)]);
  } else {
    rows.push(["Detector score", fmt(x.anomaly_score, 3)], ["Main contributing variables", x.top_variables]);
  }
  rows.push(["Severity", x.severity], ["Detection method", `${x.method} (baseline ${x.baseline_period})`],
    ["Supporting evidence", x.confidence + (x.data_tier ? ` (data tier ${x.data_tier})` : "")], ["Source", x.source_dataset]);
  $("details").innerHTML = `<dl class="kv">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
    <p class="note">Statistical unusualness only. A physical explanation or attribution needs separate evidence.</p>`;
}

async function anomClusters() {
  try {
    const r = await getJSON("/api/ml04/events?min_months=2&limit=12");
    $("clusters").innerHTML = `<div class="scroll"><table><tr><th>start</th><th>end</th><th>months</th><th>max area (10⁶ km²)</th><th>regions</th></tr>${r.events.map((e) =>
      `<tr><td>${esc(e.start)}</td><td>${esc(e.end)}</td><td>${e.n_months}</td><td>${fmt(e.max_area_km2 / 1e6, 2)}</td><td>${esc(e.regions.replace(/_/g, " "))}</td></tr>`).join("")}</table></div>
      <p class="note">${esc(r.definition)}.</p>`;
  } catch (e) { $("clusters").textContent = "Events unavailable."; }
}
