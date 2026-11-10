"""Feature analysis (validation, candidate model) and interpretability / scientific checks (final model).

TreeSHAP values come from LightGBM's native ``pred_contrib`` (exact TreeSHAP), so the shap package is not required.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..config import EXPERIMENTS_DIR, load
from ..features.build import ATM_FEATURES, feature_names, issue_dates
from ..models.tree_models import TreeModel
from ..training.pipeline import CKPT, FINAL, METRICS, TABLES, _dump, build_table, make_context

OUT = METRICS / "analysis"


def _season(dates: pd.Series) -> pd.Series:
    seasons = load("evaluation")["seasons"]
    m2s = {m: s for s, ms in seasons.items() for m in ms}
    return (pd.to_datetime(dates) + pd.Timedelta(days=4)).dt.month.map(m2s)


def shap_values(model: TreeModel, X: pd.DataFrame) -> np.ndarray:
    if model.kind != "lightgbm":
        raise ValueError("native TreeSHAP implemented for LightGBM")
    return model.model.predict(X[model.features], pred_contrib=True, num_iteration=model.best_iteration)[:, :-1]


def permutation_importance(model: TreeModel, X: pd.DataFrame, rng, repeats: int = 2) -> dict:
    y = X["target"].to_numpy()
    base = np.mean(np.abs(model.predict_sic(X) - y))
    out = {}
    for f in model.features:
        inc = []
        for _ in range(repeats):
            Xp = X.copy()
            Xp[f] = rng.permutation(Xp[f].to_numpy())
            inc.append(np.mean(np.abs(model.predict_sic(Xp) - y)) - base)
        out[f] = float(np.mean(inc))
    return {"baseline_mae_pp": float(base), "mae_increase_pp": dict(sorted(out.items(), key=lambda kv: -kv[1]))}


def feature_analysis(n_rows: int = 250_000) -> dict:
    """Validation-period analysis of the candidate LightGBM (selection-stage evidence)."""
    rng = np.random.default_rng(load("training")["seed"])
    va = pd.read_parquet(TABLES / "validation_fit1979-2015.parquet")
    va = va.sample(min(n_rows, len(va)), random_state=1)
    names = feature_names(True)
    names = [n for n in names if n in va.columns]
    m = TreeModel.load(CKPT, "lgbm_residual")
    res = {}
    corr = va[names].corr(method="spearman")
    pairs = [(a, b, float(corr.loc[a, b])) for i, a in enumerate(names) for b in names[i + 1:] if abs(corr.loc[a, b]) >= 0.9]
    res["high_collinearity_pairs_abs_spearman_ge_0.9"] = sorted(pairs, key=lambda x: -abs(x[2]))
    resid = va["target"] - va["persistence"]
    res["spearman_with_target_residual"] = {n: float(va[n].corr(resid, method="spearman")) for n in names}
    res["lightgbm_gain_importance"] = dict(sorted(zip(m.features, map(float, m.model.feature_importance("gain"))), key=lambda kv: -kv[1]))
    res["permutation_importance_validation"] = permutation_importance(m, va.sample(80_000, random_state=2), rng)
    sv = shap_values(m, va)
    mean_abs = pd.DataFrame(np.abs(sv), columns=m.features)
    res["shap_mean_abs_validation"] = mean_abs.mean().sort_values(ascending=False).astype(float).to_dict()
    seas = _season(va["issue_date"]).to_numpy()
    by = {s: mean_abs[seas == s].mean().sort_values(ascending=False) for s in ["DJF", "MAM", "JJA", "SON"]}
    res["shap_top10_by_season"] = {s: list(v.index[:10]) for s, v in by.items()}
    ranks = pd.DataFrame({s: v.rank(ascending=False) for s, v in by.items()})
    res["shap_rank_spread_across_seasons"] = (ranks.max(axis=1) - ranks.min(axis=1)).sort_values().astype(float).to_dict()
    _dump(res, OUT / "feature_analysis_validation.json")
    corr.to_csv(OUT / "spearman_correlation_validation.csv")
    return res


def final_interpretation(n_rows: int = 200_000) -> dict:
    """Post-selection interpretation of the FINAL model on test-period rows (no tuning or selection follows)."""
    cfg = load("training")
    t0, _ = cfg["splits"]["train"]
    _, v1 = cfg["splits"]["validation"]
    s0, s1 = cfg["splits"]["test"]
    ctx = make_context(t0, v1)
    names = feature_names(ctx.atmos is not None)
    te = build_table(ctx, issue_dates(s0, s1), 0.05, cfg["seed"] + 7, TABLES / "test_sample_fit1979-2020.parquet", names)
    te = te.sample(min(n_rows, len(te)), random_state=3)
    m = TreeModel.load(FINAL, "final_model")
    n_shap = 20_000                       # exact TreeSHAP is O(rows x trees x leaves x depth^2); 200k rows took > 40 min
    res = {"rows": len(te), "shap_rows": n_shap}
    sv = shap_values(m, te.iloc[:n_shap])
    res["shap_mean_abs_test"] = pd.Series(np.abs(sv).mean(0), index=m.features).sort_values(ascending=False).astype(float).to_dict()
    np.savez_compressed(OUT / "final_shap_sample.npz", shap=sv.astype(np.float32), X=te[m.features].to_numpy(np.float32)[:n_shap],
                        features=np.array(m.features))
    y = te["target"].to_numpy()
    raw = m.predict_sic(te, clip=False)
    res["pre_clip_below_0_fraction"] = float((raw < 0).mean())
    res["pre_clip_above_100_fraction"] = float((raw > 100).mean())
    res["pre_clip_min_max"] = [float(raw.min()), float(raw.max())]
    base = float(np.mean(np.abs(np.clip(raw, 0, 100) - y)))
    res["mae_pp_test_sample"] = base
    used_atm = [f for f in ATM_FEATURES if f in m.features]
    if used_atm:
        Xn = te.copy()
        Xn[used_atm] = np.nan
        res["sensitivity_missing_atmosphere_mae_pp"] = float(np.mean(np.abs(m.predict_sic(Xn) - y)))
    Xs = te.copy()
    for f in ["sic_w2", "sic_w3", "sic_w4", "sic_w8"]:
        Xs[f] = np.nan
    res["sensitivity_missing_older_sic_lags_mae_pp"] = float(np.mean(np.abs(m.predict_sic(Xs) - y)))
    # feature response (partial dependence) for top features
    pdp = {}
    top = list(res["shap_mean_abs_test"])[:6]
    sub = te.sample(5000, random_state=4)
    for f in top:
        if f == "sector":
            continue
        grid = np.nanpercentile(te[f], np.linspace(2, 98, 25))
        vals = []
        for g in grid:
            X = sub.copy(); X[f] = g
            vals.append(float(np.mean(m.predict_raw(X))))
        pdp[f] = {"grid": grid.tolist(), "mean_model_output": vals,
                  "output": "mean predicted residual over persistence (pp)" if m.target_mode == "residual" else "mean predicted SIC (%)"}
    res["partial_dependence"] = pdp
    # residual analysis by condition
    err = np.clip(raw, 0, 100) - y
    cond = pd.cut(y, [-0.1, 15, 80, 100.1], labels=["open_water", "marginal_ice", "pack_ice"])
    res["residual_by_condition"] = {str(k): {"bias_pp": float(err[cond == k].mean()), "mae_pp": float(np.abs(err[cond == k]).mean()),
                                             "n": int((cond == k).sum())} for k in cond.categories}
    _dump(res, OUT / "final_interpretation_test.json")
    return res


def spatial_checks() -> dict:
    """Physical plausibility of saved test grids: bounds, spatial roughness vs observations, regional bias."""
    z = np.load(METRICS / "test_final" / "grids.npz")
    obs = z["obs"].astype(np.float32)
    out = {}
    for k in [k for k in z.files if k not in ("dates", "obs")]:
        p = z[k].astype(np.float32)
        p = np.where(np.isfinite(obs), p, np.nan)
        gx = np.abs(np.diff(p, axis=2)); gy = np.abs(np.diff(p, axis=1))
        ox = np.abs(np.diff(obs, axis=2)); oy = np.abs(np.diff(obs, axis=1))
        out[k] = {"min": float(np.nanmin(p)), "max": float(np.nanmax(p)),
                  "mean_abs_neighbour_difference_pp": float(np.nanmean(np.concatenate([gx.ravel(), gy.ravel()]))),
                  "p99_abs_neighbour_difference_pp": float(np.nanpercentile(np.concatenate([gx.ravel(), gy.ravel()]), 99))}
    out["observed"] = {"mean_abs_neighbour_difference_pp": float(np.nanmean(np.concatenate([ox.ravel(), oy.ravel()]))),
                       "p99_abs_neighbour_difference_pp": float(np.nanpercentile(np.concatenate([ox.ravel(), oy.ravel()]), 99))}
    _dump(out, OUT / "spatial_checks_test.json")
    return out
