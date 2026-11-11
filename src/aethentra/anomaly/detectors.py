"""ML-04 Phases 5-6: anomaly detectors on the cell-month feature table. Every detector returns a score (higher = more unusual).

Statistical reference methods (always available):
  zscore       max_v |z_v|                      (z vs 1981-2010 calendar-month baseline)
  percentile   max_v -log10(2 min(p_v, 1-p_v))  (two-sided empirical tail probability, Weibull plotting position)
  mad          max_v |robust z_v|               (median / MAD baseline)
  mahalanobis  sqrt((z-mu_m)' S_m^-1 (z-mu_m))  (per calendar month, Ledoit-Wolf shrunk covariance of TRAINING features;
                                                 assumes roughly elliptical z vectors; reported with that caveat)
  seasonal     max_v |z of trailing 3-month mean|       (reference/reporting only; see climatology.seasonal_z)
  rolling      max_v |z vs trailing 30-yr baseline|     (reference/reporting only; see climatology.rolling_z)
ML methods (fitted on TRAINING 1979-2010 samples only):
  isolation_forest, lof (novelty=True), ocsvm (RBF), autoencoder (MLP, reconstruction MSE)
"""
from __future__ import annotations

import json
import logging
import time

import joblib
import numpy as np

from .features import FEATS, model_matrix
from .paths import MODELS

LOG = logging.getLogger("aethentra.ml04.detectors")
STAT_METHODS = ["zscore", "percentile", "mad", "mahalanobis"]
ML_METHODS = ["isolation_forest", "lof", "ocsvm", "autoencoder"]


def zscore_score(z):
    return np.nanmax(np.abs(model_matrix(z)), 1)


def mad_score(robust):
    r = np.asarray(robust).copy()
    r[~np.isfinite(r)] = 0.0
    return np.max(np.abs(np.clip(r, -50, 50)), 1)


def percentile_score(p):
    p = np.asarray(p, dtype=np.float64)
    q = 2 * np.minimum(p, 1 - p)
    s = -np.log10(np.clip(q, 1e-6, 1))
    s[~np.isfinite(p)] = 0.0
    return s.max(1)


class Mahalanobis:
    name = "mahalanobis"

    def fit(self, Z, moy):
        from sklearn.covariance import LedoitWolf
        self.mu, self.prec = {}, {}
        for m in range(1, 13):
            lw = LedoitWolf().fit(Z[moy == m])
            self.mu[m], self.prec[m] = lw.location_, lw.precision_
        return self

    def score(self, Z, moy):
        out = np.empty(len(Z))
        for m in range(1, 13):
            k = moy == m
            d = Z[k] - self.mu[m]
            out[k] = np.sqrt(np.einsum("ij,jk,ik->i", d, self.prec[m], d))
        return out


class SkModel:
    """Isolation Forest / LOF / One-Class SVM wrapper (score = -score_samples, i.e. higher = more anomalous)."""

    def __init__(self, kind: str, params: dict, n_fit: int | None = None, seed: int = 42):
        self.kind, self.params, self.n_fit, self.seed = kind, dict(params), n_fit, seed
        self.name = kind

    def fit(self, Z, moy=None):
        from sklearn.ensemble import IsolationForest
        from sklearn.neighbors import LocalOutlierFactor
        from sklearn.svm import OneClassSVM
        rng = np.random.default_rng(self.seed)
        if self.n_fit and len(Z) > self.n_fit:
            Z = Z[np.sort(rng.choice(len(Z), self.n_fit, replace=False))]
        t = time.time()
        if self.kind == "isolation_forest":
            self.m = IsolationForest(random_state=self.seed, n_jobs=-1, **self.params).fit(Z)
        elif self.kind == "lof":
            self.m = LocalOutlierFactor(novelty=True, n_jobs=-1, **self.params).fit(Z)
        elif self.kind == "ocsvm":
            self.m = OneClassSVM(kernel="rbf", cache_size=2000, **self.params).fit(Z)
        self.fit_seconds, self.n_train = time.time() - t, len(Z)
        return self

    def score(self, Z, moy=None):
        out = np.empty(len(Z))
        for s in range(0, len(Z), 100_000):
            out[s:s + 100_000] = -self.m.score_samples(Z[s:s + 100_000])
        return out


