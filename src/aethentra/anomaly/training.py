"""ML-04 training / validation / frozen selection / single test (same protocol as ML-01...03).

1. fit       statistical + ML candidates on TRAINING cell-months (1979-2010, atm_valid). Severity thresholds = quantiles of
             each candidate's training-period score (LOF/OCSVM: training rows NOT used to fit, to avoid self-neighbour bias).
2. validate  synthetic injection into VALIDATION (2011-2017, seed 2011); seed-stability of ML candidates; best member per
             family by PR-AUC; cross-family selection by rank-sum of PR-AUC overall / univariate / compound / covariance-break
             among candidates with seed-stability Spearman >= 0.9. The decision is frozen to decision.json.
3. test      the frozen decision is evaluated ONCE on TEST (2018-2025, seed 2018). Re-running needs --force and is logged.
No test data are used for any fit, threshold or choice.
"""
from __future__ import annotations

import datetime as dt
import json
import logging

import numpy as np
import pandas as pd

from .detectors import (Autoencoder, Mahalanobis, SkModel, load_model, mad_score, percentile_score, save, severity_of,
                        severity_thresholds, zscore_score)
from .evaluation import correlated_pairs, featurize_rows, inject, metrics, stability
from .features import FEATS, Featurizer, load_table, model_matrix
from .paths import METRICS, MODELS, load

LOG = logging.getLogger("aethentra.ml04.training")
NOW = lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")  # noqa: E731

CANDIDATES = {
    "isolation_forest": [("isolation_forest_s256", {"n_estimators": 300, "max_samples": 256}),
                         ("isolation_forest_s4096", {"n_estimators": 300, "max_samples": 4096})],
    "lof": [("lof_k20", {"n_neighbors": 20}), ("lof_k100", {"n_neighbors": 100})],
    "ocsvm": [("ocsvm_nu01", {"nu": 0.01, "gamma": "scale"}), ("ocsvm_nu05", {"nu": 0.05, "gamma": "scale"})],
    "autoencoder": [("autoencoder_b3", {"bottleneck": 3}), ("autoencoder_b5", {"bottleneck": 5})],
}
N_FIT = {"lof": 50_000, "ocsvm": 20_000}
STATS = ["zscore", "percentile", "mad", "mahalanobis"]


def _rows(df, split):
    return np.flatnonzero((df["split"].values == split) & df["atm_valid"].values)


def score_methods(names: list[str], z, robust, pct, moy, models: dict | None = None) -> dict:
    """Scores for the named methods on given rows (arrays already row-selected)."""
    Z = model_matrix(np.asarray(z))
    out = {}
    for n in names:
        if n == "zscore":
            out[n] = zscore_score(z)
        elif n == "percentile":
            out[n] = percentile_score(pct)
        elif n == "mad":
            out[n] = mad_score(robust)
        else:
            m = (models or {}).get(n) or load_model(n)
            out[n] = m.score(Z, moy)
    return out


def _new(fam, name, params, seed=42):
    if fam == "autoencoder":
        return Autoencoder(seed=seed, **params)
    return SkModel(fam, params, n_fit=N_FIT.get(fam), seed=seed)


