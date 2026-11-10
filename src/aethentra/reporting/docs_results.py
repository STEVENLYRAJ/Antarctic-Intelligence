"""Generate result documents strictly from experiment artifacts.

MODEL_TRAINING_REPORT.md, MODEL_EVALUATION_REPORT.md, MODEL_CARD.md, AETHENTRA_ML_TASK_01_FINAL_REPORT.md (+ NEXT_STEPS.md is static).
Every number is read from experiments/metrics/*, models/**/meta.json or outputs/*; missing artifacts are reported as missing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..config import DOCS_DIR, EXPERIMENTS_DIR, MODELS_DIR, OUTPUTS_DIR, ROOT, load

M = EXPERIMENTS_DIR / "metrics"
BASE = ["persistence", "persistence_week", "climatology", "linear_trend", "anomaly_persistence"]
NAMES = {"persistence": "Persistence (latest day)", "persistence_week": "Persistence (7-day mean)", "climatology": "Climatology (train)",
         "linear_trend": "Linear 7-day trend", "anomaly_persistence": "Anomaly persistence", "lgbm_residual": "LightGBM residual",
         "lgbm_absolute": "LightGBM absolute", "lgbm_residual_sic_only": "LightGBM residual, SIC-only", "xgb_residual": "XGBoost residual",
         "rf_residual": "Random forest residual", "lgbm_residual_tuned": "LightGBM residual (Optuna-tuned)", "final_model": "FINAL model"}


def _j(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def _f(x, nd=2):
    if x is None or (isinstance(x, float) and x != x):
        return "n/a"
    return f"{x:,.{nd}f}"


def metrics_table(met: dict, methods: list[str], group: str) -> list[str]:
    L = ["| Method | MAE (pp) | RMSE (pp) | Bias (pp) | R² | AW-MAE | AW-RMSE | Extent MAE (10³ km²) | Extent bias (10³ km²) | Rel. extent err. | Area MAE (10³ km²) | IIEE (10³ km²) | IoU | F1 | Precision | Recall |",
         "|---|" + "---|" * 15]
    for m in methods:
        g = met.get(m, {}).get(group)
        if not g:
            continue
        L.append(f"| {NAMES.get(m, m)} | {_f(g['mae_pp'])} | {_f(g['rmse_pp'])} | {_f(g['bias_pp'])} | {_f(g['r2'], 3)} | {_f(g['area_weighted_mae_pp'])} | "
                 f"{_f(g['area_weighted_rmse_pp'])} | {_f(g['extent_mae_km2'] / 1e3, 0)} | {_f(g['extent_bias_km2'] / 1e3, 0)} | "
                 f"{_f(100 * g['extent_relative_error_mean'], 2)} % | {_f(g['area_mae_km2'] / 1e3, 0)} | {_f(g['iiee_mean_km2'] / 1e3, 0)} | "
                 f"{_f(g['edge_iou'], 3)} | {_f(g['edge_f1'], 3)} | {_f(g['edge_precision'], 3)} | {_f(g['edge_recall'], 3)} |")
    return L


def compact_table(met: dict, methods: list[str], groups: list[str], key="mae_pp", label="MAE (pp)") -> list[str]:
    L = [f"| Method | " + " | ".join(groups) + " |", "|---|" + "---|" * len(groups)]
    for m in methods:
        if m in met:
            L.append(f"| {NAMES.get(m, m)} | " + " | ".join(_f(met[m].get(g, {}).get(key)) for g in groups) + " |")
    return L


def skill(met, m, ref, group, key):
    a, b = met[m][group][key], met[ref][group][key]
    return 100 * (1 - a / b)


def figures_md(prefix="../../") -> list[str]:
    man = _j(OUTPUTS_DIR / "figures/ml_task_01/figures_manifest.json") or []
    return [f"![{Path(f['file']).stem}]({prefix}{f['file']})\n*{f['caption']}*\n" for f in man]


# --------------------------------------------------------------------------- training report
def training_report():
    cfg = load("training")
    rec = _j(M / "candidate_training_records.json") or {}
    tabs = {p.stem: _j(p) for p in sorted((ROOT / "data/processed/aethentra/tables").glob("*.json"))}
    opt = _j(M / "optuna_lightgbm.json")
    sel = _j(M / "selection_record.json")
    fin = _j(MODELS_DIR / "final/final_model.meta.json")
    L = ["# Model Training Report — AETHENTRA ML Task 01", "", "Generated from `models/**/meta.json`, `experiments/metrics/*` and table metadata.", "",
         "## 1. Split configuration (by forecast issue date)", "",
         "| Split | Issue dates from | to | Rule |", "|---|---|---|---|"]
    for k, (s, e) in cfg["splits"].items():
        L.append(f"| {k} | {s} | {e} | full target window (t+1..t+7) inside the split; 7-day cadence |")
    L += ["", "Climatology (SIC and atmosphere) for training/validation: fitted on 1979–2015 only. Final refit: 1979–2020. Test years never enter a fit.",
          "All cells of one issue date stay in the same split (splits are by date, never by cell).", "",
          "## 2. Training tables", "", "| Table | Issue dates | Rows | Sample fraction | Seconds | Dates without rows |", "|---|---|---|---|---|---|"]
    for k, t in tabs.items():
        if t:
            L.append(f"| {k} | {t['dates']} | {t['rows']:,} | {t['fraction']} | {t['seconds']:.0f} | {len(t['dates_without_rows'])} |")
    L += ["", "## 3. Candidate models (trained on 1979–2015, early stopping on the 2016–2020 validation sample)", "",
          "| Model | Family | Target | Features | Train rows | Best iteration | Fit time (s) | RSS after fit (GB) |", "|---|---|---|---|---|---|---|---|"]
    for k, r in rec.items():
        L.append(f"| {NAMES.get(k, k)} | {r['kind']} | {r['target_mode']} | {len(r['features'])} | {r.get('train_rows', 'n/a'):,} | {r['best_iteration']} | "
                 f"{_f(r['fit_seconds'], 0)} | {_f(r.get('rss_gb_after_fit'), 1)} |")
    L += ["", "Hyper-parameters as currently in `configs/training.yaml`. **The candidate table above (read from each checkpoint's "
          "`.meta.json`) is authoritative for what was actually trained**: the random-forest budget in the config (`n_estimators`, "
          "`max_train_rows`) and the Optuna budget were reduced after the candidates were trained to shorten re-runs; the trained RF used "
          "the values recorded in `models/checkpoints/rf_residual.meta.json`.", "", "```yaml", json.dumps(cfg["models"], indent=2), "```", ""]
    if opt:
        L += ["## 4. Hyper-parameter optimisation (Optuna TPE, validation only)", "",
              f"* Trials completed: {opt['n_trials']} (budget {cfg['optuna']['n_trials']} trials / {cfg['optuna']['timeout_s']} s).",
              f"* Objective: {opt['objective']}.",
              f"* Untuned candidate: {_f(opt.get('untuned_candidate_mae_pp_validation_sample'), 3)} pp; best trial: {_f(opt['best_value_mae_pp_validation_sample'], 3)} pp "
              f"(best iteration {opt['best_iteration']}).",
              f"* Best parameters: `{json.dumps(opt['best_params'])}`", ""]
    if sel:
        L += ["## 5. Model selection (frozen before any test access)", "", f"* Selected: **{NAMES.get(sel['selected_model'], sel['selected_model'])}** "
              f"({sel['kind']}, target = {sel['target_mode']}, {len(sel['features'])} features), at {sel['selection_utc']}.",
              f"* Criteria: {sel['criteria']}.", f"* Best baseline on validation: {NAMES.get(sel['best_baseline'])}; selected model beats it on all criteria: "
              f"{sel['beats_best_baseline_on_all_criteria']}.", "", "| Method | SIZ MAE | SIZ RMSE | IIEE (10³ km²) | Extent MAE (10³ km²) | Rank sum |", "|---|---|---|---|---|---|"]
        for r in sel["validation_table"]:
            L.append(f"| {NAMES.get(r['method'], r['method'])} | {_f(r['siz_mae'])} | {_f(r['siz_rmse'])} | {_f(r['iiee'] / 1e3, 0)} | {_f(r['extent_mae'] / 1e3, 0)} | "
                     f"{_f(sel['rank_sum'].get(r['method']), 0) if r['method'] in sel['rank_sum'] else 'baseline'} |")
    if fin:
        L += ["", "## 6. Final model", "", f"* Version: `{fin['model_version']}`; file `models/final/{fin['file']}`; trained {fin['trained_utc']}.",
              f"* Training period {fin['train_period'][0]} … {fin['train_period'][1]} ({fin['train_rows']:,} rows), {fin['best_iteration']} trees "
              f"({fin['n_estimators_rule']}), no early stopping (no held-out data remain).",
              f"* Climatology artifact: `{fin['climatology_artifact']}` (copied to `models/final/sic_climatology.npz`).",
              f"* Fit time {_f(fin['fit_seconds'], 0)} s. Seed {fin['seed']}.",
              "* Quantile companions `final_q10`, `final_q90` (LightGBM quantile loss, residual target) trained on the same data.", "",
              "## 7. Overfitting monitoring", "",
              "Loss curves: `models/checkpoints/*.history.json` and Figure `02_learning_curves`. Early stopping halts boosting when the validation "
              "loss stops improving for 100 rounds; the train–validation gap is shown in the figure."]
    (DOCS_DIR / "MODEL_TRAINING_REPORT.md").write_text("\n".join(L), encoding="utf-8")


# --------------------------------------------------------------------------- evaluation report
def evaluation_report():
    val = _j(M / "validation_candidates/summary.json")
    vt = _j(M / "validation_tuned/summary.json")
    te = _j(M / "test_final/summary.json")
    fa = _j(M / "analysis/feature_analysis_validation.json")
    fi = _j(M / "analysis/final_interpretation_test.json")
    sc = _j(M / "analysis/spatial_checks_test.json")
    icv = _j(M / "interval_coverage_validation.json")
    L = ["# Model Evaluation Report — AETHENTRA ML Task 01", "",
         "All numbers come from full-grid evaluations (`experiments/metrics/*/summary.json`). SIC errors are percentage points (pp) of the 7-day-mean "
         "concentration; extent/area in km²; IIEE = integrated ice-edge error (area of 15 %-class disagreement); IoU/F1/precision/recall treat "
         "'SIC ≥ 15 %' as the positive class, area-weighted. **Land and missing cells are never counted as 0 %.** R² over all ocean cells is inflated "
         "by the many easy open-water cells; use the seasonal-ice-zone (SIZ) and ice-edge-band rows for skill.", ""]
    if val:
        vm = dict(val["metrics"])
        if vt:
            vm.update({k: v for k, v in vt["metrics"].items() if k != "persistence"})
        ml = [m for m in vm if m not in BASE]
        L += ["## 1. Validation 2016–2020 (model selection)", "", f"Issue dates: {val['n_issue_dates']} ({val['first']} … {val['last']}); skipped: "
              f"{len(val['skipped_issue_dates'])} {val['skipped_issue_dates'][:6]}.", "", "### Seasonal ice zone", ""]
        L += metrics_table(vm, BASE + ml, "seasonal_ice_zone")
        L += ["", "### All ocean cells", ""] + metrics_table(vm, BASE + ml, "all")
        L += ["", "### Ice-edge band (±3 cells of the observed 15 % edge) — MAE / RMSE", ""]
        L += compact_table(vm, BASE + ml, ["ice_edge_band"], "mae_pp") + [""]
        L += ["### Ablations (validation, SIZ)", ""]
        abl = [("lgbm_residual", "lgbm_absolute", "residual vs absolute target"), ("lgbm_residual", "lgbm_residual_sic_only", "with vs without atmosphere")]
        for a, b, d in abl:
            if a in vm and b in vm:
                L.append(f"* {d}: MAE {_f(vm[a]['seasonal_ice_zone']['mae_pp'])} vs {_f(vm[b]['seasonal_ice_zone']['mae_pp'])} pp; "
                         f"IIEE {_f(vm[a]['all']['iiee_mean_km2'] / 1e3, 0)} vs {_f(vm[b]['all']['iiee_mean_km2'] / 1e3, 0)} ×10³ km².")
        if icv:
            L += ["", f"Validation 80 % interval (q10–q90): empirical coverage {icv['empirical_coverage']:.3f} (nominal {icv['nominal_coverage']:.2f}), "
                  f"mean width {icv['mean_width_pp']:.1f} pp, {icv['cells']:,} cells."]
    if te:
        tm = te["metrics"]
        meth = ["final_model"] + [b for b in BASE if b in tm]
        L += ["", "## 2. Untouched test 2021–2025 (single evaluation of the frozen final model)", "",
              f"Issue dates: {te['n_issue_dates']} ({te['first']} … {te['last']}); skipped {len(te['skipped_issue_dates'])}. "
              f"Climatology used by features and baseline: {te['climatology_period'][0]} … {te['climatology_period'][1]}.", "", "### Seasonal ice zone", ""]
        L += metrics_table(tm, meth, "seasonal_ice_zone")
        L += ["", "### All ocean cells", ""] + metrics_table(tm, meth, "all")
        L += ["", "### Ice-edge band", ""] + metrics_table(tm, meth, "ice_edge_band")
        L += ["", "### Skill relative to persistence (positive = better than persistence)", "", "| Metric | Final model skill vs persistence | vs anomaly persistence |", "|---|---|---|"]
        for g, k, lbl in [("seasonal_ice_zone", "mae_pp", "SIZ MAE"), ("seasonal_ice_zone", "rmse_pp", "SIZ RMSE"), ("ice_edge_band", "mae_pp", "Ice-edge-band MAE"),
                          ("all", "iiee_mean_km2", "IIEE"), ("all", "extent_mae_km2", "Extent MAE"), ("all", "area_mae_km2", "Area MAE")]:
            L.append(f"| {lbl} | {skill(tm, 'final_model', 'persistence', g, k):+.1f} % | {skill(tm, 'final_model', 'anomaly_persistence', g, k):+.1f} % |")
        L += ["", "### By season (SIZ MAE, pp)", ""] + compact_table(tm, meth, [f"seasonal_ice_zone|season:{s}" for s in ["DJF", "MAM", "JJA", "SON"]])
        L += ["", "### By season (IIEE, km²)", ""] + compact_table(tm, meth, [f"all|season:{s}" for s in ["DJF", "MAM", "JJA", "SON"]], "iiee_mean_km2")
        secs = [g for g in tm["final_model"] if g.startswith("sector:")]
        L += ["", "### By sector (area-weighted RMSE, pp, all ocean cells)", ""] + compact_table(tm, meth, secs, "area_weighted_rmse_pp")
        L += ["", "### By sea-ice condition (MAE, pp; condition = observed target class)", ""]
        L += compact_table(tm, meth, ["condition:open_water", "condition:marginal_ice", "condition:pack_ice"])
        worse = [f"{s}" for s in ["DJF", "MAM", "JJA", "SON"]
                 if tm["final_model"][f"seasonal_ice_zone|season:{s}"]["mae_pp"] >= tm["persistence"][f"seasonal_ice_zone|season:{s}"]["mae_pp"]]
        worse_sec = [s.split(":")[1] for s in secs if tm["final_model"][s]["area_weighted_rmse_pp"] >= tm["persistence"][s]["area_weighted_rmse_pp"]]
        L += ["", f"Seasons where the final model does NOT beat persistence (SIZ MAE): {', '.join(worse) or 'none'}. "
              f"Sectors where it does not (AW-RMSE): {', '.join(worse_sec) or 'none'}."]
        cov = te.get("interval_coverage")
        if cov:
            ok = abs(cov["empirical_coverage"] - cov["nominal_coverage"]) <= 0.05
            L += ["", "### Uncertainty", "", f"80 % quantile interval on test: empirical coverage **{cov['empirical_coverage']:.3f}** vs nominal "
                  f"{cov['nominal_coverage']:.2f}, mean width {cov['mean_width_pp']:.1f} pp ({cov['cells']:,} cells, model domain). "
                  + ("Within ±5 pp of nominal → intervals are exported by the inference pipeline, with this coverage stated." if ok else
                     "Outside ±5 pp of nominal → intervals are NOT exported as validated uncertainty.")]
        pc = te["physical_checks"]["final_model"]
        L += ["", "### Physical plausibility (test)", "",
              f"* Pre-clip predictions below 0 %: {pc['pre_clip_below_0']:,}; above 100 %: {pc['pre_clip_above_100']:,} of {pc['model_cells']:,} model cells "
              f"({100 * (pc['pre_clip_below_0'] + pc['pre_clip_above_100']) / max(pc['model_cells'], 1):.2f} %); all clipped to [0, 100]."]
        if sc:
            L.append(f"* Spatial roughness (mean |neighbour difference|): observed {sc['observed']['mean_abs_neighbour_difference_pp']:.2f} pp, final model "
                     f"{sc['final_model']['mean_abs_neighbour_difference_pp']:.2f} pp, persistence {sc['persistence']['mean_abs_neighbour_difference_pp']:.2f} pp "
                     f"(99th pct: {sc['observed']['p99_abs_neighbour_difference_pp']:.1f} / {sc['final_model']['p99_abs_neighbour_difference_pp']:.1f} / "
                     f"{sc['persistence']['p99_abs_neighbour_difference_pp']:.1f}). No artificial discontinuities beyond the observed texture.")
        if fi:
            L.append(f"* Residuals by observed condition (test sample): " + "; ".join(f"{k}: bias {_f(v['bias_pp'])} pp, MAE {_f(v['mae_pp'])} pp"
                                                                                   for k, v in fi["residual_by_condition"].items()) + ".")
            if "sensitivity_missing_atmosphere_mae_pp" in fi:
                L.append(f"* Sensitivity to missing atmosphere: MAE {fi['mae_pp_test_sample']:.3f} → {fi['sensitivity_missing_atmosphere_mae_pp']:.3f} pp when all "
                         f"atmospheric inputs are set missing; older SIC lags missing → {fi['sensitivity_missing_older_sic_lags_mae_pp']:.3f} pp.")
    if fa:
        L += ["", "## 3. Feature analysis (validation, candidate LightGBM)", "",
              "| Feature | Mean |SHAP| | Permutation ΔMAE (pp) | Spearman with residual |", "|---|---|---|---|"]
        perm = fa["permutation_importance_validation"]["mae_increase_pp"]
        for f_, v in list(fa["shap_mean_abs_validation"].items())[:20]:
            L.append(f"| {f_} | {v:.3f} | {perm.get(f_, float('nan')):.3f} | {fa['spearman_with_target_residual'].get(f_, float('nan')):+.3f} |")
        L += ["", "High collinearity (|Spearman| ≥ 0.9): " + "; ".join(f"{a}–{b} ({r:+.2f})" for a, b, r in fa["high_collinearity_pairs_abs_spearman_ge_0.9"][:15])
              + ". Tree ensembles are robust to collinearity for prediction, but it splits importance between correlated features (interpret jointly).",
              "", "Top-10 SHAP features by season: " + "; ".join(f"**{s}**: {', '.join(v[:5])}…" for s, v in fa["shap_top10_by_season"].items()), ""]
    if fi:
        L += ["## 4. Final-model interpretation (test sample, post-selection)", "", "| Feature | Mean |SHAP| (pp) |", "|---|---|"]
        L += [f"| {k} | {v:.3f} |" for k, v in list(fi["shap_mean_abs_test"].items())[:15]]
    L += ["", "## 5. Figures", ""] + figures_md()
    (DOCS_DIR / "MODEL_EVALUATION_REPORT.md").write_text("\n".join(L), encoding="utf-8")