class Autoencoder:
    """MLP autoencoder 9-32-16-4-16-32-9 (GELU); trained on training samples, early stopping on validation reconstruction."""
    name = "autoencoder"

    def __init__(self, bottleneck: int = 4, hidden=(32, 16), epochs: int = 60, lr: float = 2e-3, seed: int = 42):
        self.bottleneck, self.hidden, self.epochs, self.lr, self.seed = bottleneck, tuple(hidden), epochs, lr, seed

    def _net(self, d):
        import torch.nn as nn
        h1, h2 = self.hidden
        enc = nn.Sequential(nn.Linear(d, h1), nn.GELU(), nn.Linear(h1, h2), nn.GELU(), nn.Linear(h2, self.bottleneck))
        dec = nn.Sequential(nn.Linear(self.bottleneck, h2), nn.GELU(), nn.Linear(h2, h1), nn.GELU(), nn.Linear(h1, d))
        return nn.Sequential(enc, dec)

    def fit(self, Z, moy=None, Zval=None):
        import torch
        torch.manual_seed(self.seed)
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        self.dev = dev
        net = self._net(Z.shape[1]).to(dev)
        opt = torch.optim.AdamW(net.parameters(), lr=self.lr, weight_decay=1e-5)
        X = torch.tensor(Z, dtype=torch.float32, device=dev)
        V = torch.tensor(Zval if Zval is not None else Z[:50_000], dtype=torch.float32, device=dev)
        g = torch.Generator(device="cpu").manual_seed(self.seed)
        best, best_state, bad, self.history = np.inf, None, 0, []
        t = time.time()
        for ep in range(self.epochs):
            net.train()
            perm = torch.randperm(len(X), generator=g).to(dev)
            for s in range(0, len(X), 4096):
                b = X[perm[s:s + 4096]]
                loss = ((net(b) - b) ** 2).mean()
                opt.zero_grad()
                loss.backward()
                opt.step()
            net.eval()
            with torch.no_grad():
                vl = float(((net(V) - V) ** 2).mean())
            self.history.append(vl)
            if vl < best - 1e-5:
                best, bad = vl, 0
                best_state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
            else:
                bad += 1
                if bad >= 6:
                    break
        net.load_state_dict(best_state)
        self.net = net.cpu().eval()
        self.best_epoch, self.fit_seconds, self.n_train = int(np.argmin(self.history)) + 1, time.time() - t, len(Z)
        return self

    def reconstruct(self, Z):
        import torch
        with torch.no_grad():
            return np.concatenate([self.net(torch.tensor(Z[s:s + 200_000], dtype=torch.float32)).numpy()
                                   for s in range(0, len(Z), 200_000)])

    def score(self, Z, moy=None):
        return ((self.reconstruct(Z) - Z) ** 2).mean(1)

    def __getstate__(self):
        d = self.__dict__.copy()
        if "net" in d:
            d["state_dict"] = {k: v.numpy() for k, v in d.pop("net").state_dict().items()}
        return d

    def __setstate__(self, d):
        sd = d.pop("state_dict", None)
        self.__dict__.update(d)
        if sd is not None:
            import torch
            self.net = self._net(len(FEATS))
            self.net.load_state_dict({k: torch.tensor(v) for k, v in sd.items()})
            self.net.eval()


def save(model, name: str, meta: dict):
    MODELS.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODELS / f"{name}.joblib")
    (MODELS / f"{name}.meta.json").write_text(json.dumps(meta, indent=1, default=str))


def load_model(name: str):
    return joblib.load(MODELS / f"{name}.joblib")


def severity_thresholds(train_scores: np.ndarray, classes: list[dict]) -> dict:
    qs = [c["below"] for c in classes[:-1]]
    t = np.quantile(train_scores[np.isfinite(train_scores)], qs)
    return {c["name"]: float(v) for c, v in zip(classes[1:], t)}   # lower bound of each non-normal class


def severity_of(score: np.ndarray, thr: dict) -> np.ndarray:
    names = ["normal"] + list(thr)
    k = np.zeros(score.shape, int)
    for i, v in enumerate(thr.values()):
        k[score >= v] = i + 1
    return np.array(names, dtype=object)[k]
