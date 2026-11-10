"""MODEL_CARD.md and AETHENTRA_ML_TASK_01_FINAL_REPORT.md generated from artifacts (narrative statements are computed)."""
from __future__ import annotations

import json
from pathlib import Path

from ..config import DOCS_DIR, EXPERIMENTS_DIR, MODELS_DIR, OUTPUTS_DIR, ROOT, load
from .addendum import cnn_status, ncep_lines, viewer_lines
from .docs_results import BASE, NAMES, _f, _j, compact_table, figures_md, metrics_table, skill

M = EXPERIMENTS_DIR / "metrics"


def _latest_forecast():
    s = sorted((OUTPUTS_DIR / "forecasts").glob("sic7d_*/sic7d_*.json"))
    s = [p for p in s if not p.name.endswith(".geojson")]
    return json.loads(s[-1].read_text()) if s else None


def model_card():
    fin = _j(MODELS_DIR / "final/final_model.meta.json")
    te = _j(M / "test_final/summary.json")
    sel = _j(M / "selection_record.json")
    if not (fin and te):
        return
    tm = te["metrics"]
    f, p = tm["final_model"], tm["persistence"]
    cov = te.get("interval_coverage") or {}
    L = ["# Model Card — AETHENTRA Antarctic Weekly Sea-Ice Concentration Forecast", "",
         f"**Version** `{fin['model_version']}` · **Family** {fin['kind']} gradient-boosted trees ({fin['best_iteration']} trees) · "
         f"**Selected candidate** {NAMES.get(fin['selected_from'], fin['selected_from'])} · **Trained** {fin['trained_utc']}", "",
         "## Intended use", "",
         "* One-week-ahead outlook of Antarctic sea-ice concentration for scientific exploration and visualisation in AETHENTRA.",
         "* **Not** for navigation, operational ice services, or decisions affecting safety. Not a substitute for official ice charts.", "",
         "## What it predicts", "",
         "* Output: mean SIC (%) over days t+1…t+7 for every ocean cell of the NSIDC 25 km polar-stereographic grid (EPSG:3412), issued at the end of day t.",
         "* Derived: sea-ice extent and area (km²) with the 15 % threshold, hemispheric and per sector.",
         f"* Internally the model predicts the change relative to persistence ({fin['target_mode']} target); output is clipped to [0, 100].", "",
         "## Inputs", "",
         "* Daily NOAA/NSIDC CDR v6 SIC for days t−55…t (+ CDR uncertainty for t−6…t); training-period climatology (1979–2020).",
         "* Past-week NCEP/NCAR R1 near-surface air temperature, winds and sea-level pressure (interim substitute for ERA5).",
         f"* {len(fin['features'])} features — see FEATURE_ENGINEERING.md. Input schema: `src/aethentra/inference/prediction_schema.py`.", "",
         "## Training data", "", f"* Issue dates {fin['train_period'][0]} … {fin['train_period'][1]} (weekly), {fin['train_rows']:,} sampled cell-weeks.",
         "* Hyper-parameters selected on 2016–2020 validation only; test 2021–2025 used once.", "",
         "## Performance on the untouched test period (2021–2025)", "",
         "| Metric | Final model | Persistence | Skill vs persistence |", "|---|---|---|---|"]
    for g, k, lbl, scale in [("seasonal_ice_zone", "mae_pp", "SIZ MAE (pp)", 1), ("seasonal_ice_zone", "rmse_pp", "SIZ RMSE (pp)", 1),
                             ("ice_edge_band", "mae_pp", "Ice-edge-band MAE (pp)", 1), ("all", "area_weighted_rmse_pp", "Area-weighted RMSE, all ocean (pp)", 1),
                             ("all", "extent_mae_km2", "Extent MAE (10³ km²)", 1e3), ("all", "area_mae_km2", "Area MAE (10³ km²)", 1e3),
                             ("all", "iiee_mean_km2", "IIEE (10³ km²)", 1e3)]:
        L.append(f"| {lbl} | {_f(f[g][k] / scale)} | {_f(p[g][k] / scale)} | {skill(tm, 'final_model', 'persistence', g, k):+.1f} % |")
    L += [f"| Ice-edge IoU (≥15 %) | {_f(f['all']['edge_iou'], 3)} | {_f(p['all']['edge_iou'], 3)} | |", ""]
    if cov:
        ok = abs(cov["empirical_coverage"] - cov["nominal_coverage"]) <= 0.05
        L += ["## Uncertainty", "", f"80 % quantile interval: test coverage {cov['empirical_coverage']:.3f} (nominal {cov['nominal_coverage']:.2f}) → "
              + ("exported with the forecast." if ok else "**not** exported (calibration not verified)."), ""]
    worse = [s for s in ["DJF", "MAM", "JJA", "SON"]
             if f[f"seasonal_ice_zone|season:{s}"]["mae_pp"] >= p[f"seasonal_ice_zone|season:{s}"]["mae_pp"]]
    L += ["## Limitations and known failure modes", "",
          "* Errors are largest in the marginal ice zone and during rapid advance/retreat; see seasonal and ice-edge tables in MODEL_EVALUATION_REPORT.md.",
          f"* Seasons where it does not beat persistence on SIZ MAE: {', '.join(worse) or 'none'}.",
          "* Passive-microwave SIC underestimates concentration over melt ponds / wet snow in summer and over thin ice; the model inherits these biases.",
          "* No forecast of the target-week weather is used; extreme wind events during the target week are not anticipated.",
          "* 2.5° atmospheric inputs cannot resolve coastal polynya winds; ERA5 (0.25°) is the recommended upgrade.",
          "* The 2021–2025 test period includes record-low Antarctic sea ice (2023); performance in other regimes may differ.",
          "* Statistical skill ≠ physical validity: the model has no explicit dynamics or thermodynamics. **Independent review by a sea-ice scientist is required before public scientific use.**", "",
          "## Ethical / communication notes", "",
          "* Forecast layers are labelled `data_type = model_prediction` and must be visually distinct from observations in the UI.",
          "* Always display issue time, target period, model version and data source with the forecast."]
    (DOCS_DIR / "MODEL_CARD.md").write_text("\n".join(L), encoding="utf-8")


