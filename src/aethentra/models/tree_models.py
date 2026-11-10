"""Tabular grid-cell models with a common interface.

target_mode = 'residual': the model learns (target - persistence) and the forecast is clip(persistence + yhat, 0, 100).
target_mode = 'absolute': the model learns the target directly (ablation).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ..baselines.baselines import fallback

try:
    import psutil
    N_THREADS = psutil.cpu_count(logical=False) or 8
except Exception:  # pragma: no cover
    N_THREADS = 8


class TreeModel:
    def __init__(self, kind: str, features: list[str], params: dict, target_mode: str = "residual", name: str | None = None,
                 quantile: float | None = None):
        self.kind, self.features, self.params, self.target_mode = kind, list(features), dict(params), target_mode
        self.quantile = quantile
        self.name = name or kind
        self.model = None
        self.history: dict = {}
        self.best_iteration = None
        self.fit_seconds = None

    # ------------------------------------------------------------------ helpers
    def _y(self, df: pd.DataFrame) -> np.ndarray:
        y = df["target"].to_numpy(np.float32)
        return y - df["persistence"].to_numpy(np.float32) if self.target_mode == "residual" else y

    def _to_sic(self, raw: np.ndarray, persistence: np.ndarray) -> np.ndarray:
        out = persistence + raw if self.target_mode == "residual" else raw
        return out

    # ------------------------------------------------------------------ fit
    def fit(self, tr: pd.DataFrame, va: pd.DataFrame | None, seed: int = 42, n_estimators: int | None = None,
            early_stopping: bool = True):
        Xtr, ytr = tr[self.features], self._y(tr)
        t0 = time.time()
        p = dict(self.params)
        es = p.pop("early_stopping_rounds", 100)
        n_est = n_estimators or p.pop("n_estimators", 1000)
        p.pop("n_estimators", None)
        if self.kind == "lightgbm":
            import lightgbm as lgb
            if self.quantile is not None:
                p.update(objective="quantile", alpha=self.quantile)
            p.update(seed=seed, verbose=-1, num_threads=N_THREADS)   # explicit: num_threads=0 is ~10x slower on Windows
            dtr = lgb.Dataset(Xtr, ytr, categorical_feature=["sector"] if "sector" in self.features else "auto", free_raw_data=True)
            vs, cbs, ev = [dtr], [], {}
            if va is not None:
                dva = lgb.Dataset(va[self.features], self._y(va), reference=dtr)
                vs = [dtr, dva]
                cbs.append(lgb.record_evaluation(ev))
                if early_stopping:
                    cbs.append(lgb.early_stopping(es, verbose=False))
            self.model = lgb.train(p, dtr, num_boost_round=n_est, valid_sets=vs, valid_names=["train", "valid"][:len(vs)], callbacks=cbs)
            self.best_iteration = self.model.best_iteration or n_est
            self.history = {k: {m: list(map(float, v)) for m, v in d.items()} for k, d in ev.items()}
        elif self.kind == "xgboost":
            import xgboost as xgb
            p.update(random_state=seed, tree_method="hist", n_estimators=n_est)
            if va is not None and early_stopping:
                p["early_stopping_rounds"] = es
            p.setdefault("eval_metric", "mae")
            self.model = xgb.XGBRegressor(**p)
            ev = [(Xtr, ytr)] + ([(va[self.features], self._y(va))] if va is not None else [])
            self.model.fit(Xtr, ytr, eval_set=ev, verbose=False)
            r = self.model.evals_result()
            self.history = {("train" if k == "validation_0" else "valid"): v for k, v in r.items()}
            self.best_iteration = int(getattr(self.model, "best_iteration", n_est - 1) or n_est - 1) + 1
        elif self.kind == "random_forest":
            from sklearn.ensemble import RandomForestRegressor
            q = {k: v for k, v in p.items() if k != "max_train_rows"}
            self.model = RandomForestRegressor(n_estimators=n_est, random_state=seed, n_jobs=-1, **q)
            self.model.fit(Xtr.fillna(-999).to_numpy(np.float32), ytr)
            self.best_iteration = n_est
        else:
            raise ValueError(self.kind)
        self.fit_seconds = time.time() - t0
        return self

    # ------------------------------------------------------------------ predict
    def predict_raw(self, X: pd.DataFrame) -> np.ndarray:
        if self.kind == "lightgbm":
            return self.model.predict(X[self.features], num_iteration=self.best_iteration)
        if self.kind == "xgboost":
            return self.model.predict(X[self.features], iteration_range=(0, self.best_iteration))
        return self.model.predict(X[self.features].fillna(-999).to_numpy(np.float32))

    def predict_sic(self, X: pd.DataFrame, clip: bool = True) -> np.ndarray:
        out = self._to_sic(self.predict_raw(X), X["persistence"].to_numpy(np.float32))
        return np.clip(out, 0, 100) if clip else out

    def predict_grid(self, F: dict, active: np.ndarray, clip: bool = True) -> tuple[np.ndarray, dict]:
        """Model on active cells with a valid persistence value; persistence/fallback elsewhere."""
        base = fallback(F["sic_d0"].copy(), F)
        m = active & np.isfinite(F["sic_d0"])
        idx = np.flatnonzero(m)
        info = {"model_cells": int(idx.size), "pre_clip_below_0": 0, "pre_clip_above_100": 0}
        if idx.size:
            X = pd.DataFrame({n: F[n].ravel()[idx] for n in self.features})
            X["persistence"] = F["sic_d0"].ravel()[idx]
            raw = self.predict_sic(X, clip=False)
            info["pre_clip_below_0"] = int((raw < 0).sum())
            info["pre_clip_above_100"] = int((raw > 100).sum())
            out = base.ravel().copy()
            out[idx] = np.clip(raw, 0, 100) if clip else raw
            base = out.reshape(base.shape)
        return base.astype(np.float32), info

    # ------------------------------------------------------------------ persistence
    def save(self, directory: Path, extra: dict | None = None) -> dict:
        directory.mkdir(parents=True, exist_ok=True)
        if self.kind == "lightgbm":
            f = directory / f"{self.name}.lgb.txt"
            self.model.save_model(str(f), num_iteration=self.best_iteration)
        elif self.kind == "xgboost":
            f = directory / f"{self.name}.xgb.json"
            self.model.save_model(str(f))
        else:
            f = directory / f"{self.name}.joblib"
            joblib.dump(self.model, f, compress=3)
        meta = {"name": self.name, "kind": self.kind, "file": f.name, "features": self.features, "params": self.params,
                "target_mode": self.target_mode, "quantile": self.quantile, "best_iteration": self.best_iteration,
                "fit_seconds": self.fit_seconds, **(extra or {})}
        (directory / f"{self.name}.meta.json").write_text(json.dumps(meta, indent=2, default=str))
        if self.history:
            (directory / f"{self.name}.history.json").write_text(json.dumps(self.history))
        return meta

    @classmethod
    def load(cls, directory: Path, name: str) -> "TreeModel":
        meta = json.loads((directory / f"{name}.meta.json").read_text())
        m = cls(meta["kind"], meta["features"], meta["params"], meta["target_mode"], meta["name"], meta.get("quantile"))
        f = directory / meta["file"]
        if m.kind == "lightgbm":
            import lightgbm as lgb
            m.model = lgb.Booster(model_file=str(f))
            m.best_iteration = None          # saved with best iteration only
        elif m.kind == "xgboost":
            import xgboost as xgb
            m.model = xgb.XGBRegressor()
            m.model.load_model(str(f))
            m.best_iteration = meta["best_iteration"]
        else:
            m.model = joblib.load(f)
        m.meta = meta
        return m
