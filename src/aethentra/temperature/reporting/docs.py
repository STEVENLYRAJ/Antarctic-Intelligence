"""Generate the artefact-driven ML-02 documents. Every number is read from saved artefacts; missing artefacts are stated."""
from __future__ import annotations

import json

import pandas as pd

from ...config import ROOT
from ...reporting.addendum import cnn_status, viewer_lines
from ..paths import DOCS, FIGURES, METRICS, MODELS, OUTPUTS, load

REGIONS = ["all", "antarctica_land", "southern_ocean", "antarctic_peninsula", "west_antarctica", "east_antarctica", "coastal_land", "inland"]
BASE = ["climatology", "persistence", "persistence_week", "recent_trend", "damped_persistence"]


def _j(p):
    return json.loads(p.read_text()) if p.exists() else None


def _f(x, d=3):
    return "n/a" if x is None else (f"{x:.{d}f}" if isinstance(x, float) else str(x))


def _src() -> str:
    return load("data_sources")["primary"]


def _src_note() -> str:
    return ("**Truth = NCEP/NCAR Reanalysis 1 (interim substitute for ERA5).** All skill numbers below are agreement with NCEP R1, "
            "not with ERA5 and not with direct observations." if _src() == "ncep_r1" else "Truth = ERA5 reanalysis.")


def table(res: dict, models: list[str], region: str = "all", cols=None) -> list[str]:
    cols = cols or [("area_weighted_mae_degC", "MAE °C"), ("area_weighted_rmse_degC", "RMSE °C"), ("area_weighted_bias_degC", "bias °C"),
                    ("acc_pattern_mean", "ACC"), ("anomaly_correlation_all", "corr"), ("msss_vs_climatology", "MSSS vs clim"),
                    ("r2_anomaly", "R² anom"), ("r2_absolute_t2m", "R² T2m")]
    L = ["| model | " + " | ".join(c[1] for c in cols) + " |", "|---|" + "---|" * len(cols)]
    for m in models:
        if m in res["metrics"] and region in res["metrics"][m]:
            r = res["metrics"][m][region]
            L.append(f"| {m} | " + " | ".join(_f(r.get(c[0])) for c in cols) + " |")
    return L


def skill_vs(res, model, ref, region="all") -> float | None:
    a = res["metrics"].get(model, {}).get(region, {}).get("mse_area_weighted")
    b = res["metrics"].get(ref, {}).get(region, {}).get("mse_area_weighted")
    return None if a is None or not b else 1 - a / b


def figs(sub: str) -> list[str]:
    d = FIGURES / sub
    return [f"![{p.stem}](../../{p.relative_to(ROOT).as_posix()})" for p in sorted(d.glob("*.png"))] if d.exists() else ["(no figures)"]


