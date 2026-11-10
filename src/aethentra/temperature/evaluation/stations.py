"""Independent station evaluation (points vs 25 km cells).

Station anomalies use each station's OWN 1981-2010 daily climatology (same day-of-year method and smoothing as the gridded
climatology), so model/station comparisons are anomaly-to-anomaly and insensitive to elevation / representativeness offsets.
ERA5 assimilates SYNOP reports from many of these stations: agreement is therefore only partially independent and is
reported as such. Absolute-temperature bias (model cell vs station) is reported separately for information.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ...config import ROOT
from ..climatology.climatology import doy_index, smooth_circular
from ..paths import METRICS, load


def _zenodo() -> dict:
    cfg = load("data_sources")["stations"]["zenodo"]
    st = load("stations")["zenodo_to_ghcnd"]
    meta = _ghcnd_meta()
    out = {}
    for name, gid in st.items():
        p = ROOT / cfg["local_dir"] / f"{name}_surface_daily.csv"
        if not p.exists():
            continue
        d = pd.read_csv(p)
        s = pd.Series(d["Tmean"].to_numpy(float), index=pd.to_datetime(d["DATE"])).sort_index()
        s = s[~s.index.duplicated()]
        out[f"zenodo:{name}"] = {"series": s, **meta.loc[gid].to_dict(), "ghcnd_id": gid, "source": "Zenodo 17164992 (Turner et al.)"}
    return out


def _ghcnd_meta() -> pd.DataFrame:
    cfg = load("data_sources")["stations"]["ghcnd"]
    st = pd.read_fwf(ROOT / cfg["local_dir"] / "ghcnd-stations.txt", colspecs=[(0, 11), (12, 20), (21, 30), (31, 37), (41, 71)],
                     names=["id", "lat", "lon", "elev_m", "name"])
    return st.set_index("id")


def _ghcnd(exclude: set) -> dict:
    cfg = load("data_sources")["stations"]["ghcnd"]
    sel = pd.read_csv(ROOT / cfg["local_dir"] / "antarctic_stations_selected.csv")
    out = {}
    for _, r in sel.iterrows():
        if r["id"] in exclude:
            continue
        d = pd.read_csv(ROOT / cfg["local_dir"] / f"{r['id']}.csv", usecols=["DATE", "TAVG", "TAVG_ATTRIBUTES"], low_memory=False).dropna(subset=["TAVG"])
        q = d["TAVG_ATTRIBUTES"].fillna(",,").str.split(",", expand=True)[1].fillna("").str.strip()
        d = d[q == ""]                                                       # drop values with any GHCN quality flag
        s = pd.Series(d["TAVG"].to_numpy(float) / 10.0, index=pd.to_datetime(d["DATE"])).sort_index()
        out[f"ghcnd:{r['id']}"] = {"series": s[~s.index.duplicated()], "lat": r["lat"], "lon": r["lon"], "elev_m": r["elev_m"],
                                   "name": r["name"], "ghcnd_id": r["id"], "source": "NOAA GHCN-Daily TAVG"}
    return out


def station_climatology(s: pd.Series, period=(1981, 2010), half=15, min_years=15) -> np.ndarray | None:
    ref = s[(s.index.year >= period[0]) & (s.index.year <= period[1])].dropna()
    if ref.index.year.nunique() < min_years:
        return None
    d = doy_index(ref.index)
    sums = np.bincount(d, ref.to_numpy(), 365)
    cnt = np.bincount(d, minlength=365)
    m = np.where(cnt > 0, sums / np.maximum(cnt, 1), np.nan)
    if np.isnan(m).any():
        m = pd.Series(m).interpolate(limit_direction="both").to_numpy()
    return smooth_circular(m[:, None], half)[:, 0]


def nearest_cell(grid: dict, lat: float, lon: float, prefer_land: bool = True) -> tuple[int, float]:
    la, lo = np.radians(grid["lat"]), np.radians(grid["lon"])
    p, q = np.radians(lat), np.radians(lon)
    d = 6371 * np.arccos(np.clip(np.sin(la) * np.sin(p) + np.cos(la) * np.cos(p) * np.cos(lo - q), -1, 1))
    if prefer_land:
        d = np.where(grid["land"], d, d + 1e6) if (grid["land"] & (d < 50)).any() else d
    i = int(np.argmin(d))
    return i, float(d[i] % 1e6)


def evaluate_stations(ctx, tag: str = "test_final") -> dict:
    """Uses the saved test fields (obs reanalysis anomaly, final model, persistence) of the single test evaluation."""
    with np.load(METRICS / tag / "fields.npz") as z:                 # load once (NpzFile decompresses on every access)
        fz = {k: z[k] for k in ("dates", "obs_anom", "final_model", "persistence", "climatology")}
    dates = pd.to_datetime(fz["dates"])
    clim_week = np.stack([ctx.clim.window_mean("t2m", t + pd.Timedelta(days=1), load("features")["labels"]["horizon_days"]) for t in dates])
    h, need = load("features")["labels"]["horizon_days"], load("stations")["min_valid_days_per_week"]
    zen = _zenodo()
    stations = {**zen, **_ghcnd({v["ghcnd_id"] for v in zen.values()})}
    per, pooled = [], {k: [] for k in ("station", "reanalysis", "final_model", "persistence", "climatology")}
    for sid, st in stations.items():
        clim = station_climatology(st["series"])
        if clim is None:
            continue
        cell, dist = nearest_cell(ctx.cube.grid, st["lat"], st["lon"])
        s = st["series"]
        rows = []
        for i, t in enumerate(dates):
            win = pd.date_range(t + pd.Timedelta(days=1), periods=h)
            v = s.reindex(win)
            if v.notna().sum() < need:
                continue
            a = float((v - clim[doy_index(win)]).mean())
            rows.append((a, float(fz["obs_anom"][i, cell]), float(fz["final_model"][i, cell]), float(fz["persistence"][i, cell]),
                         float(fz["climatology"][i, cell]), float(v.mean()), float(clim_week[i, cell])))
        if len(rows) < 20:
            continue
        r = np.array(rows)
        res = {"station": sid, "name": st["name"], "source": st["source"], "lat": st["lat"], "lon": st["lon"], "elev_m": st["elev_m"],
               "cell": cell, "cell_distance_km": round(dist, 1), "cell_elevation_m": float(ctx.cube.grid["elevation_m"][cell]),
               "n_weeks": len(r)}
        for j, k in ((1, "reanalysis"), (2, "final_model"), (3, "persistence"), (4, "climatology")):
            e = r[:, j] - r[:, 0]
            res[f"{k}_anom_mae"] = float(np.abs(e).mean())
            res[f"{k}_anom_rmse"] = float(np.sqrt((e ** 2).mean()))
            res[f"{k}_anom_corr"] = float(np.corrcoef(r[:, j], r[:, 0])[0, 1]) if np.std(r[:, j]) > 0 else None
        res["model_abs_t2m_bias_vs_station"] = float(np.mean(r[:, 6] + r[:, 2] - r[:, 5]))
        per.append(res)
        for j, k in ((0, "station"), (1, "reanalysis"), (2, "final_model"), (3, "persistence"), (4, "climatology")):
            pooled[k].append(r[:, j])
    P = {k: np.concatenate(v) for k, v in pooled.items()}
    summary = {}
    for k in ("reanalysis", "final_model", "persistence", "climatology"):
        e = P[k] - P["station"]
        summary[k] = {"anom_mae_degC": float(np.abs(e).mean()), "anom_rmse_degC": float(np.sqrt((e ** 2).mean())),
                      "anom_corr": float(np.corrcoef(P[k], P["station"])[0, 1]) if np.std(P[k]) > 0 else None}
    out = {"tag": tag, "n_stations": len(per), "n_station_weeks": int(P["station"].size), "pooled": summary, "stations": per,
           "note": "Station anomalies vs each station's own 1981-2010 climatology; nearest 25 km cell (land preferred). "
                   "Reanalysis assimilates many of these stations -> partially independent."}
    (METRICS / "station_evaluation_test.json").write_text(json.dumps(out, indent=1))
    return out
