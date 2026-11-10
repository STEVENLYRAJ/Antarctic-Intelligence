"""ML-02 training / evaluation stages (each stage is cached; the test stage refuses to run twice).

    tables -> candidates -> tune -> select -> final -> test ; stations (independent check)
"""
from __future__ import annotations

import json
import logging
import time

import numpy as np
import pandas as pd
import psutil

from ..baselines.baselines import BASELINES, fit_damped_alpha, predict_baseline
from ..climatology.climatology import Climatology
from ..evaluation.metrics import Accumulator
from ..features.build import CATEGORICAL, FeatureContext, feature_names, issue_dates
from ..labels.labels import Sigma, categorize, target_season
from ..models.anomaly_model import AnomalyModel
from ..paths import EXPERIMENTS, METRICS, MODELS, PROCESSED, load
from ..preprocessing.cube import Cube

LOG = logging.getLogger("aethentra.ml02.train")
CKPT, FINAL, ART = MODELS / "checkpoints", MODELS / "final", MODELS / "artifacts"
TABLES = PROCESSED / "tables"


def _dump(obj, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


def split_dates(name: str, source: str | None = None) -> pd.DatetimeIndex:
    """Issue dates of a split, minus those whose input (history_days) or target window overlaps a suspect period."""
    s, e = load("training")["splits"][name]
    d = issue_dates(s, e)
    source = source or load("data_sources")["primary"]
    fc = load("features")
    hist, h = fc["issue"]["history_days"], fc["labels"]["horizon_days"]
    keep = np.ones(len(d), bool)
    for a, b in load("preprocessing")["sources"][source].get("suspect_periods", []):
        keep &= ~((d - pd.Timedelta(days=hist - 1) <= pd.Timestamp(b)) & (d + pd.Timedelta(days=h) >= pd.Timestamp(a)))
    return d[keep]


# ------------------------------------------------------------------------------------------- context
def make_context(source: str | None = None, use_sic: bool | None = None) -> FeatureContext:
    cube = Cube(source)
    ART.mkdir(parents=True, exist_ok=True)
    cp = ART / f"t2m_climatology_{cube.source}.npz"
    if cp.exists():
        clim = Climatology.load(cp)
    else:
        clim = Climatology.fit(cube)
        clim.save(cp)
    sp = ART / f"anomaly_sigma_{cube.source}.npz"
    if sp.exists():
        sigma = Sigma.load(sp)
    else:
        p0, p1 = load("features")["categories"]["sigma_period"]
        tr0, tr1 = load("training")["splits"]["train"]
        assert pd.Timestamp(f"{p1}-12-31") <= pd.Timestamp(tr1), "sigma period must lie inside the training split"
        d = split_dates("train", cube.source)
        sigma = Sigma.fit(cube, clim, d[(d.year >= p0) & (d.year <= p1)])
        sigma.save(sp)
    use_sic = load("features")["use_sea_ice"] if use_sic is None else use_sic
    sic = None
    if use_sic:
        try:
            from ...preprocessing.cube import Cube as SicCube
            sic = SicCube()
        except Exception as e:  # noqa: BLE001
            LOG.warning("ML-01 SIC cube unavailable (%s); sea-ice features disabled", e)
    return FeatureContext(cube, clim, sigma, sic)


def names_for(ctx: FeatureContext, temperature_only: bool = False) -> list[str]:
    return feature_names(ctx.cube.variables, ctx.sic_cube is not None, temperature_only)


# ------------------------------------------------------------------------------------------- tables
def build_table(ctx, dates, frac, seed, tag) -> pd.DataFrame:
    p = TABLES / f"{tag}_{ctx.cube.source}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    rng = np.random.default_rng(seed)
    names = names_for(ctx)
    parts, t0 = [], time.time()
    for i, t in enumerate(dates):
        df = ctx.table(t, names, frac, rng)
        df["season"] = target_season(t)
        parts.append(df)
        if i % 200 == 0:
            LOG.info("table %s: %d/%d dates %.0f s", tag, i, len(dates), time.time() - t0)
    out = pd.concat(parts, ignore_index=True)
    fcols = out.select_dtypes("float64").columns
    out[fcols] = out[fcols].astype("float32")
    num = out[names].to_numpy(np.float32)
    if np.isinf(num).any():
        raise ValueError(f"inf in features: {[n for n in names if np.isinf(out[n]).any()]}")
    TABLES.mkdir(parents=True, exist_ok=True)
    out.to_parquet(p)
    _dump({"rows": len(out), "dates": len(dates), "first": str(dates[0].date()), "last": str(dates[-1].date()), "fraction": frac,
           "features": names}, p.with_suffix(".json"))
    return out


def stage_tables(source=None):
    cfg = load("training")
    ctx = make_context(source)
    tr = build_table(ctx, split_dates("train"), cfg["train_sample_fraction"], cfg["seed"], "train")
    va = build_table(ctx, split_dates("validation"), cfg["val_sample_fraction"], cfg["seed"] + 1, "validation")
    LOG.info("tables: train %d rows, validation %d rows", len(tr), len(va))
    alpha = fit_damped_alpha(tr)
    _dump(alpha, ART / f"damped_persistence_alpha_{ctx.cube.source}.json")
    return ctx, tr, va


# ------------------------------------------------------------------------------------------- evaluation
def evaluate_split(ctx, dates, models: dict, tag: str, baselines=BASELINES, save_fields: bool = False) -> dict:
    alpha = json.loads((ART / f"damped_persistence_alpha_{ctx.cube.source}.json").read_text())
    names = list(models) + list(baselines)
    acc = {n: Accumulator(ctx.cube.grid, ctx.area) for n in names}
    fields, t0 = {}, time.time()
    for i, t in enumerate(dates):
        F = ctx.features(t)
        tw, aw, _ = ctx.labels(t)
        s = target_season(t)
        sig = ctx.sigma.for_date(t)
        cobs = categorize(aw, sig)
        preds = {n: m.predict_cells(F) for n, m in models.items()}
        for b in baselines:
            preds[b] = predict_baseline(b, F, sig, alpha, s)
        for n, p in preds.items():
            acc[n].add(t, s, p, aw, tw, categorize(p, sig), cobs)
        if save_fields:
            fields.setdefault("obs_anom", []).append(aw)
            for n in list(models)[:1] + ["persistence", "climatology"]:
                fields.setdefault(n, []).append(preds[n])
        if i % 50 == 0:
            LOG.info("eval %s: %d/%d dates %.0f s", tag, i, len(dates), time.time() - t0)
    out = METRICS / tag
    out.mkdir(parents=True, exist_ok=True)
    res = {"tag": tag, "source": ctx.cube.source, "n_issue_dates": len(dates), "first": str(dates[0].date()), "last": str(dates[-1].date()),
           "seconds": round(time.time() - t0, 1), "metrics": {}}
    frames = []
    for n, a in acc.items():
        res["metrics"][n] = a.summary()
        f = a.frame(); f["model"] = n; frames.append(f)
    pd.concat(frames).to_parquet(out / "per_date_sums.parquet")
    np.savez_compressed(out / "error_maps.npz", **{f"{n}__{k}": v.astype(np.float32) for n, a in acc.items() for k, v in a.maps().items()})
    if save_fields:
        np.savez_compressed(out / "fields.npz", dates=np.array([str(d.date()) for d in dates]), **{k: np.stack(v) for k, v in fields.items()})
    _dump(res, out / "summary.json")
    return res


# ------------------------------------------------------------------------------------------- candidates
def _rss():
    return round(psutil.Process().memory_info().rss / 1e9, 2)


def train_candidates(source=None):
    cfg = load("training")
    ctx, tr, va = stage_tables(source)
    names = names_for(ctx)
    t_only = names_for(ctx, temperature_only=True)
    M = cfg["models"]
    specs = [("lgbm", "lightgbm", names, M["lightgbm"], None), ("lgbm_temperature_only", "lightgbm", t_only, M["lightgbm"], None),
             ("xgb", "xgboost", names, M["xgboost"], None), ("rf", "random_forest", names, M["random_forest"], None)]
    specs += [(f"lgbm_q{int(q * 100):02d}", "lightgbm", names, M["lightgbm"], q) for q in cfg["quantiles"]]
    models, records = {}, {}
    for name, kind, feats, params, q in specs:
        if (CKPT / f"{name}.meta.json").exists():
            models[name] = AnomalyModel.load(CKPT, name)
            records[name] = models[name].meta
            continue
        m0 = _rss()
        mdl = AnomalyModel(kind, feats, params, name=name, quantile=q)
        trd = tr.sample(params["max_train_rows"], random_state=cfg["seed"]) if kind == "random_forest" and len(tr) > params["max_train_rows"] else tr
        mdl.fit(trd, va if kind != "random_forest" else None, seed=cfg["seed"])
        records[name] = mdl.save(CKPT, {"train_rows": len(trd), "validation_rows": len(va), "train_period": cfg["splits"]["train"],
                                        "seed": cfg["seed"], "rss_gb_before": m0, "rss_gb_after": _rss(), "source": ctx.cube.source})
        LOG.info("%s: %.0f s, best_iteration=%s", name, mdl.fit_seconds, mdl.best_iteration)
        models[name] = AnomalyModel.load(CKPT, name)
    _dump(records, METRICS / "candidate_training_records.json")
    point = {k: v for k, v in models.items() if "_q" not in k}
    res = evaluate_split(ctx, split_dates("validation"), point, "validation_candidates")
    cov = interval_coverage(ctx, split_dates("validation"), CKPT, "lgbm_q", "validation")
    return res, cov


def interval_coverage(ctx, dates, directory, prefix, tag) -> dict:
    qs = load("training")["quantiles"]
    lo = AnomalyModel.load(directory, f"{prefix}{int(qs[0] * 100):02d}")
    hi = AnomalyModel.load(directory, f"{prefix}{int(qs[1] * 100):02d}")
    inside = n = 0
    widths = []
    for t in dates:
        F = ctx.features(t)
        _, aw, _ = ctx.labels(t)
        a, b = lo.predict_cells(F), hi.predict_cells(F)
        a, b = np.minimum(a, b), np.maximum(a, b)
        ok = np.isfinite(a) & np.isfinite(aw)
        inside += int(((aw >= a) & (aw <= b) & ok).sum()); n += int(ok.sum())
        widths.append((b - a)[ok])
    w = np.concatenate(widths)
    res = {"nominal_coverage": qs[1] - qs[0], "empirical_coverage": inside / n, "cells": n, "n_issue_dates": len(dates),
           "mean_width_degC": float(w.mean()), "median_width_degC": float(np.median(w)), "split": tag}
    _dump(res, METRICS / f"interval_coverage_{tag}.json")
    return res


# ------------------------------------------------------------------------------------------- tuning (validation only)
def tune(source=None):
    import lightgbm as lgb
    import optuna
    cfg = load("training")
    ctx, tr, va = stage_tables(source)
    names = names_for(ctx)
    dtr = lgb.Dataset(tr[names], tr["target_anom"], free_raw_data=False, params={"feature_pre_filter": False})
    dva = lgb.Dataset(va[names], va["target_anom"], reference=dtr)
    yva = va["target_anom"].to_numpy()
    nthreads = psutil.cpu_count(logical=False) or 8

    def objective(trial):
        p = {"objective": "regression", "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.15, log=True),
             "num_leaves": trial.suggest_int("num_leaves", 31, 511, log=True),
             "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 20, 2000, log=True),
             "feature_fraction": trial.suggest_float("feature_fraction", 0.4, 1.0),
             "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0), "bagging_freq": 1,
             "lambda_l2": trial.suggest_float("lambda_l2", 1e-3, 30, log=True), "seed": cfg["seed"], "verbose": -1, "num_threads": nthreads}
        b = lgb.train(p, dtr, 3000, valid_sets=[dva], callbacks=[lgb.early_stopping(100, verbose=False)])
        trial.set_user_attr("best_iteration", b.best_iteration)
        return float(np.sqrt(np.mean((b.predict(va[names], num_iteration=b.best_iteration) - yva) ** 2)))

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=cfg["seed"]))
    study.optimize(objective, n_trials=cfg["optuna"]["n_trials"], timeout=cfg["optuna"]["timeout_s"])
    ok = [t for t in study.trials if t.value is not None]
    if not ok:
        raise RuntimeError("all Optuna trials failed")
    base = AnomalyModel.load(CKPT, "lgbm")
    res = {"objective": "RMSE (degC) of weekly anomaly on the validation sample", "best_value": study.best_value,
           "best_params": study.best_params, "best_iteration": study.best_trial.user_attrs["best_iteration"], "n_trials_completed": len(ok),
           "n_trials_failed": len(study.trials) - len(ok),
           "untuned_lgbm_value": float(np.sqrt(np.mean((base.predict_anom(va) - yva) ** 2))),
           "trials": [{"number": t.number, "value": t.value, "params": t.params, "best_iteration": t.user_attrs.get("best_iteration")} for t in ok]}
    _dump(res, METRICS / "optuna_lightgbm.json")
    p = dict(cfg["models"]["lightgbm"]); p.update(study.best_params)
    mdl = AnomalyModel("lightgbm", names, p, name="lgbm_tuned")
    mdl.fit(tr, va, seed=cfg["seed"])
    mdl.save(CKPT, {"train_rows": len(tr), "train_period": cfg["splits"]["train"], "optuna": True, "source": ctx.cube.source})
    ev = evaluate_split(ctx, split_dates("validation"), {"lgbm_tuned": AnomalyModel.load(CKPT, "lgbm_tuned")}, "validation_tuned",
                        baselines=("persistence",))
    return res, ev