def final_report():
    cm = _j(ROOT / "data/interim/aethentra/cube_meta.json") or {}
    dq = _j(OUTPUTS_DIR / "reports/data_validation/data_quality.json") or {}
    fin = _j(MODELS_DIR / "final/final_model.meta.json")
    sel = _j(M / "selection_record.json")
    val = _j(M / "validation_candidates/summary.json")
    vt = _j(M / "validation_tuned/summary.json")
    te = _j(M / "test_final/summary.json")
    opt = _j(M / "optuna_lightgbm.json")
    rec = _j(M / "candidate_training_records.json") or {}
    tests = _j(EXPERIMENTS_DIR / "logs/pytest_summary.json")
    fc = _latest_forecast()
    cfg = load("training")
    L = ["# AETHENTRA ML Task 01 — Final Report", "## Antarctic Weekly Sea-Ice Concentration & Extent Forecasting", "",
         "Status legend: **COMPLETED** = implemented, executed and verified; **IMPLEMENTED** = code exists and tested but not executed on real data; "
         "**NOT DONE** = documented gap.", "",
         "## 1. Scientific objective", "",
         "Forecast the 7-day-mean Antarctic sea-ice concentration for days t+1…t+7 on the native 25 km grid, and derive sea-ice extent and area "
         "(15 % threshold). Definitions: SCIENTIFIC_PROBLEM_DEFINITION.md.", "",
         "## 2. Datasets actually acquired and verified coverage", ""]
    if cm:
        L += [f"* **NOAA/NSIDC SIC CDR v6 (G02202)** — {len(cm['inputs'])} files, {sum(1 for i in cm['inputs'] if i.get('md5_verified'))} MD5-verified; "
              f"daily {cm['start']} … {cm['end']} ({cm['days_present']:,} days in files, {cm['days_missing']} absent); "
              f"{dq.get('days_in_file_but_all_ocean_missing', 'n/a')} days are entirely fill.",
              f"* **NCEP/NCAR R1 daily** air/uwnd/vwnd/slp south of 35°S — coverage "
              + ", ".join(f"{v}: {c['first']}…{c['last']}" for v, c in dq.get("atmosphere", {}).get("coverage", {}).items()) + ".",
              "* Comparison: NSIDC Sea Ice Index v4 daily extent (Stage 1).", "* **Not acquired:** ERA5 (CDS token), Copernicus Marine products (account), NSIDC-0803 (Earthdata login).", ""]
    L += ["## 3. Preprocessing performed", "",
          "Native-grid daily cube (no regridding of labels), static ocean mask from the CDR surface-type mask, exact cell areas, explicit gaps, "
          "per-day QA statistics, independent extent cross-check, NCEP bilinear interpolation to cell centres. Details: DATA_QUALITY_REPORT.md.", "",
          "## 4. Features used", "", f"{len(fin['features']) if fin else 'n/a'} features (SIC history, train-only climatology/anomalies, spatial context, "
          "hemispheric state, season, past-week atmosphere). FEATURE_ENGINEERING.md.", "",
          "## 5. Splits", "", "| Split | Issue dates | Climatology fit |", "|---|---|---|",
          f"| Train | {cfg['splits']['train'][0]} … {cfg['splits']['train'][1]} | 1979–2015 |",
          f"| Validation | {cfg['splits']['validation'][0]} … {cfg['splits']['validation'][1]} | 1979–2015 |",
          f"| Test (once) | {cfg['splits']['test'][0]} … {cfg['splits']['test'][1]} | 1979–2020 (final refit) |", "",
          "## 6. Models actually trained", "", "| Model | Status | Checkpoint |", "|---|---|---|"]
    for k, r in rec.items():
        L.append(f"| {NAMES.get(k, k)} | COMPLETED (trained, checkpoint verified, validated) | `models/checkpoints/{r['file']}` |")
    if (MODELS_DIR / "checkpoints/lgbm_residual_tuned.meta.json").exists():
        L.append("| LightGBM residual (Optuna-tuned) | COMPLETED | `models/checkpoints/lgbm_residual_tuned.lgb.txt` |")
    if fin:
        L.append(f"| **Final model** ({NAMES.get(fin['selected_from'])}, refit 1979–2020) | COMPLETED | `models/final/{fin['file']}` |")
    L += [f"| U-Net (spatial deep learning, addendum) | {cnn_status('ml01')[0]} | {'`models/checkpoints/cnn_unet_residual.pt`' if (MODELS_DIR / 'checkpoints' / 'cnn_unet_residual.pt').exists() else '—'} |", ""]
    L += ["### U-Net addendum", ""] + cnn_status("ml01")[1] + [""]
    if opt:
        L += [f"Optuna: {opt['n_trials']} trials; best validation-sample MAE {_f(opt['best_value_mae_pp_validation_sample'], 3)} pp vs "
              f"{_f(opt.get('untuned_candidate_mae_pp_validation_sample'), 3)} pp untuned. Hyper-parameters: MODEL_TRAINING_REPORT.md.", ""]
    if val:
        vm = dict(val["metrics"])
        if vt:
            vm.update({k: v for k, v in vt["metrics"].items() if k != "persistence"})
        L += ["## 7. Baseline and candidate results (validation 2016–2020, seasonal ice zone)", ""]
        L += compact_table(vm, BASE + [m for m in vm if m not in BASE], ["seasonal_ice_zone", "ice_edge_band"], "mae_pp")
        L += ["", "(MAE in pp; full metric tables in MODEL_EVALUATION_REPORT.md.)", ""]
    if sel:
        L += [f"**Selection:** {NAMES.get(sel['selected_model'])} — {sel['criteria']}; beats the best baseline ({NAMES.get(sel['best_baseline'])}) on all "
              f"criteria: {sel['beats_best_baseline_on_all_criteria']}. Recorded {sel['selection_utc']} before the test evaluation.", ""]
    if te:
        tm = te["metrics"]
        L += ["## 8. Final test metrics (2021–2025, evaluated once)", "", "### Seasonal ice zone", ""]
        L += metrics_table(tm, ["final_model"] + [b for b in BASE if b in tm], "seasonal_ice_zone")
        L += ["", "### All ocean cells", ""] + metrics_table(tm, ["final_model"] + [b for b in BASE if b in tm], "all")
        L += ["", f"Final model vs persistence: SIZ MAE {skill(tm, 'final_model', 'persistence', 'seasonal_ice_zone', 'mae_pp'):+.1f} %, "
              f"IIEE {skill(tm, 'final_model', 'persistence', 'all', 'iiee_mean_km2'):+.1f} %, extent MAE {skill(tm, 'final_model', 'persistence', 'all', 'extent_mae_km2'):+.1f} % "
              "(positive = improvement).", ""]
        cov = te.get("interval_coverage")
        if cov:
            L.append(f"80 % interval coverage on test: {cov['empirical_coverage']:.3f} (nominal {cov['nominal_coverage']:.2f}).")
    L += ["", "## 9. Visualizations", ""] + figures_md()
    if fc:
        L += ["## 10. Latest forecast produced by the inference pipeline", "",
              f"* Forecast `{fc['forecast_id']}` issued {fc['issue_date']} for {fc['target_start']} … {fc['target_end']} (model {fc['model_version']}).",
              f"* Extent {fc['extent_km2'] / 1e6:.2f} × 10⁶ km², area {fc['area_km2'] / 1e6:.2f} × 10⁶ km² (persistence extent "
              f"{fc['persistence_extent_km2'] / 1e6:.2f}, climatology {fc['climatology_extent_km2'] / 1e6:.2f}).",
              f"* Inputs: latest observation {fc['input_quality']['latest_observation_date']}, persistence coverage "
              f"{fc['input_quality']['persistence_coverage_fraction']:.1%}, atmosphere used: {fc['input_quality']['atmosphere_used']}. "
              f"Warnings: {fc['input_quality']['warnings'] or 'none'}.",
              f"* Uncertainty validated: {fc['uncertainty']['validated']} — {fc['uncertainty']['note']}",
              f"* Files: `outputs/forecasts/{fc['forecast_id']}/` ({', '.join(fc['files'].values())}) and `layers/` for the frontend.", ""]
    L += ["## 11. Limitations", "", "See MODEL_CARD.md (failure modes) and MISSING_PREREQUISITES.md. Key points: interim 2.5° atmosphere instead of ERA5; "
          "passive-microwave biases; no target-week weather; 2021–2025 includes record lows; expert review pending.", ""] + ncep_lines() + ["",
          "## 12. Reproducibility", "", "REPRODUCIBILITY_GUIDE.md lists every command; all numbers in this report were generated by `scripts/build_docs.py` from artifacts.", ""]
    if tests:
        L += [f"Tests: {tests['passed']} passed, {tests['failed']} failed, {tests['skipped']} skipped ({tests['when']})."]
    L += ["", "## 13. Integration status", "",
          "* Inference pipeline (`src/aethentra/inference/`) — COMPLETED: NetCDF + JSON + GeoJSON outputs.",
          "* FastAPI service (`api/main.py`: /health, /model/info, POST /forecast/weekly, /forecast/latest, /forecast/history, /forecast/metrics, "
          "/forecast/metadata, file download by logical name, /layers/…) — COMPLETED and tested (TestClient + live uvicorn on 127.0.0.1); not a production deployment.",
          "* Frontend layers (`outputs/forecasts/<id>/layers/`: EPSG:3412 GeoTIFFs, EPSG:4326 PNG overlays with bounds, GeoJSON edges, extent time "
          "series, regional summary, manifest with data_type labels) — COMPLETED."] + viewer_lines() + ["",
          "## 14. Recommended next research direction", "", "See NEXT_STEPS.md."]
    (DOCS_DIR / "AETHENTRA_ML_TASK_01_FINAL_REPORT.md").write_text("\n".join(L), encoding="utf-8")
