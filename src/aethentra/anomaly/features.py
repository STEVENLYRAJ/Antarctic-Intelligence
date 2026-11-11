"""ML-04 Phase 4: cell-month feature table (model baseline 1981-2010).

One sample = one 2.5 deg cell in one calendar month. Features (all standardised against the cell's own calendar-month
climatology, so location and season are removed before any detector sees the data):

  z_t2m, z_slp, z_wspd, z_rhum, z_prate, z_tcdc, z_z500, z_sic, z_dsic   (dsic = SIC change from the previous month)

Also kept per sample: robust z (median/MAD) and empirical percentile rank for every variable (statistical detectors),
physical values (for synthetic injection and reporting) and validity flags.
* SIC exists only for ocean cells (>= 25 % valid 25 km ocean pixels). Elsewhere z_sic / z_dsic are imputed as 0
  ("no sea-ice anomaly is possible") and `sic_available` is False.
* A sample is `atm_valid` only if all seven atmospheric variables exist (NCEP R1 ends 2026-03-17 -> no multivariate
  scores after February 2026; univariate SIC anomalies continue).
* z values are clipped to +-8 for the multivariate detectors only (raw values stay in the univariate products).
Only the current and previous month enter a sample: no future information.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .climatology import load_clim, monthly, monthly_dsic
from .paths import FEATURES, INTERIM, load
from .preprocessing import ALL_VARS, ATM_VARS, grid, month_index

FEATS = ALL_VARS + ["dsic"]
CLIP = 8.0


def _floor(v):
    f = load("anomaly")["std_floor"]
    return f.get("sic" if v == "dsic" else v, 0.0)


class Featurizer:
    """Maps physical cell-month values -> standardised features using the frozen 1981-2010 baseline."""

    def __init__(self, baseline: str = "model"):
        self.baseline = baseline
        self.clim = {v: load_clim(baseline, v) for v in FEATS}
        g = grid()
        self.shape = (g["lat"].size, g["lon"].size)
        self.ncell = int(np.prod(self.shape))

    def _lookup(self, v, key, moy, cell):
        a = self.clim[v][key]                                      # (12, lat, lon) or (12, n, lat, lon)
        if a.ndim == 3:
            return a.reshape(12, -1)[moy - 1, cell]
        return a.reshape(12, a.shape[1], -1)[moy - 1, :, cell]     # (N, n)

    def transform(self, X: dict, moy: np.ndarray, cell: np.ndarray) -> dict:
        """X: {var: (N,) physical values incl. 'dsic'} -> {'z','robust','percentile': (N, 9)}."""
        out = {k: np.full((moy.size, len(FEATS)), np.nan, np.float32) for k in ("z", "robust", "percentile")}
        for j, v in enumerate(FEATS):
            x = X[v].astype(np.float32)
            f = _floor(v)
            mean, std = self._lookup(v, "mean", moy, cell), np.maximum(self._lookup(v, "std", moy, cell), f)
            med, mad = self._lookup(v, "median", moy, cell), np.maximum(self._lookup(v, "mad", moy, cell), f)
            out["z"][:, j] = (x - mean) / std
            out["robust"][:, j] = (x - med) / mad
            for s in range(0, moy.size, 200_000):
                srt = self._lookup(v, "sorted", moy[s:s + 200_000], cell[s:s + 200_000])
                xs = x[s:s + 200_000, None]
                n = np.isfinite(srt).sum(1)
                below = (srt < xs).sum(1) + 0.5 * (srt == xs).sum(1)
                with np.errstate(invalid="ignore", divide="ignore"):
                    p = (below + 0.5) / (n + 1.0)
                out["percentile"][s:s + 200_000, j] = np.where((n > 0) & np.isfinite(x[s:s + 200_000]), p, np.nan)
        return out


def model_matrix(z: np.ndarray) -> np.ndarray:
    """Standardised feature matrix for the multivariate detectors: SIC NaN -> 0 (no sea ice possible), clip +-8."""
    m = z.copy()
    m[:, FEATS.index("sic")] = np.nan_to_num(m[:, FEATS.index("sic")], nan=0.0)
    m[:, FEATS.index("dsic")] = np.nan_to_num(m[:, FEATS.index("dsic")], nan=0.0)
    return np.clip(m, -CLIP, CLIP)


def split_of(year: np.ndarray) -> np.ndarray:
    s = load("anomaly")["splits"]
    out = np.full(year.shape, "none", dtype=object)
    for k in ("train", "validation", "test", "operational"):
        a, b = s[k]
        out[(year >= a) & (year <= b)] = k
    return out


def build_table() -> pd.DataFrame:
    """All cell-months -> FEATURES/table.parquet (+ physical values) and arrays z/robust/percentile .npy."""
    FEATURES.mkdir(parents=True, exist_ok=True)
    months = month_index()
    g = grid()
    nT, (nl, nm) = months.size, g["cell_area_km2"].shape
    ncell = nl * nm
    X = {v: np.asarray(monthly(v)).reshape(nT, ncell) for v in ALL_VARS}
    X["dsic"] = monthly_dsic().reshape(nT, ncell)
    t_idx, cell = np.repeat(np.arange(nT), ncell), np.tile(np.arange(ncell), nT)
    moy = months.month.values[t_idx].astype(np.int64)
    flat = {v: X[v].ravel() for v in FEATS}
    fz = Featurizer("model").transform(flat, moy, cell)
    np.save(FEATURES / "z.npy", fz["z"])
    np.save(FEATURES / "robust.npy", fz["robust"])
    np.save(FEATURES / "percentile.npy", fz["percentile"])
    np.save(FEATURES / "physical.npy", np.stack([flat[v] for v in FEATS], 1).astype(np.float32))
    year = months.year.values[t_idx]
    ofrac = np.load(INTERIM / "ocean_fraction.npy").ravel()
    df = pd.DataFrame({"month": months.strftime("%Y-%m").values[t_idx], "year": year.astype(np.int16), "moy": moy.astype(np.int8),
                       "cell": cell.astype(np.int32), "row": (cell // nm).astype(np.int16), "col": (cell % nm).astype(np.int16),
                       "lat": g["lat"][cell // nm].astype(np.float32), "lon": g["lon"][cell % nm].astype(np.float32),
                       "area_km2": g["cell_area_km2"].ravel()[cell].astype(np.float32),
                       "ocean_fraction": ofrac[cell].astype(np.float32),
                       "atm_valid": np.isfinite(np.stack([flat[v] for v in ATM_VARS], 1)).all(1),
                       "sic_available": np.isfinite(flat["sic"]) & np.isfinite(flat["dsic"])})
    df["split"] = split_of(year)
    df.to_parquet(FEATURES / "table.parquet", index=False)
    meta = {"features": FEATS, "baseline": "model (1981-2010)", "n_samples": int(len(df)), "months": [str(months[0].date()), str(months[-1].date())],
            "by_split": df.groupby("split").size().to_dict(), "atm_valid_by_split": df.groupby("split")["atm_valid"].sum().astype(int).to_dict(),
            "clip": CLIP, "imputation": "z_sic, z_dsic = 0 where SIC unavailable (land / ice sheet / <25 % ocean)"}
    (FEATURES / "table.json").write_text(json.dumps(meta, indent=1, default=int))
    return df


def load_table():
    df = pd.read_parquet(FEATURES / "table.parquet")
    arr = {k: np.load(FEATURES / f"{k}.npy", mmap_mode="r") for k in ("z", "robust", "percentile", "physical")}
    return df, arr


def correlations(z: np.ndarray, mask: np.ndarray) -> pd.DataFrame:
    m = model_matrix(np.asarray(z[mask]))
    return pd.DataFrame(np.corrcoef(m.T), index=FEATS, columns=FEATS)
