"""ML-04 inference on submitted monthly-mean observations (POST /api/ml04/detect).

Steps: validate -> locate the 2.5 deg cell -> standardise against the frozen 1981-2010 baseline (saved climatology) ->
statistical scores + selected multivariate detector -> base-rate severity classes -> per-variable contributions.
The input must be a MONTHLY MEAN on the NCEP R1 scale; point observations (stations) are not directly comparable with
2.5 deg reanalysis cells, which the response states.
"""
from __future__ import annotations

import json

import numpy as np

from .detectors import load_model, mad_score, percentile_score, severity_of, zscore_score
from .features import FEATS, Featurizer, model_matrix
from .paths import MODELS
from .preprocessing import grid
from .products import DATA_TIER, regions, univariate_thresholds_model

_FZ = None


def _fz():
    global _FZ
    if _FZ is None:
        _FZ = Featurizer("model")
    return _FZ


def detect_observations(obs: list[dict]) -> list[dict]:
    g = grid()
    d = json.loads((MODELS / "decision.json").read_text())
    sel = d["selected_multivariate"]
    model = load_model(sel)
    thr = {n: json.loads((MODELS / f"{n}.meta.json").read_text())["thresholds"] for n in ("zscore", "percentile", "mad", sel)}
    uth = univariate_thresholds_model()
    ofr_ok = np.isfinite(_fz().clim["sic"]["mean"]).any(0).ravel()
    N = len(obs)
    moy, cell = np.empty(N, np.int64), np.empty(N, np.int64)
    X = {v: np.full(N, np.nan, np.float32) for v in FEATS}
    for k, o in enumerate(obs):
        m = o["month"]
        if len(m) != 7 or m[4] != "-" or not (1 <= int(m[5:]) <= 12):
            raise ValueError(f"observation {k}: month must be YYYY-MM")
        i = int(np.clip(np.round((g["lat"][0] - o["latitude"]) / 2.5), 0, g["lat"].size - 1))
        j = int(np.mod(np.round(np.mod(o["longitude"], 360) / 2.5), g["lon"].size))
        moy[k], cell[k] = int(m[5:]), i * g["lon"].size + j
        for v in FEATS[:7]:
            X[v][k] = o[v]
        if o.get("sic") is not None:
            if not ofr_ok[cell[k]]:
                raise ValueError(f"observation {k}: SIC given for a cell without sea-ice climatology (land / ice sheet)")
            X["sic"][k] = o["sic"]
            if o.get("sic_previous_month") is not None:
                X["dsic"][k] = o["sic"] - o["sic_previous_month"]
    f = _fz().transform(X, moy, cell)
    Z = model_matrix(f["z"])
    s = {"zscore": zscore_score(f["z"]), "percentile": percentile_score(f["percentile"]), "mad": mad_score(f["robust"]),
         sel: model.score(Z, moy)}
    sev = {n: severity_of(v, thr[n]) for n, v in s.items()}
    base = s[sel]
    contrib = np.zeros(Z.shape)
    for j in range(Z.shape[1]):
        Zj = Z.copy()
        Zj[:, j] = 0
        contrib[:, j] = base - model.score(Zj, moy)
    reg = regions().ravel()
    out = []
    for k in range(N):
        agree = sum(sev[n][k] in ("moderate", "strong", "extreme") for n in s)
        per_var = {}
        for j, v in enumerate(FEATS):
            z = f["z"][k, j]
            if not np.isfinite(z):
                continue
            cls = ["normal", "mild", "moderate", "strong", "extreme"][int(np.searchsorted(uth[v], abs(z), side="right"))]
            per_var[v] = {"z": round(float(z), 3), "robust_z": round(float(f["robust"][k, j]), 3),
                          "percentile": round(100 * float(f["percentile"][k, j]), 1), "severity": cls, "data_tier": DATA_TIER[v],
                          "baseline_mean": round(float(_fz()._lookup(v, "mean", moy[k:k + 1], cell[k:k + 1])[0]), 3),
                          "contribution_to_multivariate_score": round(float(contrib[k, j]), 4)}
        out.append({"month": obs[k]["month"], "cell": {"lat": float(g["lat"][cell[k] // 144]), "lon": float(g["lon"][cell[k] % 144]),
                                                       "region": reg[cell[k]]},
                    "multivariate": {"method": sel, "score": round(float(base[k]), 4), "severity": sev[sel][k]},
                    "statistical": {n: {"score": round(float(s[n][k]), 4), "severity": sev[n][k]} for n in ("zscore", "percentile", "mad")},
                    "method_agreement": f"{agree}/4", "variables": per_var, "baseline": "1981-2010 (model)",
                    "caveat": "monthly means on the 2.5 deg NCEP R1 scale; a point observation is not directly comparable"})
    return out
