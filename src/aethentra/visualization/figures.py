"""Evaluation figures generated from saved metrics/grids only -> outputs/figures/ml_task_01/."""
from __future__ import annotations

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..config import EXPERIMENTS_DIR, OUTPUTS_DIR, ROOT
from ..preprocessing.cube import Cube
from .style import BLUE_CMAP, DIVERGING, INK2, MUTED, OTHER, SERIES, apply_style

M = EXPERIMENTS_DIR / "metrics"
FIG = OUTPUTS_DIR / "figures" / "ml_task_01"
LABEL = {"persistence": "Persistence", "persistence_week": "Persistence (7-day mean)", "climatology": "Climatology",
         "linear_trend": "Linear trend", "anomaly_persistence": "Anomaly persistence", "lgbm_residual": "LightGBM (residual)",
         "lgbm_absolute": "LightGBM (absolute)", "lgbm_residual_sic_only": "LightGBM (SIC-only)", "xgb_residual": "XGBoost (residual)",
         "rf_residual": "Random forest", "lgbm_residual_tuned": "LightGBM tuned", "final_model": "Final model"}
MANIFEST = []


def _save(fig, name, caption):
    FIG.mkdir(parents=True, exist_ok=True)
    p = FIG / f"{name}.png"
    fig.savefig(p, dpi=160, bbox_inches="tight")
    plt.close(fig)
    MANIFEST.append({"file": p.relative_to(ROOT).as_posix(), "caption": caption})


def _metrics(tag):
    p = M / tag / "summary.json"
    return json.loads(p.read_text()) if p.exists() else None


def fig_validation_comparison():
    v = _metrics("validation_candidates")
    t = _metrics("validation_tuned")
    if not v:
        return
    met = dict(v["metrics"])
    if t:
        met.update({k: x for k, x in t["metrics"].items() if k != "persistence"})
    rows = [(k, g["seasonal_ice_zone"]["mae_pp"], g["seasonal_ice_zone"]["rmse_pp"], g["all"]["iiee_mean_km2"] / 1e3) for k, g in met.items()]
    df = pd.DataFrame(rows, columns=["m", "mae", "rmse", "iiee"]).sort_values("mae", ascending=False)
    fig, axs = plt.subplots(1, 3, figsize=(13, 0.42 * len(df) + 1.6), sharey=True)
    for a, col, xl in zip(axs, ["mae", "rmse", "iiee"], ["SIZ MAE (pp)", "SIZ RMSE (pp)", "Mean IIEE (10$^3$ km$^2$)"]):
        colors = [SERIES[0] if m not in ("persistence", "persistence_week", "climatology", "linear_trend", "anomaly_persistence") else OTHER
                  for m in df.m]
        a.barh([LABEL.get(m, m) for m in df.m], df[col], color=colors, height=0.6)
        for i, x in enumerate(df[col]):
            a.text(x, i, f" {x:.2f}" if col != "iiee" else f" {x:.0f}", va="center", fontsize=8, color=INK2)
        a.set_xlabel(xl); a.grid(axis="y", visible=False)
    axs[0].set_title("Validation 2016-2020 (grey = baselines)", loc="left")
    _save(fig, "01_validation_model_comparison", "Validation (2016-2020) full-grid comparison of baselines and ML candidates: MAE and RMSE "
          "over the seasonal ice zone (cells whose training climatology reaches 15 %) and mean integrated ice-edge error.")


def fig_learning_curves():
    fig, ax = plt.subplots(figsize=(8, 4))
    for i, n in enumerate(["lgbm_residual", "xgb_residual", "lgbm_residual_tuned"]):
        p = ROOT / "models" / "checkpoints" / f"{n}.history.json"
        if not p.exists():
            continue
        h = json.loads(p.read_text())
        for split, ls in (("train", ":"), ("valid", "-")):
            if split in h:
                k = list(h[split])[0]
                ax.plot(h[split][k], color=SERIES[i], ls=ls, lw=1.4, label=f"{LABEL[n]} {split}")
    ax.set_xlabel("Boosting iteration"); ax.set_ylabel("MAE of residual (pp)"); ax.set_yscale("log")
    ax.set_title("Training and validation loss"); ax.legend(fontsize=8)
    _save(fig, "02_learning_curves", "Training (dotted) and validation (solid) L1 loss of the boosted models on the sampled tables; "
          "early stopping at the validation minimum.")


