"""ML-02 tabular models: predict the weekly T2m anomaly (label B); absolute T = climatology of the target week + anomaly.

Reuses the ML-01 ``TreeModel`` (LightGBM / XGBoost / Random Forest, early stopping, save/load) with an anomaly target.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ...models.tree_models import TreeModel


class AnomalyModel(TreeModel):
    def __init__(self, kind, features, params, target_mode: str = "anomaly", name=None, quantile=None):
        super().__init__(kind, features, params, target_mode, name, quantile)

    def _y(self, df: pd.DataFrame) -> np.ndarray:
        return df["target_anom"].to_numpy(np.float32)

    def predict_anom(self, X: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.predict_raw(X), np.float32)

    def predict_cells(self, F: dict) -> np.ndarray:
        """Anomaly forecast for every cell with a defined last-week anomaly (NaN elsewhere)."""
        ok = np.isfinite(F["anom_w1"])
        out = np.full(ok.shape, np.nan, np.float32)
        idx = np.flatnonzero(ok)
        if idx.size:
            out[idx] = self.predict_anom(pd.DataFrame({n: F[n][idx] for n in self.features}))
        return out