# ------------------------------------------------------------------------------------------- selection
SIMPLICITY = {"damped_persistence": 0, "persistence_week": 0, "persistence": 0, "climatology": 0, "recent_trend": 0,
              "lgbm_temperature_only": 1, "lgbm": 2, "lgbm_tuned": 3, "xgb": 2, "rf": 2}


def select():
    if (METRICS / "test_final" / "summary.json").exists():
        raise RuntimeError("test already evaluated; selection is frozen")
    cfg = load("training")
    val = json.loads((METRICS / "validation_candidates" / "summary.json").read_text())["metrics"]
    tp = METRICS / "validation_tuned" / "summary.json"
    if tp.exists():
        val["lgbm_tuned"] = json.loads(tp.read_text())["metrics"]["lgbm_tuned"]
    table = {}
    for reg, met, d in cfg["selection_metrics"]:
        vals = {m: v[reg][met] for m, v in val.items()}
        # undefined values (e.g. ACC of the zero-anomaly climatology forecast) rank last
        order = sorted(vals, key=lambda m: (vals[m] is None, 0 if vals[m] is None else (vals[m] if d == "min" else -vals[m])))
        for r, m in enumerate(order, 1):
            table.setdefault(m, {})[f"{reg}:{met}"] = {"value": vals[m], "rank": r}
    score = {m: sum(x["rank"] for x in v.values()) for m, v in table.items()}
    ml = [m for m in score if m in SIMPLICITY and SIMPLICITY[m] > 0]
    best = min(ml, key=lambda m: (score[m], SIMPLICITY[m]))
    best_baseline = min([m for m in score if SIMPLICITY.get(m, 9) == 0], key=lambda m: score[m])
    meta = json.loads((CKPT / f"{best}.meta.json").read_text())
    rec = {"selected_model": best, "selection_basis": "validation 2011-2017 full-grid, rank-sum of " + ", ".join(":".join(x[:2]) for x in cfg["selection_metrics"]),
           "rank_sum": score, "ranks": table, "best_baseline_on_validation": best_baseline, "selected_params": meta["params"],
           "selected_features": meta["features"], "best_iteration": meta["best_iteration"],
           "beats_best_baseline_on_all_selection_metrics": all(table[best][k]["rank"] < table[best_baseline][k]["rank"] for k in table[best]),
           "test_set_accessed_before_selection": False, "frozen_utc": pd.Timestamp.now(tz="UTC").isoformat()}
    _dump(rec, METRICS / "selection_record.json")
    return rec


