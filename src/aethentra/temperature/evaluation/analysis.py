"""ML-02 feature analysis (validation, selection-stage evidence) and final-model interpretation (test period, post-selection).

TreeSHAP: LightGBM ``pred_contrib`` / XGBoost ``pred_contribs`` (exact TreeSHAP), so the shap package is not required.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..models.anomaly_model import AnomalyModel
from ..paths import METRICS, load
from ..training.pipeline import CKPT, FINAL, TABLES, _dump, build_table, make_context, split_dates

OUT = METRICS / "analysis"


def shap_values(m: AnomalyModel, X: pd.DataFrame) -> np.ndarray:
    if m.kind == "lightgbm":
        return m.model.predict(X[m.features], pred_contrib=True, num_iteration=m.best_iteration)[:, :-1]
    if m.kind == "xgboost":
        import xgboost as xgb
        return m.model.get_booster().predict(xgb.DMatrix(X[m.features]), pred_contribs=True)[:, :-1]
    raise ValueError("TreeSHAP implemented for LightGBM / XGBoost")


def _rmse(p, y):
    return float(np.sqrt(np.mean((p - y) ** 2)))


def permutation_importance(m, X, rng, repeats=2) -> dict:
    y = X["target_anom"].to_numpy()
    base = _rmse(m.predict_anom(X), y)
    out = {}
    for f in m.features:
        inc = []
        for _ in range(repeats):
            Xp = X.copy()
            Xp[f] = rng.permutation(Xp[f].to_numpy())
            inc.append(_rmse(m.predict_anom(Xp), y) - base)
        out[f] = float(np.mean(inc))
    return {"baseline_rmse_degC": base, "rmse_increase_degC": dict(sorted(out.items(), key=lambda kv: -kv[1]))}


def _shap_block(m, X) -> dict:
    sv = pd.DataFrame(np.abs(shap_values(m, X)), columns=m.features)
    seas = X["season"].to_numpy()
    by = {s: sv[seas == s].mean().sort_values(ascending=False) for s in ["DJF", "MAM", "JJA", "SON"] if (seas == s).any()}
    ranks = pd.DataFrame({s: v.rank(ascending=False) for s, v in by.items()})
    return {"shap_mean_abs": sv.mean().sort_values(ascending=False).astype(float).to_dict(),
            "shap_top10_by_season": {s: list(v.index[:10]) for s, v in by.items()},
            "shap_rank_spread_across_seasons": (ranks.max(axis=1) - ranks.min(axis=1)).sort_values().astype(float).to_dict()}


def feature_analysis(n_rows: int = 200_000) -> dict:
    """Validation-period analysis of the untuned candidate LightGBM (used for documentation of the selection stage)."""
    rng = np.random.default_rng(load("training")["seed"])
    src = load("data_sources")["primary"]
    va = pd.read_parquet(TABLES / f"validation_{src}.parquet")
    va = va.sample(min(n_rows, len(va)), random_state=1)
    m = AnomalyModel.load(CKPT, "lgbm")
    names = m.features
    corr = va[names].corr(method="spearman")
    res = {"high_collinearity_pairs_abs_spearman_ge_0.9": sorted(
        [(a, b, float(corr.loc[a, b])) for i, a in enumerate(names) for b in names[i + 1:] if abs(corr.loc[a, b]) >= 0.9], key=lambda x: -abs(x[2])),
        "spearman_with_target_anomaly": {n: float(va[n].corr(va["target_anom"], method="spearman")) for n in names},
        "lightgbm_gain_importance": dict(sorted(zip(m.features, map(float, m.model.feature_importance("gain"))), key=lambda kv: -kv[1])),
        "permutation_importance_validation": permutation_importance(m, va.sample(60_000, random_state=2), rng)}
    res.update(_shap_block(m, va))
    _dump(res, OUT / "feature_analysis_validation.json")
    corr.to_csv(OUT / "spearman_correlation_validation.csv")
    return res


def final_interpretation(n_frac: float = 0.02) -> dict:
    """Post-selection interpretation of the FINAL model on test-period rows. No tuning or selection follows from it."""
    if not (METRICS / "test_final" / "summary.json").exists():
        raise RuntimeError("run the single test evaluation first")
    cfg = load("training")
    ctx = make_context()
    te = build_table(ctx, split_dates("test"), n_frac, cfg["seed"] + 2, "test_sample")
    m = AnomalyModel.load(FINAL, "final_model")
    rng = np.random.default_rng(cfg["seed"])
    X = te.sample(min(150_000, len(te)), random_state=3)
    y = X["target_anom"].to_numpy()
    p = m.predict_anom(X)
    res = {"rows": len(X), "permutation_importance_test": permutation_importance(m, X.sample(min(50_000, len(X)), random_state=4), rng)}
    try:
        res.update(_shap_block(m, X))
    except ValueError as e:
        res["shap"] = str(e)
    # sensitivity to missing predictor groups (NaN as at inference when a source is unavailable)
    groups = {"atmosphere": [f for f in m.features if f.split("_")[0] in ("msl", "u10", "v10", "wspd", "d2m", "tcc", "z500", "t850")],
              "sea_ice": [f for f in m.features if f.startswith("sic_")],
              "lags_beyond_week1": [f for f in m.features if f in ("anom_w2", "anom_w3", "anom_w4", "anom_m8", "anom_tend", "anom_std_w4")]}
    sens = {}
    for g, fs in groups.items():
        if fs:
            Xm = X.copy(); Xm[fs] = np.nan
            sens[g] = {"features": fs, "rmse_full": _rmse(p, y), "rmse_missing": _rmse(m.predict_anom(Xm), y)}
    res["missing_predictor_sensitivity"] = sens
    # partial dependence of the top-4 SHAP features (on the test sample, median of others implicit)
    top = list(res.get("shap_mean_abs", {}) or res["permutation_importance_test"]["rmse_increase_degC"])[:4]
    pdp = {}
    for f in top:
        qs = np.nanquantile(X[f], np.linspace(0.02, 0.98, 15))
        sub = X.sample(min(5000, len(X)), random_state=5)
        vals = []
        for q in qs:
            s = sub.copy(); s[f] = q
            vals.append(float(m.predict_anom(s).mean()))
        pdp[f] = {"x": qs.tolist(), "mean_prediction_degC": vals}
    res["partial_dependence"] = pdp
    # residual analysis
    X = X.assign(pred=p, err=p - y)
    sig = np.array([ctx.sigma.for_date(t)[c] for t, c in zip(X["issue_date"], X["cell"])])
    z = y / sig
    X["z_obs"] = z
    bins = pd.cut(X["z_obs"], [-np.inf, -2, -1, 1, 2, np.inf], labels=["<-2s", "-2..-1s", "-1..1s", "1..2s", ">2s"])
    res["residual_by_observed_anomaly_class"] = X.groupby(bins, observed=True)["err"].agg(["mean", lambda e: float(np.sqrt(np.mean(e ** 2))), "size"]).rename(
        columns={"mean": "bias_degC", "<lambda_0>": "rmse_degC", "size": "n"}).to_dict(orient="index")
    eb = pd.cut(X["elevation_m"], [-1, 1, 500, 1500, 2500, 5000])
    res["residual_by_elevation_m"] = {str(k): {"bias_degC": float(g["err"].mean()), "rmse_degC": float(np.sqrt((g["err"] ** 2).mean())), "n": len(g)}
                                      for k, g in X.groupby(eb, observed=True)}
    res["residual_by_season"] = {s: {"bias_degC": float(g["err"].mean()), "rmse_degC": float(np.sqrt((g["err"] ** 2).mean()))} for s, g in X.groupby("season")}
    res["prediction_range_degC"] = [float(p.min()), float(p.max())]
    res["observed_range_degC"] = [float(y.min()), float(y.max())]
    res["fraction_predictions_beyond_observed_range"] = float(((p < y.min()) | (p > y.max())).mean())
    res["shrinkage_std_ratio_pred_over_obs"] = float(np.std(p) / np.std(y))
    _dump(res, OUT / "final_interpretation_test.json")
    return res


def spatial_smoothness(tag: str = "test_final") -> dict:
    """Mean absolute neighbour difference of forecast vs reanalysis anomaly fields (spatial-discontinuity check)."""
    ctx = make_context()
    fz = np.load(METRICS / tag / "fields.npz")
    out = {}
    for k in ("obs_anom", "final_model", "persistence"):
        v = []
        for i in range(0, fz[k].shape[0], 4):
            g = ctx.cube.to_grid(fz[k][i])
            dx, dy = np.abs(np.diff(g, axis=1)), np.abs(np.diff(g, axis=0))
            v.append((np.nanmean(dx) + np.nanmean(dy)) / 2)
        out[k] = float(np.mean(v))
    out["ratio_model_over_reanalysis"] = out["final_model"] / out["obs_anom"]
    _dump(out, OUT / "spatial_smoothness_test.json")
    return out