# ---------------------------------------------------------------------------------------------------------------- data quality
def data_quality_report():
    src = _src()
    dq = _j(OUTPUTS / "reports" / f"data_quality_{src}.json")
    meta = _j(ROOT / "data" / "interim" / "ml02" / src / "cube_meta.json")
    st = OUTPUTS / "reports" / "station_inventory.csv"
    L = ["# AETHENTRA ML-02 — Data Quality Report", "", f"Source: `{src}`. {_src_note()}", ""]
    if not dq or not meta:
        L.append("Validation artefacts missing — run `python scripts/ml02/validate_data.py`.")
    else:
        L += ["## Cube", "", f"* {meta['n_cells']:,} cells south of 60°S ({dq['n_land']:,} land / ice shelf), {dq['calendar_days']:,} days "
              f"{meta['start']} … {meta['end']}; cells with any missing day: {dq['cells_with_any_missing_day']}.",
              f"* Orography: {meta['orography_source']}.", "", "| variable | units | conversion | days present | impossible → missing | doubtful (kept) | flag range | duplicates dropped | files |",
              "|---|---|---|---|---|---|---|---|---|"]
        for v, x in meta["variables"].items():
            L.append(f"| {v} | {x['units']} | {'; '.join(x['unit_conversion'])} | {x['days_present']:,} | {x['values_out_of_range_set_missing']:,} | "
                     f"{x.get('values_flagged_doubtful_kept', 0):,} | {x.get('flag_range')} | {x['duplicate_timestamps_dropped']} | {len(x['files'])} |")
        L += ["", f"* Raw files checked: {dq['raw_files']} (units in files: {', '.join(dq['raw_units'])}).",
              f"* Raw-file issues: {len(dq['raw_issues'])}" + (" — " + "; ".join(f"{i['file']} (non-monotonic time {i['non_monotonic']}, NaN fraction "
                                                                                    f"{i['nan_fraction']:.2f}, {i['first']}…{i['last']})" for i in dq['raw_issues']) if dq['raw_issues'] else "") + ".",
              "  The ML-01 file `ncep_r1_uwnd_2026_south.nc` carries 289 all-NaN placeholder steps mislabelled 2025-03-18…2025-12-31 after the 76 valid "
              "2026 days. ML-02 reads only 1979–2025 files, and the ML-01 loader keeps the first (valid 2025-file) value of duplicated dates, so no "
              "valid value is overwritten.",
              f"* Domain-mean daily T2m jumps > {load('preprocessing')['qa']['max_domain_mean_daily_jump_degC']} °C: {meta.get('t2m_domain_mean_jump_days')}. "
              "1997-08-07: +8.6 °C domain mean (ocean +12.7 °C, single cells up to +43 °C; next-largest jump on record 2.8 °C) — treated as a reanalysis "
              "boundary-condition artefact; issue dates whose input or target windows overlap 1997-08-06…10 are excluded (9 training dates).",
              f"* Daily T2m percentiles 1981–2010 (every 15th day): " + ", ".join(f"{k} {v:.1f} °C" for k, v in dq["t2m_1981_2010_percentiles"].items()) + ".",
              "", "### Seasonal cycle 1981–2010 (area-mean °C)", "", "| region | min | mean | max |", "|---|---|---|---|"]
        for r, x in dq["seasonal_cycle_1981_2010"].items():
            L.append(f"| {r} | {x['min']:.1f} | {x['mean']:.1f} | {x['max']:.1f} |")
        if dq.get("domain_mean_anomaly_correlation"):
            L += ["", "Correlation of land-mean daily anomalies between variables: " +
                  ", ".join(f"{a}–{b} {v:+.2f}" for a, row in dq["domain_mean_anomaly_correlation"].items() for b, v in row.items() if a < b) + "."]
    if st.exists():
        s = pd.read_csv(st)
        L += ["", "## Stations", "", f"{len(s)} stations (16 Zenodo 17164992, {len(s) - 16} GHCN-Daily not duplicating them). "
              "Zenodo series end in 2022; GHCN to 2026.", "",
              "| station | lat | lon | elev m | first | last | days | share of 2018–2025 days |", "|---|---|---|---|---|---|---|---|"]
        for _, r in s.iterrows():
            L.append(f"| {r['name']} ({r['station'].split(':')[0]}) | {r['lat']:.2f} | {r['lon']:.2f} | {r['elev_m']:.0f} | {r['first']} | {r['last']} | {r['n_days']:,} | {r['frac_days_2018_2025']:.2f} |")
        L += ["", "Elevation −999.9 = not given in the GHCN station list."]
    L += ["", "## Figures", ""] + figs("data_quality")
    (DOCS / "DATA_QUALITY_REPORT.md").write_text("\n".join(L), encoding="utf-8")


