"""Training / validation / selection / final-refit / single test evaluation for AETHENTRA Task 01.

Stages (each writes verifiable artifacts and can be rerun independently):
  tables     training + validation tables (climatology fitted on TRAIN years only)
  candidates baselines + LightGBM / XGBoost / RF (+ ablations), full-grid validation evaluation
  tune       Optuna on validation data only
  select     freeze the final configuration (selection_record.json) BEFORE any test access
  final      refit on train+validation, climatology refitted on train+validation
  test       ONE evaluation of the frozen final model and the baselines on 2021-2025
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

from ..baselines.baselines import BASELINES, predict_baseline
from ..config import EXPERIMENTS_DIR, MODELS_DIR, PROCESSED_DIR, load, rel
from ..evaluation.metrics import Accumulator, edge_band, summarize_all
from ..features.atmosphere import Atmosphere
from ..features.build import FeatureContext, feature_names, issue_dates
from ..features.climatology import Climatology
from ..models.tree_models import TreeModel
from ..preprocessing.cube import Cube

LOG = logging.getLogger("aethentra.train")
ART = MODELS_DIR / "artifacts"
CKPT = MODELS_DIR / "checkpoints"
FINAL = MODELS_DIR / "final"
METRICS = EXPERIMENTS_DIR / "metrics"
TABLES = PROCESSED_DIR / "tables"


def _mem_gb():
    return psutil.Process(os.getpid()).memory_info().rss / 1e9


def _dump(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


# --------------------------------------------------------------------------- context
def make_context(fit_start: str, fit_end: str, with_atm: bool = True, cube: Cube | None = None) -> FeatureContext:
    cube = cube or Cube()
    ART.mkdir(parents=True, exist_ok=True)
    cpath = ART / f"sic_climatology_{fit_start[:4]}_{fit_end[:4]}.npz"
    if cpath.exists():
        clim = Climatology.load(cpath)
    else:
        LOG.info("Fitting SIC climatology on %s..%s", fit_start, fit_end)
        clim = Climatology.fit(cube, fit_start, fit_end, load("features")["climatology"]["window_half_width_days"])
        clim.save(cpath)
    atm = None
    if with_atm and load("features")["atmosphere"]["enabled"]:
        atm = Atmosphere.load(cube.grid["lat"], cube.grid["lon"])
        if atm is not None:
            atm.fit_climatology(fit_start, fit_end)
    return FeatureContext(cube, clim, atm)


def split_dates(name: str) -> pd.DatetimeIndex:
    s, e = load("training")["splits"][name]
    return issue_dates(s, e)


# --------------------------------------------------------------------------- tables
def build_table(ctx: FeatureContext, dates, frac: float, seed: int, path: Path, names: list[str]) -> pd.DataFrame:
    if path.exists():
        return pd.read_parquet(path)
    rng = np.random.default_rng(seed)
    parts, skipped = [], []
    t0 = time.time()
    for i, t in enumerate(dates):
        df, F, y = ctx.table(t, names, frac, rng)
        if df.empty:
            skipped.append(str(t.date()))
            continue
        parts.append(df.astype({c: np.float32 for c in names}))
        if i % 200 == 0:
            LOG.info("  table %s: %d/%d dates, %.0f s, mem %.1f GB", path.stem, i, len(dates), time.time() - t0, _mem_gb())
    tab = pd.concat(parts, ignore_index=True)
    n_inf = int(np.isinf(tab[names].to_numpy(np.float32)).sum())
    if n_inf:
        raise ValueError(f"{n_inf} infinite feature values in {path.name}; fix the feature code (NaN is the only allowed missing marker)")
    path.parent.mkdir(parents=True, exist_ok=True)
    tab.to_parquet(path, index=False)
    _dump({"dates": len(dates), "dates_without_rows": skipped, "rows": len(tab), "fraction": frac, "seed": seed,
           "seconds": time.time() - t0, "features": names}, path.with_suffix(".json"))
    return tab


def stage_tables():
    cfg = load("training")
    tr0, tr1 = cfg["splits"]["train"]
    ctx = make_context(tr0, tr1)
    names = feature_names(ctx.atmos is not None)
    tr = build_table(ctx, split_dates("train"), cfg["train_sample_fraction"], cfg["seed"], TABLES / "train_fit1979-2015.parquet", names)
    va = build_table(ctx, split_dates("validation"), cfg["val_sample_fraction"], cfg["seed"] + 1, TABLES / "validation_fit1979-2015.parquet", names)
    LOG.info("Tables: train %d rows, validation %d rows", len(tr), len(va))
    return tr, va, names


# --------------------------------------------------------------------------- evaluation over full grids
def evaluate_split(ctx: FeatureContext, dates, models: dict[str, TreeModel], baselines=tuple(BASELINES), tag: str = "",
                   save_grids: list[str] | None = None) -> dict:
    ev = load("evaluation")
    acc = Accumulator(ctx.ocean.shape)
    siz = ctx.clim.seasonal_ice_zone(ev["sic_threshold"]) & ctx.ocean
    sec = ctx.sector
    phys = {k: {"pre_clip_below_0": 0, "pre_clip_above_100": 0, "model_cells": 0} for k in models}
    grids = {m: [] for m in (save_grids or [])}
    obs_store, kept_dates, skipped = [], [], []
    t0 = time.time()
    for i, t in enumerate(dates):
        F = ctx.features(t)
        y, _ = ctx.target(t)
        valid = ctx.ocean & np.isfinite(y)
        if valid.sum() == 0 or np.isfinite(F["sic_d0"][ctx.ocean]).mean() < 0.5:
            skipped.append(str(t.date()))
            continue
        groups = {"all": valid, "seasonal_ice_zone": valid & siz, "ice_edge_band": valid & edge_band(y, ctx.ocean, ev["ice_edge_band_cells"])}
        for s, nm in enumerate(ctx.sector_names):
            groups[f"sector:{nm}"] = valid & (sec == s)
        for c, (lo, hi) in ev["conditions"].items():
            groups[f"condition:{c}"] = valid & (y >= lo) & (y < hi)
        preds = {b: predict_baseline(b, F) for b in baselines}
        active = ctx.active_mask(F)
        for name, mdl in models.items():
            preds[name], info = mdl.predict_grid(F, active)
            for k in info:
                phys[name][k] += info[k]
        for name, p in preds.items():
            acc.add(t, name, p, y, ctx.area, groups, ev["sic_threshold"])
            if name in grids:
                grids[name].append(p.astype(np.float16))
        if save_grids:
            obs_store.append(np.where(valid, y, np.nan).astype(np.float16))
        kept_dates.append(t)
        if i % 50 == 0:
            LOG.info("  eval %s: %d/%d dates %.0f s", tag, i, len(dates), time.time() - t0)
    df = acc.frame()
    h = load("features")["labels"]["horizon_days"]
    summary = summarize_all(df, ev["seasons"], h)
    out_dir = METRICS / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_dir / "per_date_sums.parquet", index=False)
    with np.errstate(invalid="ignore", divide="ignore"):
        maps = {f"mae_{k}": (v / acc.count_map).astype(np.float32) for k, v in acc.err_maps.items()}
        maps.update({f"bias_{k}": (v / acc.count_map).astype(np.float32) for k, v in acc.bias_maps.items()})
    np.savez_compressed(out_dir / "error_maps.npz", count=acc.count_map, **maps)
    if save_grids:
        np.savez_compressed(out_dir / "grids.npz", dates=np.array([str(d.date()) for d in kept_dates]), obs=np.stack(obs_store),
                            **{k: np.stack(v) for k, v in grids.items()})
    res = {"tag": tag, "n_issue_dates": len(kept_dates), "skipped_issue_dates": skipped, "first": str(kept_dates[0].date()),
           "last": str(kept_dates[-1].date()), "seconds": time.time() - t0, "physical_checks": phys, "metrics": summary,
           "climatology_period": list(ctx.clim.period)}
    _dump(res, out_dir / "summary.json")
    return res


# --------------------------------------------------------------------------- candidates
def train_candidates():
    cfg = load("training")
    seed = cfg["seed"]
    tr, va, names = stage_tables()
    sic_only = [n for n in names if n not in ("air_w1", "air_anom_w1", "uwnd_w1", "vwnd_w1", "wspd_w1", "slp_w1", "slp_anom_w1")]
    M = cfg["models"]
    specs = [
        ("lgbm_residual", "lightgbm", names, M["lightgbm"], "residual", None),
        ("lgbm_absolute", "lightgbm", names, M["lightgbm"], "absolute", None),
        ("lgbm_residual_sic_only", "lightgbm", sic_only, M["lightgbm"], "residual", None),
        ("xgb_residual", "xgboost", names, M["xgboost"], "residual", None),
        ("rf_residual", "random_forest", names, M["random_forest"], "residual", None),
    ]
    models, records = {}, {}
    for name, kind, feats, params, mode, q in specs:
        meta_f = CKPT / f"{name}.meta.json"
        if meta_f.exists():
            models[name] = TreeModel.load(CKPT, name)
            records[name] = json.loads(meta_f.read_text())
            LOG.info("Loaded existing checkpoint %s", name)
            continue
        LOG.info("Training %s (%s, %d features, %s)", name, kind, len(feats), mode)
        m0 = _mem_gb()
        mdl = TreeModel(kind, feats, params, mode, name, q)
        trd = tr
        if kind == "random_forest" and len(tr) > params["max_train_rows"]:
            trd = tr.sample(params["max_train_rows"], random_state=seed)
        mdl.fit(trd, va if kind != "random_forest" else None, seed=seed)
        rows = len(trd)
        records[name] = mdl.save(CKPT, {"train_rows": rows, "validation_rows": len(va), "train_period": cfg["splits"]["train"],
                                        "seed": seed, "rss_gb_after_fit": _mem_gb(), "rss_gb_before_fit": m0,
                                        "trained_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
        models[name] = TreeModel.load(CKPT, name)
        LOG.info("  %s: %.0f s, best_iteration=%s", name, mdl.fit_seconds, mdl.best_iteration)
    # quantile models for interval evaluation
    for q in load("evaluation")["quantiles"]:
        name = f"lgbm_q{int(q * 100):02d}"
        if not (CKPT / f"{name}.meta.json").exists():
            p = dict(M["lightgbm"]); p.pop("objective", None)
            mdl = TreeModel("lightgbm", names, p, "residual", name, q).fit(tr, va, seed=seed)
            mdl.save(CKPT, {"train_rows": len(tr), "quantile": q})
    _dump(records, METRICS / "candidate_training_records.json")
    tr0, tr1 = cfg["splits"]["train"]
    ctx = make_context(tr0, tr1)
    res = evaluate_split(ctx, split_dates("validation"), models, tag="validation_candidates")
    res_interval = interval_coverage(ctx, split_dates("validation"), names, "validation")
    return res, res_interval


def interval_coverage(ctx, dates, names, tag, directory=CKPT, prefix="lgbm_q") -> dict:
    qs = load("evaluation")["quantiles"]
    lo = TreeModel.load(directory, f"{prefix}{int(qs[0] * 100):02d}")
    hi = TreeModel.load(directory, f"{prefix}{int(qs[1] * 100):02d}")
    inside = n = 0
    widths = []
    for t in dates:
        F = ctx.features(t)
        y, _ = ctx.target(t)
        act = ctx.active_mask(F) & np.isfinite(F["sic_d0"]) & np.isfinite(y)
        idx = np.flatnonzero(act)
        if not idx.size:
            continue
        X = pd.DataFrame({k: F[k].ravel()[idx] for k in names})
        X["persistence"] = F["sic_d0"].ravel()[idx]
        a, b = lo.predict_sic(X), hi.predict_sic(X)
        a, b = np.minimum(a, b), np.maximum(a, b)
        yy = y.ravel()[idx]
        inside += ((yy >= a) & (yy <= b)).sum(); n += idx.size
        widths.append(b - a)
    w = np.concatenate(widths)
    res = {"nominal_coverage": qs[1] - qs[0], "empirical_coverage": float(inside / n), "cells": int(n),
           "mean_width_pp": float(w.mean()), "median_width_pp": float(np.median(w)), "split": tag,
           "n_issue_dates": len(dates),
           "note": "Evaluated on active cells with valid persistence (model domain), all issue dates of the split."}
    _dump(res, METRICS / f"interval_coverage_{tag}.json")
    return res


# --------------------------------------------------------------------------- tuning
def tune(n_trials: int | None = None):
    import lightgbm as lgb
    import optuna
    cfg = load("training")
    tr, va, names = stage_tables()
    base = dict(cfg["models"]["lightgbm"])
    oc = cfg["optuna"]
    ytr = tr["target"] - tr["persistence"]
    yva = (va["target"] - va["persistence"]).to_numpy()
    dtr = lgb.Dataset(tr[names], ytr, categorical_feature=["sector"], free_raw_data=False,
                      params={"feature_pre_filter": False})   # min_data_in_leaf varies across trials
    dva = lgb.Dataset(va[names], yva, reference=dtr)

    def objective(trial):
        p = {"objective": "regression_l1", "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.15, log=True),
             "num_leaves": trial.suggest_int("num_leaves", 31, 511, log=True),
             "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 20, 2000, log=True),
             "feature_fraction": trial.suggest_float("feature_fraction", 0.4, 1.0),
             "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0), "bagging_freq": 1,
             "lambda_l2": trial.suggest_float("lambda_l2", 1e-3, 30, log=True), "seed": cfg["seed"], "verbose": -1,
             "num_threads": psutil.cpu_count(logical=False) or 8}
        b = lgb.train(p, dtr, 3000, valid_sets=[dva], callbacks=[lgb.early_stopping(100, verbose=False)])
        trial.set_user_attr("best_iteration", b.best_iteration)
        return float(np.mean(np.abs(b.predict(va[names], num_iteration=b.best_iteration) - yva)))

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=cfg["seed"]))
    study.optimize(objective, n_trials=n_trials or oc["n_trials"], timeout=oc["timeout_s"])
    trials = [{"number": t.number, "value": t.value, "params": t.params, "best_iteration": t.user_attrs.get("best_iteration")}
              for t in study.trials if t.value is not None]
    res = {"best_value_mae_pp_validation_sample": study.best_value, "best_params": study.best_params,
           "best_iteration": study.best_trial.user_attrs["best_iteration"], "n_trials": len(trials), "trials": trials,
           "baseline_params": base, "objective": "MAE (pp) of residual on the validation sample (model domain cells)"}
    _dump(res, METRICS / "optuna_lightgbm.json")
    # validation-sample MAE of the untuned candidate for a like-for-like comparison
    cand = TreeModel.load(CKPT, "lgbm_residual")
    res["untuned_candidate_mae_pp_validation_sample"] = float(np.mean(np.abs(cand.predict_raw(va) - yva)))
    _dump(res, METRICS / "optuna_lightgbm.json")
    # tuned model trained on TRAIN only -> full-grid validation evaluation
    p = dict(base); p.update(study.best_params)
    p.pop("n_estimators", None); p.pop("early_stopping_rounds", None)
    mdl = TreeModel("lightgbm", names, p, "residual", "lgbm_residual_tuned")
    mdl.fit(tr, va, seed=cfg["seed"], n_estimators=3000)
    mdl.save(CKPT, {"train_rows": len(tr), "train_period": cfg["splits"]["train"], "optuna": True})
    tr0, tr1 = cfg["splits"]["train"]
    ctx = make_context(tr0, tr1)
    ev = evaluate_split(ctx, split_dates("validation"), {"lgbm_residual_tuned": TreeModel.load(CKPT, "lgbm_residual_tuned")},
                        baselines=("persistence",), tag="validation_tuned")
    return res, ev


# --------------------------------------------------------------------------- selection (before test)
def select() -> dict:
    cand = json.loads((METRICS / "validation_candidates" / "summary.json").read_text())["metrics"]
    tuned_p = METRICS / "validation_tuned" / "summary.json"
    if tuned_p.exists():
        cand.update({k: v for k, v in json.loads(tuned_p.read_text())["metrics"].items() if k != "persistence"})
    rows = []
    for m, groups in cand.items():
        g, s = groups.get("all", {}), groups.get("seasonal_ice_zone", {})
        rows.append({"method": m, "siz_mae": s.get("mae_pp"), "siz_rmse": s.get("rmse_pp"), "all_aw_rmse": g.get("area_weighted_rmse_pp"),
                     "iiee": g.get("iiee_mean_km2"), "extent_mae": g.get("extent_mae_km2")})
    df = pd.DataFrame(rows).set_index("method")
    ml = df[~df.index.isin(list(BASELINES))]
    # rank-sum over the primary criteria (lower is better); ties -> simpler model order below
    crit = ["siz_mae", "siz_rmse", "iiee", "extent_mae"]
    ranks = ml[crit].rank().sum(axis=1).sort_values()
    best = ranks.index[0]
    complexity = {"lgbm_residual": 1, "lgbm_residual_tuned": 1, "lgbm_residual_sic_only": 0, "lgbm_absolute": 1, "xgb_residual": 1, "rf_residual": 2}
    best_score = ranks.iloc[0]
    near = [m for m in ranks.index if ranks[m] <= best_score + 1e-9]
    best = sorted(near, key=lambda m: complexity.get(m, 3))[0]
    base_best = df.loc[list(BASELINES)].sort_values("siz_mae").index[0]
    beats = all(df.loc[best, c] < df.loc[base_best, c] for c in crit)
    meta = TreeModel.load(CKPT, best).meta
    rec = {"selected_model": best, "selection_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "criteria": "rank-sum over validation SIZ MAE, SIZ RMSE, IIEE, extent MAE; ties -> simpler model",
           "validation_table": df.reset_index().to_dict(orient="records"), "rank_sum": ranks.to_dict(),
           "best_baseline": base_best, "beats_best_baseline_on_all_criteria": bool(beats),
           "kind": meta["kind"], "features": meta["features"], "params": meta["params"], "target_mode": meta["target_mode"],
           "best_iteration_validation": meta["best_iteration"],
           "fallback_model": {"name": "final_model_sic_only", "rule": "same family/target/parameters as the selected model, atmospheric "
                              "features removed; used at inference when < 5 of 7 atmospheric days are available (declared before test)"},
           "test_set_accessed_before_selection": False}
    _dump(rec, METRICS / "selection_record.json")
    return rec


# --------------------------------------------------------------------------- final refit + single test
def final_refit():
    cfg = load("training")
    sel = json.loads((METRICS / "selection_record.json").read_text())
    t0, _ = cfg["splits"]["train"]
    _, v1 = cfg["splits"]["validation"]
    ctx = make_context(t0, v1)                         # climatology refitted on train+validation years
    names = sel["features"]
    dates = issue_dates(t0, v1)
    tab = build_table(ctx, dates, cfg["train_sample_fraction"], cfg["seed"], TABLES / "trainval_fit1979-2020.parquet",
                      feature_names(ctx.atmos is not None))
    n_iter = int(round(sel["best_iteration_validation"] * 1.1))   # ~10 % more data -> ~10 % more rounds
    p = dict(sel["params"]); p.pop("n_estimators", None); p.pop("early_stopping_rounds", None)
    mdl = TreeModel(sel["kind"], names, p, sel["target_mode"], "final_model")
    mdl.fit(tab, None, seed=cfg["seed"], n_estimators=n_iter, early_stopping=False)
    FINAL.mkdir(parents=True, exist_ok=True)
    meta = mdl.save(FINAL, {"selected_from": sel["selected_model"], "train_period": [t0, v1], "train_rows": len(tab),
                            "n_estimators_rule": "1.1 x validation best_iteration", "seed": cfg["seed"],
                            "climatology_artifact": rel(ART / f"sic_climatology_{t0[:4]}_{v1[:4]}.npz"),
                            "model_version": f"aethentra-sic-weekly-{dt.date.today():%Y%m%d}-v1",
                            "trained_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
    from ..features.build import ATM_FEATURES
    fb = TreeModel(sel["kind"], [n for n in names if n not in ATM_FEATURES], p, sel["target_mode"], "final_model_sic_only")
    fb.fit(tab, None, seed=cfg["seed"], n_estimators=n_iter, early_stopping=False)
    fb.save(FINAL, {"role": "fallback when atmospheric inputs are unavailable", "train_period": [t0, v1], "train_rows": len(tab),
                    "model_version": meta["model_version"] + "-sic-only"})
    for q in load("evaluation")["quantiles"]:
        pq = dict(cfg["models"]["lightgbm"]); pq.pop("objective"); pq.pop("n_estimators"); pq.pop("early_stopping_rounds")
        qm = TreeModel("lightgbm", feature_names(ctx.atmos is not None), pq, "residual", f"final_q{int(q * 100):02d}", q)
        qbest = json.loads((CKPT / f"lgbm_q{int(q * 100):02d}.meta.json").read_text())["best_iteration"]
        qm.fit(tab, None, seed=cfg["seed"], n_estimators=int(round(qbest * 1.1)), early_stopping=False)
        qm.save(FINAL, {"train_period": [t0, v1]})
    # copy climatology references into the final bundle
    import shutil
    shutil.copy(ART / f"sic_climatology_{t0[:4]}_{v1[:4]}.npz", FINAL / "sic_climatology.npz")
    if ctx.atmos is not None:
        np.savez_compressed(FINAL / "atmos_climatology.npz", **ctx.atmos.clim, period=np.array(ctx.atmos.clim_period))
    return meta


def test_once(force: bool = False):
    out = METRICS / "test_final" / "summary.json"
    if out.exists() and not force:
        raise RuntimeError("Test evaluation already exists; refusing to re-run (pass force=True only for a documented reason).")
    cfg = load("training")
    t0, _ = cfg["splits"]["train"]
    _, v1 = cfg["splits"]["validation"]
    ctx = make_context(t0, v1)
    model = TreeModel.load(FINAL, "final_model")
    models = {"final_model": model}
    if (FINAL / "final_model_sic_only.meta.json").exists():
        models["final_model_sic_only"] = TreeModel.load(FINAL, "final_model_sic_only")
    res = evaluate_split(ctx, split_dates("test"), models, tag="test_final",
                         save_grids=["final_model", "persistence", "climatology", "anomaly_persistence"])
    names = model.features
    cov = interval_coverage(ctx, split_dates("test"), feature_names(ctx.atmos is not None), "test", FINAL, "final_q")
    res["interval_coverage"] = cov
    _dump(res, out)
    return res
