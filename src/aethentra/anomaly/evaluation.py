"""ML-04 Phase 10: evaluation without ground-truth anomaly labels.

No labelled catalogue of Antarctic anomalies exists, so detectors are compared with:
1. SYNTHETIC anomaly recovery (clearly labelled synthetic; software/method testing only, never presented as real events).
   Into a random 1 % of real cell-months of one split, perturbations are injected in PHYSICAL units (k x the cell's
   baseline std), then every detector re-scores the perturbed samples through the same featurizer:
     univariate_spike    one variable shifted by +-U(3, 5) sigma
     compound_moderate   a physically motivated pair (configs compound_pairs) shifted by U(1.5, 2.5) sigma each in the
                         configured directions (individually only moderately unusual)
     covariance_break    a strongly correlated training pair (|r| >= 0.4) shifted against its correlation by U(1.5, 2.5) sigma
   Bounded variables are clipped to their physical range; injections whose effective shift is < 70 % of the intended one
   are re-drawn on another sample. Metrics: average precision (PR-AUC), ROC-AUC, recall at the training-calibrated
   'moderate' threshold, and the flag rate on the non-injected samples.
   Caveat: the non-injected samples are real data and contain real anomalies, which count as 'negatives' here.
2. Stability across random seeds (Spearman correlation and top-2 % Jaccard overlap of real-data scores).
3. Real-data checks after the frozen decision: flag rates per split, agreement with independent station anomalies,
   and recall of literature-documented events (qualitative, small n).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import FEATS, Featurizer, model_matrix
from .paths import load

BOUNDS = {"sic": (0, 100), "rhum": (0, 100), "tcdc": (0, 100), "prate": (0, None), "wspd": (0, None)}
SPIKE_VARS = ["t2m", "slp", "wspd", "rhum", "prate", "tcdc", "z500", "sic"]


def correlated_pairs(z_train: np.ndarray, rmin: float = 0.4) -> list[tuple[str, str, float]]:
    c = np.corrcoef(model_matrix(z_train).T)
    out = []
    for i in range(len(FEATS)):
        for j in range(i + 1, len(FEATS)):
            if {FEATS[i], FEATS[j]} == {"sic", "dsic"}:
                continue
            if abs(c[i, j]) >= rmin:
                out.append((FEATS[i], FEATS[j], float(c[i, j])))
    return sorted(out, key=lambda t: -abs(t[2]))


def inject(df: pd.DataFrame, phys: np.ndarray, fz: Featurizer, seed: int, pairs: list, frac: float = 0.01) -> dict:
    """df/phys: rows of ONE split restricted to atm_valid. Returns perturbed physical array, labels and injection log."""
    rng = np.random.default_rng(seed)
    cfg = load("anomaly")
    n_inj = int(round(frac * len(df)))
    types = cfg["synthetic_tests"]["types"]
    per = {t: n_inj // len(types) for t in types}
    P = phys.copy()
    label = np.zeros(len(df), bool)
    kind = np.full(len(df), "", dtype=object)
    log = []
    sic_ok = df["sic_available"].values & (phys[:, FEATS.index("sic")] > 0)
    moy, cell = df["moy"].values.astype(np.int64), df["cell"].values.astype(np.int64)
    used = set()

    def std(v, i):
        return float(np.maximum(fz._lookup(v, "std", moy[i:i + 1], cell[i:i + 1])[0], load("anomaly")["std_floor"]["sic" if v == "dsic" else v]))

    def apply(i, shifts):
        """shifts: {var: k sigma}; returns True if all effective shifts are >= 70 % of intended."""
        new = {}
        for v, k in shifts.items():
            j = FEATS.index(v)
            s = std(v, i)
            x0 = P[i, j]
            x1 = x0 + k * s
            lo, hi = BOUNDS.get(v, (None, None))
            x1 = np.clip(x1, lo if lo is not None else -np.inf, hi if hi is not None else np.inf)
            if abs(x1 - x0) < 0.7 * abs(k) * s:
                return False
            new[v] = (j, x1, x1 - x0)
        for v, (j, x1, d) in new.items():
            P[i, j] = x1
            if v == "sic":
                P[i, FEATS.index("dsic")] += d          # the month-to-month change moves with the injected SIC
        return True

    for t in types:
        done = 0
        while done < per[t]:
            i = int(rng.integers(len(df)))
            if i in used:
                continue
            if t == "univariate_spike":
                v = SPIKE_VARS[int(rng.integers(len(SPIKE_VARS)))]
                if v == "sic" and not sic_ok[i]:
                    continue
                k = float(rng.uniform(3, 5)) * (1 if rng.random() < 0.5 else -1)
                ok = apply(i, {v: k})
                if not ok:
                    k = -k
                    ok = apply(i, {v: k})
                info = {v: k}
            elif t == "compound_moderate":
                p = cfg["compound_pairs"][int(rng.integers(len(cfg["compound_pairs"])))]
                if "sic" in (p["a"][0], p["b"][0]) and not sic_ok[i]:
                    continue
                info = {p["a"][0]: float(rng.uniform(1.5, 2.5)) * (1 if p["a"][1] == "+" else -1),
                        p["b"][0]: float(rng.uniform(1.5, 2.5)) * (1 if p["b"][1] == "+" else -1)}
                ok = apply(i, info)
                info["pair"] = p["name"]
            else:
                a, b, r = pairs[int(rng.integers(len(pairs)))]
                if ("sic" in (a, b) or "dsic" in (a, b)) and not sic_ok[i]:
                    continue
                s = 1 if rng.random() < 0.5 else -1
                info = {a: s * float(rng.uniform(1.5, 2.5)), b: -np.sign(r) * s * float(rng.uniform(1.5, 2.5))}
                ok = apply(i, info)
                info["pair"] = f"{a}~{b} (r={r:+.2f})"
            if not ok:
                continue
            used.add(i)
            label[i], kind[i] = True, t
            log.append({"row": i, "type": t, **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in info.items()}})
            done += 1
    return {"phys": P, "label": label, "kind": kind, "log": pd.DataFrame(log)}


def featurize_rows(fz: Featurizer, df: pd.DataFrame, P: np.ndarray, rows: np.ndarray) -> dict:
    X = {v: P[rows, j] for j, v in enumerate(FEATS)}
    return fz.transform(X, df["moy"].values[rows].astype(np.int64), df["cell"].values[rows].astype(np.int64))


def metrics(score: np.ndarray, label: np.ndarray, kind: np.ndarray, thr_moderate: float) -> dict:
    from sklearn.metrics import average_precision_score, roc_auc_score
    flag = score >= thr_moderate
    out = {"pr_auc": float(average_precision_score(label, score)), "roc_auc": float(roc_auc_score(label, score)),
           "recall_at_moderate": float(flag[label].mean()), "flag_rate_non_injected": float(flag[~label].mean()),
           "positives": int(label.sum()), "negatives": int((~label).sum())}
    for t in np.unique(kind[label]):
        m = (~label) | (kind == t)
        out[f"pr_auc_{t}"] = float(average_precision_score(label[m], score[m]))
        out[f"recall_at_moderate_{t}"] = float(flag[kind == t].mean())
    return out


def stability(a: np.ndarray, b: np.ndarray, top: float = 0.02) -> dict:
    from scipy.stats import spearmanr
    k = max(1, int(top * len(a)))
    ta, tb = set(np.argsort(-a)[:k]), set(np.argsort(-b)[:k])
    return {"spearman": float(spearmanr(a, b).statistic), "top2pct_jaccard": len(ta & tb) / len(ta | tb)}