def fig_test(cube: Cube):
    s = _metrics("test_final")
    if not s:
        return
    met = s["metrics"]
    order = ["final_model", "anomaly_persistence", "persistence", "persistence_week", "linear_trend", "climatology"]
    order = [m for m in order if m in met]
    df = pd.read_parquet(M / "test_final" / "per_date_sums.parquet")
    # extent time series
    a = df[df.group == "all"].pivot_table(index="issue_date", columns="method", values=["ext_obs", "ext_pred"])
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(a.index, a[("ext_obs", "final_model")] / 1e6, color=INK2, lw=2, label="Observed (CDR, 7-day mean field)")
    for i, m in enumerate(["final_model", "persistence", "climatology"]):
        ax.plot(a.index, a[("ext_pred", m)] / 1e6, color=SERIES[i], lw=1.1, label=LABEL[m], alpha=0.9 if i == 0 else 0.7)
    ax.set_ylabel("Sea-ice extent (10$^6$ km$^2$)"); ax.set_xlabel("Issue date")
    ax.set_title("Test 2021-2025: forecast vs observed weekly extent"); ax.legend(ncol=4, loc="upper left", fontsize=8)
    _save(fig, "03_test_extent_timeseries", "Weekly sea-ice extent (SIC >= 15 %) of the observed 7-day-mean field and of the forecasts "
          "for every test issue date.")
    # extent error
    fig, ax = plt.subplots(figsize=(12, 3.4))
    for i, m in enumerate(["final_model", "persistence"]):
        e = (a[("ext_pred", m)] - a[("ext_obs", m)]) / 1e3
        ax.plot(a.index, e, color=SERIES[i], lw=1, label=f"{LABEL[m]} (MAE {np.abs(e).mean():.0f}k km$^2$)")
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_ylabel("Extent error (10$^3$ km$^2$)"); ax.set_title("Test extent error (forecast - observed)"); ax.legend(fontsize=8)
    _save(fig, "04_test_extent_error", "Extent error per test issue date for the final model and persistence.")
    # seasonal performance
    fig, axs = plt.subplots(1, 2, figsize=(12, 4))
    seas = ["DJF", "MAM", "JJA", "SON"]
    w = 0.8 / len(order)
    for i, m in enumerate(order):
        for a_, key, yl in [(axs[0], "mae_pp", "SIZ MAE (pp)"), (axs[1], "iiee_mean_km2", "IIEE (10$^3$ km$^2$)")]:
            grp = "seasonal_ice_zone" if key == "mae_pp" else "all"
            vals = [met[m].get(f"{grp}|season:{s_}", {}).get(key, np.nan) for s_ in seas]
            if key == "iiee_mean_km2":
                vals = [x / 1e3 for x in vals]
            a_.bar(np.arange(4) + i * w - 0.4 + w / 2, vals, w, color=SERIES[i] if i < len(SERIES) else OTHER, label=LABEL[m])
            a_.set_xticks(range(4)); a_.set_xticklabels(seas); a_.set_ylabel(yl)
    axs[0].legend(fontsize=7.5); axs[0].set_title("Test error by austral season (target-window midpoint)")
    _save(fig, "05_test_seasonal_performance", "Test-period MAE (seasonal ice zone) and IIEE by season; DJF = austral summer melt minimum.")
    # sectors
    secs = [g for g in met["final_model"] if g.startswith("sector:")]
    fig, ax = plt.subplots(figsize=(10, 3.8))
    for i, m in enumerate(["final_model", "persistence", "anomaly_persistence"]):
        ax.bar(np.arange(len(secs)) + i * 0.27 - 0.27, [met[m][s_]["area_weighted_rmse_pp"] for s_ in secs], 0.27, color=SERIES[i], label=LABEL[m])
    ax.set_xticks(range(len(secs))); ax.set_xticklabels([s_.split(":")[1].replace("_", "-") for s_ in secs])
    ax.set_ylabel("Area-weighted RMSE (pp)"); ax.set_title("Test error by Southern Ocean sector (all ocean cells)"); ax.legend(fontsize=8)
    _save(fig, "06_test_sector_performance", "Area-weighted RMSE per sector (NSIDC sector definitions) over all valid ocean cells.")
    # grids: obs vs pred, error distribution, maps
    z = np.load(M / "test_final" / "grids.npz")
    obs = z["obs"].astype(np.float32)
    pred = z["final_model"].astype(np.float32)
    per = z["persistence"].astype(np.float32)
    m = np.isfinite(obs) & ((obs > 0) | (pred > 0) | (per > 0))
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.6))
    hb = axs[0].hexbin(obs[m], pred[m], gridsize=50, bins="log", cmap=BLUE_CMAP, mincnt=1)
    axs[0].plot([0, 100], [0, 100], color=SERIES[1], lw=1)
    axs[0].set_xlabel("Observed 7-day mean SIC (%)"); axs[0].set_ylabel("Forecast SIC (%)"); axs[0].set_title("Observed vs forecast (test, ice-relevant cells)")
    fig.colorbar(hb, ax=axs[0], label="Cells (log)")
    bins = np.linspace(-60, 60, 121)
    for i, (nm, p_) in enumerate([("final_model", pred), ("persistence", per)]):
        axs[1].hist((p_ - obs)[m], bins=bins, histtype="step", lw=1.5, color=SERIES[i], label=LABEL[nm], density=True)
    axs[1].set_yscale("log"); axs[1].set_xlabel("Forecast - observed (pp)"); axs[1].set_ylabel("Density (log)")
    axs[1].set_title("Error distribution (test)"); axs[1].legend()
    _save(fig, "07_test_obs_vs_pred_error_dist", "Left: joint distribution of observed and forecast SIC on cells where any of observation, "
          "forecast or persistence is non-zero. Right: error distributions of the final model and persistence.")
    em = np.load(M / "test_final" / "error_maps.npz")
    ocean = cube.ocean
    fig, axs = plt.subplots(1, 2, figsize=(12, 5.2))
    a0 = np.where(ocean, em["mae_final_model"], np.nan)
    im = axs[0].imshow(a0, cmap=BLUE_CMAP, vmin=0, vmax=np.nanpercentile(a0, 99))
    fig.colorbar(im, ax=axs[0], shrink=0.75, label="MAE (pp)"); axs[0].set_title("Final model MAE per cell (test)")
    gain = np.where(ocean, em["mae_persistence"] - em["mae_final_model"], np.nan)
    lim = np.nanpercentile(np.abs(gain), 99)
    im = axs[1].imshow(gain, cmap=DIVERGING, vmin=-lim, vmax=lim)
    fig.colorbar(im, ax=axs[1], shrink=0.75, label="MAE reduction vs persistence (pp)")
    axs[1].set_title("Improvement over persistence (blue = better)")
    for a_ in axs:
        a_.imshow(np.ma.masked_where(ocean, np.ones(ocean.shape)), cmap="Greys", vmin=0, vmax=3, alpha=0.6)
        a_.set_xticks([]); a_.set_yticks([]); a_.grid(False)
    _save(fig, "08_test_spatial_error_maps", "Per-cell mean absolute error of the final model over all test issue dates and its reduction relative "
          "to persistence (native EPSG:3412 grid; grey = land/coast).")
    # example map: observed vs forecast with edges
    k = int(np.argmin([abs((pd.Timestamp(str(d)) - pd.Timestamp("2023-09-10")).days) for d in z["dates"]]))
    fig, axs = plt.subplots(1, 3, figsize=(15, 5))
    for a_, f, ttl in zip(axs, [obs[k], pred[k], pred[k] - obs[k]], ["Observed (target week)", "Final model forecast", "Forecast - observed"]):
        if ttl.startswith("Forecast -"):
            im = a_.imshow(np.where(ocean, f, np.nan), cmap=DIVERGING, vmin=-40, vmax=40)
            fig.colorbar(im, ax=a_, shrink=0.7, label="pp")
        else:
            im = a_.imshow(np.where(ocean, f, np.nan), cmap=BLUE_CMAP, vmin=0, vmax=100)
            fig.colorbar(im, ax=a_, shrink=0.7, label="SIC (%)")
        a_.contour(np.where(ocean, np.nan_to_num(obs[k]), 100), [15], colors=[INK2], linewidths=0.8)
        a_.imshow(np.ma.masked_where(ocean, np.ones(ocean.shape)), cmap="Greys", vmin=0, vmax=3, alpha=0.6)
        a_.set_title(ttl); a_.set_xticks([]); a_.set_yticks([]); a_.grid(False)
    d0 = pd.Timestamp(str(z["dates"][k]))
    fig.suptitle(f"Issue {d0.date()} -> target {(d0 + pd.Timedelta(days=1)).date()}..{(d0 + pd.Timedelta(days=7)).date()} "
                 "(black line = observed 15 % edge)", fontsize=10)
    _save(fig, "09_test_example_map", "Example test forecast near the 2023 record-low winter maximum: observed target-week mean SIC, "
          "forecast and difference, with the observed 15 % ice edge.")