# ------------------------------------------------------------------------------------------- final refit
def final_refit(source=None):
    cfg = load("training")
    rec = json.loads((METRICS / "selection_record.json").read_text())
    ctx, tr, va = stage_tables(source)
    trva = pd.concat([tr, va], ignore_index=True)       # validation sampled at a higher fraction -> reweight to the train density
    w = np.where(trva["issue_date"] > pd.Timestamp(cfg["splits"]["train"][1]), cfg["train_sample_fraction"] / cfg["val_sample_fraction"], 1.0)
    keep = np.random.default_rng(cfg["seed"]).random(len(trva)) < w
    trva = trva[keep].reset_index(drop=True)
    meta = json.loads((CKPT / f"{rec['selected_model']}.meta.json").read_text())
    n_iter = int(round(1.1 * meta["best_iteration"])) if meta["kind"] != "random_forest" else meta["best_iteration"]
    FINAL.mkdir(parents=True, exist_ok=True)
    version = f"aethentra-t2m-weekly-{pd.Timestamp.now():%Y%m%d}-v1"
    period = [cfg["splits"]["train"][0], cfg["splits"]["validation"][1]]
    out = {}
    qmeta = AnomalyModel.load(CKPT, "lgbm_q10").meta
    jobs = [("final_model", meta["kind"], meta["features"], meta["params"], None, n_iter)]
    jobs += [(f"final_q{int(q * 100):02d}", "lightgbm", qmeta["features"], cfg["models"]["lightgbm"], q,
              int(round(1.1 * AnomalyModel.load(CKPT, f"lgbm_q{int(q * 100):02d}").meta["best_iteration"]))) for q in cfg["quantiles"]]
    for name, kind, feats, params, q, n in jobs:
        p = {k: v for k, v in params.items() if k not in ("early_stopping_rounds",)}
        mdl = AnomalyModel(kind, feats, p, name=name, quantile=q)
        mdl.fit(trva, None, seed=cfg["seed"], n_estimators=n, early_stopping=False)
        out[name] = mdl.save(FINAL, {"selected_from": rec["selected_model"], "train_period": period, "train_rows": len(trva),
                                     "n_estimators": n, "model_version": version, "source": ctx.cube.source,
                                     "climatology_period": list(ctx.clim.period)})
    import shutil
    for f in (f"t2m_climatology_{ctx.cube.source}.npz", f"anomaly_sigma_{ctx.cube.source}.npz", f"damped_persistence_alpha_{ctx.cube.source}.json"):
        shutil.copy2(ART / f, FINAL / f)
    return out


# ------------------------------------------------------------------------------------------- single test evaluation
def test_once(source=None):
    out = METRICS / "test_final" / "summary.json"
    if out.exists():
        raise RuntimeError("Test evaluation already exists; refusing to re-run.")
    if not (METRICS / "selection_record.json").exists():
        raise RuntimeError("No frozen selection record")
    ctx = make_context(source)
    res = evaluate_split(ctx, split_dates("test"), {"final_model": AnomalyModel.load(FINAL, "final_model")}, "test_final", save_fields=True)
    res["interval_coverage"] = interval_coverage(ctx, split_dates("test"), FINAL, "final_q", "test")
    res["evaluated_utc"] = pd.Timestamp.now(tz="UTC").isoformat()
    res["selection_record_frozen_utc"] = json.loads((METRICS / "selection_record.json").read_text())["frozen_utc"]
    _dump(res, out)
    return res