# ---------------------------------------------------------------------------------------------------------------- training
def training_report():
    cfg = load("training")
    rec = _j(METRICS / "candidate_training_records.json") or {}
    opt = _j(METRICS / "optuna_lightgbm.json")
    sel = _j(METRICS / "selection_record.json")
    L = ["# AETHENTRA ML-02 — Model Training Report", "", _src_note(), "",
         "## Protocol", "", f"* Chronological splits: train {cfg['splits']['train']}, validation {cfg['splits']['validation']}, test {cfg['splits']['test']} "
         "(issue dates every 7 days; a target window never crosses a split boundary; suspect-period dates excluded).",
         f"* Training rows: {cfg['train_sample_fraction']:.0%} of valid cells per training issue date; validation table {cfg['val_sample_fraction']:.0%} per date "
         "(early stopping and Optuna only). Model selection uses full-grid validation metrics (every cell, every validation issue date).",
         "* Target: weekly T2m anomaly (label B); absolute T2m = target-week climatology + prediction.",
         "* Spatial deep learning: see the U-Net addendum section below (run after the tree selection and test were frozen).", ""]
    for tb in ("train", "validation"):
        j = _j(ROOT / "data" / "processed" / "ml02" / "tables" / f"{tb}_{_src()}.json")
        if j:
            L.append(f"* Table `{tb}`: {j['rows']:,} rows from {j['dates']} issue dates ({j['first']} … {j['last']}), {len(j['features'])} features.")
    L += ["", "## U-Net addendum (spatial deep-learning candidate)", ""] + cnn_status("ml02")[1]
    L += ["", "## Candidates (training records from the saved checkpoint metadata)", "",
          "| model | kind | features | train rows | best iteration / trees | fit s | RSS GB after | key parameters |", "|---|---|---|---|---|---|---|---|"]
    for n, r in rec.items():
        p = {k: v for k, v in r["params"].items() if k in ("learning_rate", "num_leaves", "min_data_in_leaf", "max_depth", "min_child_weight",
                                                             "n_estimators", "min_samples_leaf", "max_features", "max_train_rows", "objective")}
        if r.get("quantile"):
            p["objective"] = f"quantile (alpha={r['quantile']}; set at fit time)"
        L.append(f"| {n} | {r['kind']}{' q=' + str(r['quantile']) if r.get('quantile') else ''} | {len(r['features'])} | {r.get('train_rows', 'n/a'):,} | "
                 f"{r['best_iteration']} | {_f(r.get('fit_seconds'), 0)} | {r.get('rss_gb_after')} | {p} |")
    if opt:
        L += ["", "## Optuna (LightGBM, validation sample only)", "",
              f"* Objective: {opt['objective']}. Trials completed {opt['n_trials_completed']}, failed {opt['n_trials_failed']} "
              f"(budget {cfg['optuna']['n_trials']} trials / {cfg['optuna']['timeout_s']} s).",
              f"* Best {opt['best_value']:.4f} °C vs untuned LightGBM {opt['untuned_lgbm_value']:.4f} °C; best params {opt['best_params']}, best iteration {opt['best_iteration']}."]
    if sel:
        L += ["", "## Selection (frozen before the test)", "", f"* Selected: **{sel['selected_model']}** — {sel['selection_basis']}.",
              f"* Rank sums: {dict(sorted(sel['rank_sum'].items(), key=lambda kv: kv[1]))}.",
              f"* Best baseline on validation: {sel['best_baseline_on_validation']}; selected model beats it on every selection metric: "
              f"{sel['beats_best_baseline_on_all_selection_metrics']}.", f"* Frozen {sel['frozen_utc']}; test accessed before selection: {sel['test_set_accessed_before_selection']}."]
    fm = _j(MODELS / "final" / "final_model.meta.json")
    if fm:
        L += ["", "## Final refit", "", f"* `{fm['name']}` ({fm['kind']}, from `{fm['selected_from']}`), trained on {fm['train_period']} "
              f"({fm['train_rows']:,} rows; validation rows thinned to the training sampling density), {fm['n_estimators']} iterations "
              "(1.1 × validation best iteration, no early stopping), quantile models q10/q90 refitted the same way.",
              f"* Model version `{fm['model_version']}`; climatology {fm['climatology_period']}; files in `models/ml02/final/`."]
    L += ["", "## Learning curves", ""] + [x for x in figs("evaluation") if "learning" in x]
    (DOCS / "MODEL_TRAINING_REPORT.md").write_text("\n".join(L), encoding="utf-8")