def fig_interpretation():
    p = M / "analysis" / "final_interpretation_test.json"
    q = M / "analysis" / "feature_analysis_validation.json"
    if p.exists():
        r = json.loads(p.read_text())
        s = pd.Series(r["shap_mean_abs_test"]).head(15)[::-1]
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.barh(s.index, s.values, color=SERIES[0], height=0.6)
        ax.set_xlabel("Mean |SHAP| (pp of residual)"); ax.set_title("Final model: TreeSHAP importance (test sample)"); ax.grid(axis="y", visible=False)
        _save(fig, "10_final_shap_importance", "Mean absolute TreeSHAP contribution of the 15 most influential features of the final model "
              "on a random sample of test-period cells.")
        pdp = r.get("partial_dependence", {})
        if pdp:
            n = len(pdp)
            fig, axs = plt.subplots(1, n, figsize=(3.2 * n, 3.2))
            for a_, (f, d) in zip(np.atleast_1d(axs), pdp.items()):
                a_.plot(d["grid"], d["mean_model_output"], color=SERIES[0], marker="o", ms=3)
                a_.set_xlabel(f); a_.axhline(0, color=MUTED, lw=0.7)
            np.atleast_1d(axs)[0].set_ylabel("Mean predicted change vs\npersistence (pp)")
            fig.suptitle("Feature response (partial dependence), final model", fontsize=10)
            _save(fig, "11_feature_response", "Partial dependence of the predicted change relative to persistence on the top features.")
    if q.exists():
        r = json.loads(q.read_text())
        s = pd.Series(r["permutation_importance_validation"]["mae_increase_pp"]).head(15)[::-1]
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.barh(s.index, s.values, color=SERIES[0], height=0.6)
        ax.set_xlabel("MAE increase when permuted (pp)"); ax.set_title("Permutation importance (validation, candidate LightGBM)")
        ax.grid(axis="y", visible=False)
        _save(fig, "12_permutation_importance_validation", "Increase in MAE when each feature is randomly permuted (validation sample, "
              "candidate LightGBM trained on 1979-2015).")


def fig_optuna():
    p = M / "optuna_lightgbm.json"
    if not p.exists():
        return
    r = json.loads(p.read_text())
    v = [t["value"] for t in r["trials"]]
    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.plot(range(len(v)), v, "o", color=SERIES[0], ms=4, label="Trial")
    ax.plot(range(len(v)), np.minimum.accumulate(v), color=SERIES[1], label="Best so far")
    if "untuned_candidate_mae_pp_validation_sample" in r:
        ax.axhline(r["untuned_candidate_mae_pp_validation_sample"], color=MUTED, ls="--", label="Untuned candidate")
    ax.set_xlabel("Trial"); ax.set_ylabel("Validation-sample MAE (pp)"); ax.set_title("Optuna search (LightGBM, validation only)"); ax.legend()
    _save(fig, "13_optuna_history", "Optuna TPE trials: validation-sample MAE of each configuration and the running best.")


def make_all():
    apply_style()
    MANIFEST.clear()
    cube = Cube()
    for f in (fig_validation_comparison, fig_learning_curves, fig_optuna, lambda: fig_test(cube), fig_interpretation):
        f()
    (FIG / "figures_manifest.json").write_text(json.dumps(MANIFEST, indent=2))
    return MANIFEST