def fit_all() -> dict:
    df, A = load_table()
    tr, va = _rows(df, "train"), _rows(df, "validation")
    Z, moy = model_matrix(np.asarray(A["z"][tr])), df["moy"].values[tr]
    Zv = model_matrix(np.asarray(A["z"][va]))
    classes = load("anomaly")["severity"]["classes"]
    summary = {}
    m = Mahalanobis().fit(Z, moy)
    s = m.score(Z, moy)
    save(m, "mahalanobis", {"family": "mahalanobis", "trained_utc": NOW(), "n_train": len(Z), "train_split": "1979-2010",
                            "thresholds": severity_thresholds(s, classes), "features": FEATS})
    summary["mahalanobis"] = {"n_train": len(Z)}
    for n, fn in (("zscore", lambda: zscore_score(A["z"][tr])), ("percentile", lambda: percentile_score(A["percentile"][tr])),
                  ("mad", lambda: mad_score(A["robust"][tr]))):
        (MODELS / f"{n}.meta.json").write_text(json.dumps({"family": n, "thresholds": severity_thresholds(fn(), classes),
                                                           "calibrated_on": "1979-2010 training cell-months"}, indent=1))
    for fam, cands in CANDIDATES.items():
        for name, params in cands:
            LOG.info("fit %s", name)
            mdl = _new(fam, name, params)
            mdl.fit(Z, moy, Zv) if fam == "autoencoder" else mdl.fit(Z, moy)
            if fam in N_FIT:                                   # calibration on training rows not used to fit
                rng = np.random.default_rng(42)
                cal_idx = np.setdiff1d(np.arange(len(Z)), np.sort(rng.choice(len(Z), N_FIT[fam], replace=False)))
                cal_idx = np.sort(np.random.default_rng(1).choice(cal_idx, min(200_000, cal_idx.size), replace=False))
            else:
                cal_idx = np.arange(len(Z))
            sc = mdl.score(Z[cal_idx], moy[cal_idx])
            meta = {"family": fam, "params": params, "trained_utc": NOW(), "n_train": int(mdl.n_train),
                    "fit_seconds": round(mdl.fit_seconds, 1), "train_split": "1979-2010", "features": FEATS,
                    "thresholds": severity_thresholds(sc, classes), "calibration_rows": int(cal_idx.size)}
            if fam == "autoencoder":
                meta |= {"best_epoch": mdl.best_epoch, "val_recon_history": [round(x, 5) for x in mdl.history]}
            save(mdl, name, meta)
            summary[name] = {k: meta[k] for k in ("n_train", "fit_seconds")}
    METRICS.mkdir(parents=True, exist_ok=True)
    (METRICS / "fit_summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def _thr(name):
    return json.loads((MODELS / f"{name}.meta.json").read_text())["thresholds"]


def evaluate_split(split: str, seed: int, names: list[str]) -> tuple[dict, pd.DataFrame]:
    df, A = load_table()
    rows = _rows(df, split)
    sub = df.iloc[rows].reset_index(drop=True)
    fz = Featurizer("model")
    pairs = correlated_pairs(np.asarray(A["z"][_rows(df, "train")]))
    inj = inject(sub, np.asarray(A["physical"][rows]), fz, seed, pairs, load("anomaly")["synthetic_tests"]["fraction"])
    z, rb, pc = (np.array(A[k][rows]) for k in ("z", "robust", "percentile"))
    pos = np.flatnonzero(inj["label"])
    f = featurize_rows(fz, sub, inj["phys"], pos)
    z[pos], rb[pos], pc[pos] = f["z"], f["robust"], f["percentile"]
    sc = score_methods(names, z, rb, pc, sub["moy"].values)
    res = {n: metrics(s, inj["label"], inj["kind"], _thr(n)["moderate"]) for n, s in sc.items()}
    inj["log"]["month"] = sub["month"].values[inj["log"]["row"].values]
    inj["log"]["cell"] = sub["cell"].values[inj["log"]["row"].values]
    return {"split": split, "seed": seed, "n_samples": int(len(sub)), "n_injected": int(inj["label"].sum()),
            "correlated_pairs_used": pairs, "metrics": res}, inj["log"]


def validate() -> dict:
    names = STATS + [n for c in CANDIDATES.values() for n, _ in c]
    res, log = evaluate_split("validation", load("anomaly")["synthetic_tests"]["seed_validation"], names)
    log.to_csv(METRICS / "validation_injections_SYNTHETIC.csv", index=False)
    df, A = load_table()
    va = _rows(df, "validation")
    Zv, moyv = model_matrix(np.asarray(A["z"][va])), df["moy"].values[va]
    tr = _rows(df, "train")
    Z, moy = model_matrix(np.asarray(A["z"][tr])), df["moy"].values[tr]
    stab = {n: {"spearman": 1.0, "top2pct_jaccard": 1.0, "note": "deterministic"} for n in STATS}
    for fam, cands in CANDIDATES.items():
        for name, params in cands:
            alt = _new(fam, name, params, seed=7)
            alt.fit(Z, moy, Zv) if fam == "autoencoder" else alt.fit(Z, moy)
            stab[name] = stability(load_model(name).score(Zv, moyv), alt.score(Zv, moyv))
            LOG.info("stability %s %s", name, stab[name])
    res["stability_seed7"] = stab
    # best member per ML family (PR-AUC overall), then cross-family rank-sum
    fam_best = {fam: max((n for n, _ in c), key=lambda n: res["metrics"][n]["pr_auc"]) for fam, c in CANDIDATES.items()}
    finalists = STATS + list(fam_best.values())
    eligible = [n for n in finalists if stab[n]["spearman"] >= 0.9]
    keys = ["pr_auc", "pr_auc_univariate_spike", "pr_auc_compound_moderate", "pr_auc_covariance_break"]
    tab = pd.DataFrame({n: {k: res["metrics"][n][k] for k in keys} for n in eligible}).T
    ranks = tab.rank(ascending=False).sum(1).sort_values()
    multivariate = [n for n in ranks.index if n not in ("zscore", "percentile", "mad")]
    rel = load("anomaly").get("release", {"version": 1})
    decision = {"version": int(rel["version"]), "supersedes": rel.get("supersedes"),
                "frozen_utc": NOW(), "selection_split": "validation (2011-2017), synthetic injections seed 2011",
                "family_best": fam_best, "eligible": eligible, "rank_sum": ranks.round(2).to_dict(), "criteria": keys,
                "selected_overall": ranks.index[0], "selected_multivariate": multivariate[0],
                "univariate_reference": "zscore (+ percentile and MAD shown alongside)",
                "rule": "lowest rank-sum over the four PR-AUC criteria among candidates with seed-stability Spearman >= 0.9; "
                        "operational multivariate detector = best multivariate method; univariate z/percentile/MAD stay as references"}
    (METRICS / "validation.json").write_text(json.dumps(res, indent=1, default=float))
    if (MODELS / "decision.json").exists():
        LOG.warning("decision.json exists: kept (frozen). New ranking written to validation.json only")
    else:
        (MODELS / "decision.json").write_text(json.dumps(decision, indent=1))
    return decision


def test_once(force: bool = False) -> dict:
    out = METRICS / "test.json"
    if out.exists() and not force:
        raise RuntimeError("test evaluation already done (single-test rule); use --force to re-run (logged)")
    d = json.loads((MODELS / "decision.json").read_text())
    names = STATS + list(d["family_best"].values())
    res, log = evaluate_split("test", load("anomaly")["synthetic_tests"]["seed_test"], names)
    log.to_csv(METRICS / "test_injections_SYNTHETIC.csv", index=False)
    res |= {"decision_version": d.get("version", 1), "decision_frozen_utc": d["frozen_utc"], "evaluated_utc": NOW(),
            "forced_rerun": bool(force)}
    out.write_text(json.dumps(res, indent=1, default=float))
    return res


def score_all() -> pd.DataFrame:
    """Scores + severities of the reference and selected methods for every atm-valid cell-month -> METRICS/../scores.parquet."""
    from .paths import FEATURES
    d = json.loads((MODELS / "decision.json").read_text())
    names = list(dict.fromkeys(STATS + [d["selected_multivariate"]] + list(d["family_best"].values())))
    df, A = load_table()
    rows = np.flatnonzero(df["atm_valid"].values)
    sc = score_methods(names, A["z"][rows], A["robust"][rows], A["percentile"][rows], df["moy"].values[rows])
    out = pd.DataFrame({"idx": rows})
    for n, s in sc.items():
        out[f"score_{n}"] = s.astype(np.float32)
        out[f"sev_{n}"] = severity_of(s, _thr(n)).astype(str)
    out.to_parquet(FEATURES / "scores.parquet", index=False)
    return out