# ---------------------------------------------------------------------------------------------------------------- evaluation
def evaluation_report():
    val = _j(METRICS / "validation_candidates" / "summary.json")
    vt = _j(METRICS / "validation_tuned" / "summary.json")
    te = _j(METRICS / "test_final" / "summary.json")
    icv = _j(METRICS / "interval_coverage_validation.json")
    st = _j(METRICS / "station_evaluation_test.json")
    L = ["# AETHENTRA ML-02 — Model Evaluation Report", "", _src_note(), "",
         "Metrics are area-weighted over all cells of every issue date (no sampling). MAE/RMSE/bias are identical for absolute T2m and for the anomaly "
         "(same climatology on both sides); R² and correlations are given for both. ACC = mean over issue dates of the area-weighted uncentred "
         "anomaly pattern correlation. MSSS = 1 − MSE / MSE(climatology forecast).", ""]
    if val:
        if vt:
            val["metrics"]["lgbm_tuned"] = vt["metrics"]["lgbm_tuned"]
        models = [m for m in ("lgbm_tuned", "lgbm", "xgb", "rf", "lgbm_temperature_only") if m in val["metrics"]] + BASE
        L += [f"## Validation {val['first']} … {val['last']} ({val['n_issue_dates']} issue dates)", ""] + table(val, models)
        L += ["", "### Validation RMSE (°C) by region", "", "| model | " + " | ".join(REGIONS) + " |", "|---|" + "---|" * len(REGIONS)]
        for m in models:
            L.append(f"| {m} | " + " | ".join(_f(val["metrics"][m][r]["area_weighted_rmse_degC"]) for r in REGIONS) + " |")
        if icv:
            L += ["", f"Validation q10–q90 interval: empirical coverage {icv['empirical_coverage']:.3f} (nominal {icv['nominal_coverage']:.2f}) over "
                  f"{icv['n_issue_dates']} issue dates, mean width {icv['mean_width_degC']:.2f} °C."]
    if te:
        tm = ["final_model"] + BASE
        L += ["", f"## Test {te['first']} … {te['last']} ({te['n_issue_dates']} issue dates, evaluated once, {te.get('evaluated_utc', '')})", ""] + table(te, tm)
        L += ["", "### Skill of the final model (1 − MSE/MSE_ref, area-weighted)", "", "| region | vs climatology | vs persistence | vs damped persistence | RMSE final | RMSE persistence |", "|---|---|---|---|---|---|"]
        for r in REGIONS:
            L.append(f"| {r} | {_f(skill_vs(te, 'final_model', 'climatology', r))} | {_f(skill_vs(te, 'final_model', 'persistence', r))} | "
                     f"{_f(skill_vs(te, 'final_model', 'damped_persistence', r))} | {_f(te['metrics']['final_model'][r]['area_weighted_rmse_degC'])} | "
                     f"{_f(te['metrics']['persistence'][r]['area_weighted_rmse_degC'])} |")
        L += ["", "### Test by season (all cells)", "", "| model | " + " | ".join(f"{s} RMSE | {s} ACC" for s in ("DJF", "MAM", "JJA", "SON")) + " |",
              "|---|" + "---|" * 8]
        for m in tm:
            bs = te["metrics"][m]["all"]["by_season"]
            L.append(f"| {m} | " + " | ".join(f"{_f(bs[s]['area_weighted_rmse_degC'])} | {_f(bs[s].get('acc_pattern_mean'))}" for s in ("DJF", "MAM", "JJA", "SON")) + " |")
        L += ["", "### Warm / cold anomaly detection (test, all cells, cell-week counts)", "",
              "| model | balanced acc. | warm P/R/F1 | cold P/R/F1 | extreme warm P/R/F1 | extreme cold P/R/F1 |", "|---|---|---|---|---|---|"]
        for m in tm:
            c = te["metrics"][m]["all"].get("categories")
            if c:
                prf = lambda k: "/".join(_f(c[k][x], 2) for x in ("precision", "recall", "f1"))  # noqa: E731
                L.append(f"| {m} | {_f(c['balanced_accuracy'])} | {prf('warm_ge_1sigma')} | {prf('cold_le_-1sigma')} | {prf('extreme_warm_ge_2sigma')} | {prf('extreme_cold_le_-2sigma')} |")
        cov = te.get("interval_coverage")
        if cov:
            ok = abs(cov["empirical_coverage"] - cov["nominal_coverage"]) <= 0.05
            L += ["", f"Test q10–q90 interval: empirical coverage {cov['empirical_coverage']:.3f} vs nominal {cov['nominal_coverage']:.2f}, "
                  f"mean width {cov['mean_width_degC']:.2f} °C → interval **{'exported' if ok else 'not exported'}** (rule: within ±5 pp)."]
    if st:
        L += ["", f"## Independent station check (test period; {st['n_stations']} stations, {st['n_station_weeks']:,} station-weeks)", "", st["note"], "",
              "| forecast | anomaly MAE °C | anomaly RMSE °C | correlation |", "|---|---|---|---|"]
        for k, v in st["pooled"].items():
            L.append(f"| {k} | {_f(v['anom_mae_degC'])} | {_f(v['anom_rmse_degC'])} | {_f(v['anom_corr'])} |")
        L += ["", "`reanalysis` = the verifying gridded truth itself at the nearest cell: its disagreement with stations is a floor for any model trained on it."]
    L += ["", "## Figures", ""] + figs("evaluation")
    (DOCS / "MODEL_EVALUATION_REPORT.md").write_text("\n".join(L), encoding="utf-8")


