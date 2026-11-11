"use strict";
// AETHENTRA viewer: reads /layers/{product}/latest and the test-metric endpoints; no external dependencies.
const $ = (id) => document.getElementById(id);
const fmt = (v, d = 2) => (v == null || Number.isNaN(Number(v)) ? "n/a"
  : Number(v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }));
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const LABEL = { observation: "OBSERVATION", reanalysis_observation: "REANALYSIS", model_prediction: "MODEL PREDICTION", evaluation: "EVALUATION",
  "weekly composite of model predictions": "WEEKLY COMPOSITE", "observation coverage": "COVERAGE",
  statistical_anomaly: "STATISTICAL ANOMALY", anomaly_detection: "DETECTOR OUTPUT", climatology: "CLIMATOLOGY" };
const BADGE = { "weekly composite of model predictions": "model_prediction", "observation coverage": "observation" };
const METRICS_URL = { sic: "/forecast/metrics", t2m: "/temperature/forecast/metrics", sar: "/seaice-detection/detection/metrics" };
const state = { product: "sic", data: null };

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}
const period = (p) => (Array.isArray(p) ? p.join(" … ") : p || "");

function showLayer(l) {
  document.querySelectorAll("#layers button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.id === l.id)));
  const pred = l.data_type === "model_prediction" || l.data_type === "weekly composite of model predictions";
  $("mapframe").className = pred ? "pred" : "";
  $("stamp").textContent = LABEL[l.data_type] || l.data_type;
  $("stamp").className = BADGE[l.data_type] || l.data_type;
  $("mapimg").src = l.png_url;
  $("mapimg").alt = `${l.title} (${l.data_type})`;
  $("caption").innerHTML = `<b>${esc(l.title)}</b> · ${esc(period(l.period))} · units: ${esc(l.units)}`
    + (pred ? ` · issued ${esc(l.issue_date)} · model ${esc(state.data.model_version)}` : "");
  const s = l.style;
  $("ramp").style.background = `linear-gradient(90deg, ${s.colors.join(",")})`;
  $("ticks").innerHTML = s.vmin == null ? "<span>auto (2nd–98th percentile)</span>"
    : [s.vmin, (s.vmin + s.vmax) / 2, s.vmax].map((v) => `<span>${fmt(v, s.vmax - s.vmin <= 5 ? 1 : 0)}</span>`).join("");
}

function renderMeta(d) {
  const s = d.summary || {};
  const unc = s.uncertainty ? (s.uncertainty.validated ? "validated interval available" : "not shown (coverage not validated)") : "n/a";
  const rows = d.product === "sar" ? [["Composite", d.forecast_id], ["Week", `${s.week_start} … ${s.week_end}`], ["Acquisitions", s.n_acquisitions],
    ["Observed area", `${fmt(s.observed_area_km2_nominal / 1e6, 2)} × 10⁶ km² (nominal)`], ["Model", d.model_version]] :
    [["Forecast", d.forecast_id], ["Issued", s.issue_time_utc || d.issue_date], ["Target week", `${s.target_start} … ${s.target_end}`],
    ["Model", d.model_version || s.model_version], ["Uncertainty", unc]];
  const warn = (s.input_quality?.warnings || []).map((w) => `<p class="warn">⚠ ${esc(w)}</p>`).join("");
  $("meta").innerHTML = `<h2>${d.product === "sar" ? "Weekly composite" : "Forecast"}</h2><dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl>${warn}`;
}

function renderSummary(d) {
  const s = d.summary || {};
  if (d.product === "sar") {
    $("summary").innerHTML = `<table><tr><th>2 km cells</th><th>count</th></tr><tr><td>weekly ice (≥ 2/3 of looks)</td><td>${fmt(s.cells_weekly_ice, 0)}</td></tr>
      <tr><td>weekly water (≤ 1/3)</td><td>${fmt(s.cells_weekly_water, 0)}</td></tr><tr><td>variable</td><td>${fmt(s.cells_variable, 0)}</td></tr>
      <tr><td>observed</td><td>${fmt(s.observed_cells, 0)}</td></tr></table><p class="note">${esc(s.methodology)}</p>`;
  } else if (d.product === "sic") {
    const km = (v) => fmt(v / 1e6, 2);
    $("summary").innerHTML = `<table><tr><th>Extent (10⁶ km²)</th><th>value</th></tr>
      <tr><td>Forecast</td><td>${km(s.extent_km2)}</td></tr><tr><td>Persistence</td><td>${km(s.persistence_extent_km2)}</td></tr>
      <tr><td>Climatology</td><td>${km(s.climatology_extent_km2)}</td></tr></table>
      <table><tr><th>Sector</th><th>forecast</th><th>persistence</th></tr>${(s.sectors || []).map((x) =>
        `<tr><td>${esc(x.sector.replace(/_/g, " "))}</td><td>${km(x.extent_km2)}</td><td>${km(x.persistence_extent_km2)}</td></tr>`).join("")}</table>`;
  } else {
    $("summary").innerHTML = `<table><tr><th>Region</th><th>T2m °C</th><th>anomaly</th><th>last week</th></tr>${(s.regions || []).map((x) =>
      `<tr><td>${esc(x.region.replace(/_/g, " "))}</td><td>${fmt(x.forecast_mean_t2m_degC, 1)}</td><td>${fmt(x.forecast_mean_anomaly_degC, 1)}</td>`
      + `<td>${fmt(x.last_week_observed_anomaly_degC, 1)}</td></tr>`).join("")}</table>`;
  }
  $("limits").innerHTML = (s.limitations || d.limitations || []).map((x) => `<li>${esc(x)}</li>`).join("");
}

async function renderMetrics(product) {
  try {
    const m = await getJSON(METRICS_URL[product]);
    if (product === "sar") {
      const row = (n, x) => `<tr><td>${esc(n.replace(/_/g, " "))}</td><td>${fmt(x.miou)}</td><td>${fmt(x.f1_ice)}</td><td>${fmt(x.boundary_f1_scene_mean)}</td></tr>`;
      $("metrics").innerHTML = `<table><tr><th>method</th><th>mIoU</th><th>F1 ice</th><th>boundary F1</th></tr>${Object.entries(m.metrics).map(([n, x]) => row(n, x)).join("")}</table>
        <p class="note">${esc(m.n_scenes)} test scenes, charts ${esc((m.charts || []).join(" … "))}; ${esc(m.label_source)}</p>`;
    } else if (product === "sic") {
      const row = (n, g) => `<tr><td>${esc(n.replace(/_/g, " "))}</td><td>${fmt(g.seasonal_ice_zone?.mae_pp)}</td><td>${fmt(g.all?.iiee_mean_km2 / 1e3, 0)}</td></tr>`;
      $("metrics").innerHTML = `<table><tr><th>method</th><th>SIZ MAE (pp)</th><th>IIEE (10³ km²)</th></tr>${Object.entries(m.metrics).map(([n, g]) => row(n, g)).join("")}</table>
        <p class="note">${esc(m.issue_dates)} weekly issue dates, ${esc((m.evaluation_period || []).join(" … "))}</p>`;
    } else {
      const row = (n, g) => `<tr><td>${esc(n.replace(/_/g, " "))}</td><td>${fmt(g.all?.area_weighted_mae_degC)}</td><td>${fmt(g.all?.area_weighted_rmse_degC)}</td><td>${fmt(g.all?.acc_pattern_mean)}</td></tr>`;
      $("metrics").innerHTML = `<table><tr><th>method</th><th>MAE °C</th><th>RMSE °C</th><th>ACC</th></tr>${Object.entries(m.metrics).map(([n, g]) => row(n, g)).join("")}</table>
        <p class="note">${esc(m.n_issue_dates)} weekly issue dates, ${esc((m.issue_dates || []).join(" … "))}; truth: ${esc(m.source)}</p>`;
    }
  } catch (e) {
    $("metrics").textContent = "Test metrics unavailable.";
  }
}

async function load(product) {
  state.product = product;
  document.querySelectorAll("#tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.product === product)));
  $("anompanel").hidden = product !== "anom";
  $("summaryhead").textContent = product === "anom" ? "This month" : product === "sar" ? "This composite" : "This forecast";
  if (product === "anom") return loadAnom();
  try {
    const d = await getJSON(`/layers/${product}/latest`);
    state.data = d;
    const rasters = d.layers.filter((l) => l.png_url);
    $("layers").innerHTML = rasters.map((l) => `<li><button data-id="${esc(l.id)}"><span class="badge ${esc(l.data_type)}">`
      + `${esc(LABEL[l.data_type] || l.data_type)}</span>${esc(l.title)}</button><a href="${esc(l.tif_url)}" download>GeoTIFF</a></li>`).join("");
    $("layers").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => showLayer(rasters.find((l) => l.id === b.dataset.id))));
    renderMeta(d);
    renderSummary(d);
    showLayer(rasters.find((l) => l.data_type === "model_prediction") || rasters[0]);
  } catch (e) {
    $("meta").innerHTML = `<p class="warn">No forecast layers available for this product (${esc(e.message)}).</p>`;
    $("layers").innerHTML = "";
    $("summary").innerHTML = "";
  }
  renderMetrics(product);
}

// tabs are linkable: /viewer/#sic, #t2m, #sar
const PRODUCTS = ["sic", "t2m", "sar", "anom"];
document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => { history.replaceState(null, "", `#${b.dataset.product}`); load(b.dataset.product); }));
window.addEventListener("hashchange", () => { const p = location.hash.slice(1); if (PRODUCTS.includes(p)) load(p); });
load(PRODUCTS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "sic");