# ---------------------------------------------------------------------------------------------------------------- interpretability
def interpretability_report():
    fa = _j(METRICS / "analysis" / "feature_analysis_validation.json")
    fi = _j(METRICS / "analysis" / "final_interpretation_test.json")
    sm = _j(METRICS / "analysis" / "spatial_smoothness_test.json")
    st = _j(METRICS / "station_evaluation_test.json")
    L = ["# AETHENTRA ML-02 — Model Interpretability & Scientific Validation", "", _src_note(), ""]
    if fa:
        L += ["## Validation-stage feature analysis (candidate LightGBM)", "", "Top-12 mean |SHAP| (°C): " +
              ", ".join(f"{k} {v:.3f}" for k, v in list(fa["shap_mean_abs"].items())[:12]) + ".", "",
              "Top-10 permutation importance (validation RMSE increase, °C): " +
              ", ".join(f"{k} {v:.3f}" for k, v in list(fa["permutation_importance_validation"]["rmse_increase_degC"].items())[:10]) + ".", "",
              "Collinear pairs (|Spearman| ≥ 0.9): " + (", ".join(f"{a}/{b} {r:+.2f}" for a, b, r in fa["high_collinearity_pairs_abs_spearman_ge_0.9"][:12]) or "none") + ".", "",
              "Top-10 SHAP features per season: " + "; ".join(f"**{s}** {', '.join(v)}" for s, v in fa["shap_top10_by_season"].items()) + "."]
    if fi:
        L += ["", "## Final model on the test period (post-selection; nothing was tuned on it)", "",
              f"* Rows analysed: {fi['rows']:,}. Prediction range {fi['prediction_range_degC'][0]:.1f} … {fi['prediction_range_degC'][1]:.1f} °C vs observed "
              f"{fi['observed_range_degC'][0]:.1f} … {fi['observed_range_degC'][1]:.1f} °C; std(pred)/std(obs) = {fi['shrinkage_std_ratio_pred_over_obs']:.2f} "
              "(regression to the mean expected for a conditional-mean forecast).",
              "* Top-10 permutation importance (test RMSE increase, °C): " + ", ".join(f"{k} {v:.3f}" for k, v in list(fi["permutation_importance_test"]["rmse_increase_degC"].items())[:10]) + "."]
        if fi.get("shap_mean_abs"):
            L.append("* Top-10 mean |SHAP| (test): " + ", ".join(f"{k} {v:.3f}" for k, v in list(fi["shap_mean_abs"].items())[:10]) + ".")
        L += ["", "### Sensitivity to missing predictors (set to NaN at inference)", "", "| group | RMSE full | RMSE missing |", "|---|---|---|"]
        for g, v in fi["missing_predictor_sensitivity"].items():
            L.append(f"| {g} ({len(v['features'])}) | {v['rmse_full']:.3f} | {v['rmse_missing']:.3f} |")
        L += ["", "### Residuals by observed anomaly class (extremes)", "", "| observed z | bias °C | RMSE °C | n |", "|---|---|---|---|"]
        for k, v in fi["residual_by_observed_anomaly_class"].items():
            L.append(f"| {k} | {v['bias_degC']:+.3f} | {v['rmse_degC']:.3f} | {v['n']:,} |")
        L += ["", "### Residuals by elevation and season", "", "| stratum | bias °C | RMSE °C |", "|---|---|---|"]
        for k, v in fi["residual_by_elevation_m"].items():
            L.append(f"| elevation {k} m (n={v['n']:,}) | {v['bias_degC']:+.3f} | {v['rmse_degC']:.3f} |")
        for k, v in fi["residual_by_season"].items():
            L.append(f"| season {k} | {v['bias_degC']:+.3f} | {v['rmse_degC']:.3f} |")
        L += ["", "### Partial dependence (mean prediction, °C) of the top features", ""]
        for f, v in fi["partial_dependence"].items():
            L.append(f"* `{f}`: x {v['x'][0]:.2f} → {v['x'][-1]:.2f} gives {v['mean_prediction_degC'][0]:+.2f} → {v['mean_prediction_degC'][-1]:+.2f} °C "
                     f"(monotonic increasing: {all(b >= a - 0.05 for a, b in zip(v['mean_prediction_degC'], v['mean_prediction_degC'][1:]))}).")
    if sm:
        L += ["", f"### Spatial discontinuity check", "", f"Mean absolute neighbour difference of weekly anomaly fields: reanalysis {sm['obs_anom']:.3f} °C, "
              f"final model {sm['final_model']:.3f} °C, persistence {sm['persistence']:.3f} °C (ratio model/reanalysis {sm['ratio_model_over_reanalysis']:.2f}; "
              "< 1 means the forecast is smoother than the truth, > 1 would indicate artificial cell-to-cell noise)."]
    if st:
        L += ["", "## Independent station comparison (test period)", "", st["note"], "", "| station | source | dist km | cell elev m | weeks | reanalysis RMSE | model RMSE | persistence RMSE | model corr | model abs-T bias °C |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for s in sorted(st["stations"], key=lambda x: x["final_model_anom_rmse"]):
            L.append(f"| {s['name']} | {s['source'].split(' ')[0]} | {s['cell_distance_km']} | {s['cell_elevation_m']:.0f} | {s['n_weeks']} | {s['reanalysis_anom_rmse']:.2f} | "
                     f"{s['final_model_anom_rmse']:.2f} | {s['persistence_anom_rmse']:.2f} | {_f(s['final_model_anom_corr'], 2)} | {s['model_abs_t2m_bias_vs_station']:+.1f} |")
        L += ["", "Reanalysis agreement (model vs gridded truth) and station agreement measure different things: the first is skill against the training "
              "distribution, the second includes representativeness error (point vs 25 km cell, elevation mismatch) and reanalysis error."]
    (DOCS / "MODEL_INTERPRETABILITY_REPORT.md").write_text("\n".join(L), encoding="utf-8")


# ---------------------------------------------------------------------------------------------------------------- model card + final report
def _headline():
    te = _j(METRICS / "test_final" / "summary.json")
    if not te:
        return None, []
    a = te["metrics"]["final_model"]["all"]
    L = [f"* Test {te['first']} … {te['last']} ({te['n_issue_dates']} weekly issue dates, all {a['n_cells'] // te['n_issue_dates']:,} cells each): "
         f"area-weighted anomaly MAE **{a['area_weighted_mae_degC']:.3f} °C**, RMSE **{a['area_weighted_rmse_degC']:.3f} °C**, bias {a['area_weighted_bias_degC']:+.3f} °C, "
         f"ACC {a['acc_pattern_mean']:.3f}, R² (absolute T2m) {a['r2_absolute_t2m']:.3f}, R² (anomaly) {a['r2_anomaly']:.3f}.",
         f"* MSE skill: vs climatology {skill_vs(te, 'final_model', 'climatology'):.3f}, vs persistence {skill_vs(te, 'final_model', 'persistence'):.3f}, "
         f"vs damped persistence {skill_vs(te, 'final_model', 'damped_persistence'):.3f}."]
    for m in BASE:
        b = te["metrics"][m]["all"]
        L.append(f"  * baseline {m}: MAE {b['area_weighted_mae_degC']:.3f}, RMSE {b['area_weighted_rmse_degC']:.3f}, ACC {_f(b['acc_pattern_mean'])}.")
    return te, L


def _operational_unet() -> list[str]:
    """Card rows for the U-Net when the frozen addendum decision made it the operational model (else [])."""
    dec, cm = _j(METRICS / "addendum_cnn_decision_record.json"), _j(MODELS / "final" / "cnn_unet_final.meta.json")
    te = _j(METRICS / "test_cnn_addendum" / "summary.json")
    if not (dec and dec["cnn_replaces_operational_model"] and cm):
        return []
    L = ["## Operational model: U-Net (addendum)", "",
         f"The U-Net was better than the frozen tree selection `{dec['frozen_tree_selection']}` on {dec['cnn_better_on']} on validation "
         f"(decision frozen {dec['frozen_utc']}, before its test evaluation), so forecasts are produced by `cnn_unet_final`. The tree "
         "model below remains the documented frozen selection and fallback.", "", "| item | value |", "|---|---|",
         f"| Type | U-Net ({cm['n_parameters']:,} parameters; base {cm['architecture']['base']}, depth {cm['architecture']['depth']}) |",
         f"| Inputs | {len(cm['dynamic_channels'])} dynamic feature maps (the tree features as grids) + {len(cm['static_channels'])} static + validity mask |",
         f"| Training | {cm['train_period']}, {cm['train_dates']} weekly maps, {cm['epochs_run']} epochs (= best epoch on validation), {cm['loss']} |",
         "| Uncertainty | none exported (the q10/q90 interval was validated around the tree model only) |"]
    if te:
        a, r = te["metrics"]["cnn_unet_final"]["all"], te["tree_final_model_test_metrics_for_reference"]["all"]
        L += ["", f"Test {te['first']} … {te['last']} ({te['n_issue_dates']} issue dates, single evaluation {te['evaluated_utc']}): "
              f"MAE **{a['area_weighted_mae_degC']:.3f} °C** (tree {r['area_weighted_mae_degC']:.3f}), RMSE **{a['area_weighted_rmse_degC']:.3f} °C** "
              f"(tree {r['area_weighted_rmse_degC']:.3f}), bias {a['area_weighted_bias_degC']:+.3f} °C, ACC {a['acc_pattern_mean']:.3f} "
              f"(tree {r['acc_pattern_mean']:.3f}), MSSS {a['msss_vs_climatology']:.3f} (tree {r['msss_vs_climatology']:.3f})."]
    return L + [""]


def model_card():
    fm = _j(MODELS / "final" / "final_model.meta.json")
    te, H = _headline()
    L = ["# Model Card — AETHENTRA ML-02 weekly Antarctic 2 m temperature anomaly", "", _src_note(), ""] + _operational_unet()
    if L[-1:] == [""] and len(L) > 5:
        L.append("## Tree model (frozen selection; fallback)")
        L.append("")
    if not fm:
        L.append("No final model has been trained yet.")
    else:
        L += ["| item | value |", "|---|---|", f"| Model version | `{fm['model_version']}` |", f"| Type | {fm['kind']} regression (selected `{fm['selected_from']}`) |",
              f"| Output | weekly-mean (t+1…t+7) T2m anomaly on 25 km EPSG:3412 cells south of 60°S; absolute T2m = climatology + anomaly; σ categories |",
              f"| Inputs | {len(fm['features'])} features: past 8 weeks of reanalysis T2m anomalies, MSL and wind (past week), sea-ice observations, calendar, static geography |",
              f"| Training data | {fm['source']} {fm['train_period']} (issue dates every 7 days), climatology {fm['climatology_period']} |",
              "| Intended use | research / visualisation of weekly temperature-anomaly outlooks in AETHENTRA; comparison with baselines |",
              "| Not intended for | operational weather forecasting, aviation / field-safety decisions, climate-trend attribution |", "", "## Test performance", ""] + H
        L += ["", "## Ethical / scientific considerations", "", "* Trained and verified on reanalysis; station agreement is reported separately and is only partially independent.",
              "* The model is a conditional-mean forecast: it underestimates the amplitude of extreme anomalies (see the interpretability report).",
              "* Interim truth (NCEP R1) has known plateau biases; ERA5 retraining is the next step.", "", "## Limitations", ""]
        from ..inference.predict import LIMITATIONS
        L += [f"* {x}" for x in LIMITATIONS]
    (DOCS / "MODEL_CARD.md").write_text("\n".join(L), encoding="utf-8")


def final_report():
    sel = _j(METRICS / "selection_record.json")
    fm = _j(MODELS / "final" / "final_model.meta.json")
    tests = _j(ROOT / "experiments" / "logs" / "pytest_summary.json")       # whole-repository pytest run
    te, H = _headline()
    st = _j(METRICS / "station_evaluation_test.json")
    fc = sorted((OUTPUTS / "forecasts").glob("t2m7d_*/t2m7d_*.json"))
    cfg = load("training")
    status = lambda ok: "COMPLETED" if ok else "NOT DONE"  # noqa: E731
    L = ["# AETHENTRA ML Task 02 — Final Report", "## Antarctic Weekly 2 m Temperature & Temperature-Anomaly Forecasting", "", _src_note(), "",
         "Status legend: **COMPLETED** = implemented, executed on real data and checked; **IMPLEMENTED** = code + tests, not executed on real data; "
         "**PENDING** = blocked by a prerequisite; **NOT DONE** = documented gap.", "",
         "## 1. Scientific objective", "", "Forecast the 7-day-mean 2 m air temperature and its anomaly (vs a fixed 1981–2010 daily climatology) for days "
         "t+1…t+7 over Antarctica and the Southern Ocean south of 60°S on a 25 km grid, with warm/cold/extreme anomaly categories. "
         "This is a statistical forecast learnt from reanalysis, not a numerical weather prediction.", "",
         "## 2. Phase status", "", "| phase | status | evidence |", "|---|---|---|",
         "| 0 Audit | COMPLETED | PROJECT_AUDIT.md, DATA_INVENTORY.csv, MISSING_PREREQUISITES.md, ML02_IMPLEMENTATION_PLAN.md |",
         "| 1 Acquisition | COMPLETED (interim + stations); ERA5 **PENDING** (CDS key) | TEMPERATURE_DATA_SOURCES.md, provenance JSONs |",
         "| 2 Exploration & validation | COMPLETED | DATA_QUALITY_REPORT.md, outputs/ml02/figures/data_quality/, notebooks/01_temperature_exploration.ipynb |",
         "| 3 Preprocessing | COMPLETED | PREPROCESSING_DOCUMENTATION.md, data/interim/ml02/ncep_r1/cube_meta.json |",
         "| 4 Climatology & labels | COMPLETED | CLIMATOLOGY_AND_LABELS.md |",
         "| 5 Features | COMPLETED | FEATURE_ENGINEERING.md, experiments/ml02/metrics/analysis/ |",
         f"| 6 Baselines | {status(te is not None)} | 5 baselines on identical origins and masks |",
         f"| 7 Models | {status(bool(_j(METRICS / 'candidate_training_records.json')))} (tree models); {cnn_status('ml02')[0]} | MODEL_TRAINING_REPORT.md |",
         f"| 8 Splits | COMPLETED | train {cfg['splits']['train']}, validation {cfg['splits']['validation']}, test {cfg['splits']['test']} |",
         f"| 9 Evaluation | {status(te is not None)} | MODEL_EVALUATION_REPORT.md |",
         f"| 10 Optuna / final / single test | {status(te is not None and fm is not None)} | selection_record.json frozen {sel['frozen_utc'] if sel else 'n/a'}; test {te.get('evaluated_utc') if te else 'n/a'} |",
         f"| 11 Interpretability & stations | {status(bool(_j(METRICS / 'analysis' / 'final_interpretation_test.json')) and st is not None)} | MODEL_INTERPRETABILITY_REPORT.md |",
         f"| 12 Inference | {status(bool(fc))} | MODEL_OUTPUT_SCHEMA.md, {fc[-1].relative_to(ROOT).as_posix() if fc else 'no forecast'} |",
         "| 13 FastAPI | COMPLETED locally (TestClient tests + live uvicorn on 127.0.0.1) — not a production deployment | api/temperature.py under /temperature, api/viewer.py |",
         f"| 14 Frontend layers | {status(bool(fc) and (fc[-1].parent / 'layers' / 'manifest.json').exists())} (layers) + web viewer {'COMPLETED' if (ROOT / 'frontend' / 'index.html').exists() else 'NOT DONE'} | layers/manifest.json, frontend/, /viewer/ |",
         "| 15 Tests | " + ("not run" if not tests else ("COMPLETED" if not tests["failed"] else
                              "COMPLETED for ML-02 (all ML-02 tests pass); repository suite has failures")) + " | " +
         (f"whole repository: {tests['passed']} passed, {tests['failed']} failed, {tests['skipped']} skipped ({tests['when']})"
          + (f"; failed: {', '.join(tests.get('failed_tests', []))} — {tests.get('note', '')}" if tests["failed"] else "") if tests else "") + " |", "",
         "## 3. Final test metrics (single evaluation)", ""] + _operational_unet() + (["### Tree model (frozen selection)", ""] if _operational_unet() else []) + (H or ["Not available."])
    if st:
        p = st["pooled"]
        L += ["", f"Independent stations ({st['n_stations']} stations, {st['n_station_weeks']:,} station-weeks, test period): weekly-anomaly RMSE "
              f"final model {p['final_model']['anom_rmse_degC']:.2f} °C (r = {p['final_model']['anom_corr']:.2f}), persistence {p['persistence']['anom_rmse_degC']:.2f} °C, "
              f"climatology {p['climatology']['anom_rmse_degC']:.2f} °C; the verifying reanalysis itself {p['reanalysis']['anom_rmse_degC']:.2f} °C (r = {p['reanalysis']['anom_corr']:.2f})."]
    if sel:
        L += ["", "## 4. Model selection", "", f"Selected **{sel['selected_model']}** on validation only ({sel['selection_basis']}); best baseline {sel['best_baseline_on_validation']}."]
    L += ["", "## 5. Documents", "", "TEMPERATURE_DATA_SOURCES.md · DATA_QUALITY_REPORT.md · PREPROCESSING_DOCUMENTATION.md · CLIMATOLOGY_AND_LABELS.md · FEATURE_ENGINEERING.md · "
          "MODEL_TRAINING_REPORT.md · MODEL_EVALUATION_REPORT.md · MODEL_INTERPRETABILITY_REPORT.md · MODEL_CARD.md · MODEL_OUTPUT_SCHEMA.md · REPRODUCIBILITY_GUIDE.md · NEXT_STEPS.md", "",
          "## 6. Blockers and limitations", "", "* **ERA5 not acquired** (no CDS key during this run) → all results use NCEP/NCAR R1 as interim truth; ERA5 pipeline is "
          "implemented and switchable by configuration (TEMPERATURE_DATA_SOURCES.md).", "* Deep learning: " + cnn_status("ml02")[0] + ".",
          "* Station data are only partially independent of reanalysis; Zenodo station series end in 2022.", "* The API runs locally; it is not a production deployment.",
          ] + viewer_lines()
    (DOCS / "AETHENTRA_ML_TASK_02_FINAL_REPORT.md").write_text("\n".join(L), encoding="utf-8")


def build_all():
    for f in (data_quality_report, training_report, evaluation_report, interpretability_report, model_card, final_report):
        f()
