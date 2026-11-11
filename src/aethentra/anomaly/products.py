"""ML-04 Phases 7-9 and 11-12: severity, compound co-occurrence, spatial clusters / events, explanations and products.

Severity: base-rate classes from the training-period score distribution (normal < P90 <= mild < P95 <= moderate < P98 <= strong
< P99.5 <= extreme). Univariate reporting classes use the same quantiles of |z| over the 1991-2020 baseline years.

'confidence' is NOT a probability. It is reported as two separate indicators:
  method_agreement   how many of {zscore, percentile, mad, selected multivariate} flag the cell-month (>= moderate), k/4
  data_tier          A: observation-constrained (t2m, slp, z500 in NCEP R1; SIC passive-microwave CDR),
                     B: partly constrained (wind, humidity), C: model forecast fields (precipitation, cloud) with known
                     large errors over Antarctica.
"""
from __future__ import annotations

import datetime as dt
import json
import logging

import numpy as np
import pandas as pd

from ..config import ROOT
from ..config import load as load_cfg
from .climatology import anomalies, baseline_years, load_clim, monthly, monthly_dsic, seasonal_z
from .features import FEATS, load_table, model_matrix
from .paths import FEATURES, METRICS, MODELS, OUTPUTS, PROCESSED, load
from .preprocessing import ALL_VARS, grid, month_index

LOG = logging.getLogger("aethentra.ml04.products")
DATA_TIER = {"t2m": "A", "slp": "A", "z500": "A", "sic": "A", "dsic": "A", "wspd": "B", "rhum": "B", "prate": "C", "tcdc": "C"}
UNITS = {"t2m": "degC", "slp": "hPa", "wspd": "m s-1", "rhum": "%", "prate": "mm day-1", "tcdc": "%", "z500": "m", "sic": "%",
         "dsic": "percentage points"}
SEASONS = {2: "DJF", 5: "MAM", 8: "JJA", 11: "SON"}
CLASS_NAMES = ["normal", "mild", "moderate", "strong", "extreme"]


def regions() -> np.ndarray:
    """Coarse region per 2.5 deg cell: NSIDC ocean sectors for ocean cells (>= 50 % ocean), boxes on the ice sheet."""
    g = grid()
    lat, lon = np.meshgrid(g["lat"], np.where(g["lon"] > 180, g["lon"] - 360, g["lon"]), indexing="ij")
    ofr = np.load(ROOT / "data" / "interim" / "ml04" / "ocean_fraction.npy")
    sect = load_cfg("features")["sectors"]                     # standard NSIDC sectors shared with ML-01
    out = np.full(lat.shape, "", dtype=object)
    for n, (a, b) in sect.items():
        m = (lon >= a) & (lon < b) if a < b else (lon >= a) | (lon < b)
        out[m & (ofr >= 0.5)] = n
    land = ofr < 0.5
    pen = land & (lon >= -75) & (lon < -55) & (lat >= -75)
    west = land & ~pen & (lon >= -180) & (lon < -40) & (lat >= -88)
    out[land] = "east_antarctica"
    out[west] = "west_antarctica"
    out[pen] = "antarctic_peninsula"
    return out


def _sev(absz: np.ndarray, thr: list[float]) -> np.ndarray:
    k = np.zeros(absz.shape, np.int8)
    for i, t in enumerate(thr):
        k[absz >= t] = i + 1
    k[~np.isfinite(absz)] = -1
    return k


def univariate_thresholds() -> dict:
    """|z| quantiles over the 1991-2020 baseline years, per variable (reporting severity classes)."""
    p = PROCESSED / "univariate_thresholds_1991-2020.json"
    if p.exists():
        return json.loads(p.read_text())
    months = month_index()
    y0, y1 = baseline_years("reporting")
    sel = (months.year >= y0) & (months.year <= y1)
    qs = [c["below"] for c in load("anomaly")["severity"]["classes"][:-1]]
    out = {}
    for v in FEATS:
        X = monthly_dsic() if v == "dsic" else np.asarray(monthly(v))
        a = anomalies(v, X[sel], months.month.values[sel], "reporting")["z"]
        out[v] = [float(x) for x in np.nanquantile(np.abs(a), qs)]
    p.write_text(json.dumps(out, indent=1))
    return out


def reporting_cube() -> dict:
    """Univariate anomalies of every variable vs 1991-2020 for all months -> outputs/ml04/anomalies_monthly_1991-2020.nc."""
    import xarray as xr
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    months, g = month_index(), grid()
    thr = univariate_thresholds()
    data = {}
    for v in FEATS:
        X = monthly_dsic() if v == "dsic" else np.asarray(monthly(v))
        a = anomalies(v, X, months.month.values, "reporting")
        dims = ("time", "lat", "lon")
        data[f"{v}"] = (dims, X.astype(np.float32), {"units": UNITS[v], "long_name": f"monthly mean {v}"})
        data[f"{v}_anomaly"] = (dims, a["absolute"], {"units": UNITS[v], "long_name": f"{v} minus 1991-2020 calendar-month mean"})
        data[f"{v}_z"] = (dims, a["z"], {"units": "1", "long_name": f"{v} standardised anomaly (1991-2020)"})
        data[f"{v}_percentile"] = (dims, (100 * a["percentile"]).astype(np.float32),
                                   {"units": "percent", "long_name": f"{v} empirical percentile within 1991-2020 (Weibull)"})
        data[f"{v}_severity"] = (dims, _sev(np.abs(a["z"]), thr[v]),
                                 {"flag_values": "-1 0 1 2 3 4", "flag_meanings": "no_data " + " ".join(CLASS_NAMES),
                                  "long_name": f"{v} statistical severity class (|z| base-rate classes, 1991-2020)"})
    ds = xr.Dataset(data, coords={"time": months.values, "lat": g["lat"], "lon": g["lon"]},
                    attrs={"title": "AETHENTRA ML-04 monthly univariate climate anomalies", "baseline": "1991-2020 (fixed)",
                           "source": "NCEP/NCAR Reanalysis 1 daily means (NOAA PSL); NOAA/NSIDC SIC CDR v6",
                           "grid": "NCEP R1 native 2.5 deg regular lat/lon (cell centres), EPSG:4326",
                           "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                           "nature": "statistical anomalies; not attribution; not confirmed extreme events",
                           "Conventions": "CF-1.8"})
    enc = {k: {"zlib": True, "complevel": 4} for k in data}
    dst = OUTPUTS / "anomalies_monthly_1991-2020.nc"
    ds.to_netcdf(dst, encoding=enc)
    return {"file": dst.name, "variables": len(data), "months": int(months.size)}


# ------------------------------------------------------------------ scored table helpers
def scored_table() -> pd.DataFrame:
    df, A = load_table()
    sc = pd.read_parquet(FEATURES / "scores.parquet")
    d = json.loads((MODELS / "decision.json").read_text())
    sel = d["selected_multivariate"]
    t = df.iloc[sc["idx"].values].reset_index(drop=True)
    for c in sc.columns:
        if c != "idx":
            t[c] = sc[c].values
    t["row_idx"] = sc["idx"].values
    flag = lambda s: s.isin(["moderate", "strong", "extreme"])  # noqa: E731
    t["agreement"] = (flag(t["sev_zscore"]).astype(int) + flag(t["sev_percentile"]).astype(int) + flag(t["sev_mad"]).astype(int)
                      + flag(t[f"sev_{sel}"]).astype(int))
    t["selected"] = sel
    t["region"] = regions().ravel()[t["cell"].values]
    return t


def contributions(model_name: str, Z: np.ndarray, moy: np.ndarray) -> np.ndarray:
    """Ablation contribution per feature: score(x) - score(x with that feature set to its climatological normal, z = 0)."""
    from .detectors import load_model
    from .training import score_methods
    m = load_model(model_name) if model_name not in ("zscore", "percentile", "mad") else None
    base = m.score(Z, moy)
    out = np.zeros(Z.shape, np.float32)
    for j in range(Z.shape[1]):
        Zj = Z.copy()
        Zj[:, j] = 0.0
        out[:, j] = base - m.score(Zj, moy)
    return out


def explain_flagged(t: pd.DataFrame) -> pd.DataFrame:
    sel = t["selected"].iloc[0]
    _, A = load_table()
    f = t[t[f"sev_{sel}"].isin(["moderate", "strong", "extreme"])].copy()
    Z = model_matrix(np.asarray(A["z"][f["row_idx"].values]))
    C = contributions(sel, Z, f["moy"].values)
    for j, v in enumerate(FEATS):
        f[f"z_{v}"] = Z[:, j]
        f[f"contrib_{v}"] = C[:, j]
    order = np.argsort(-C, 1)
    f["top_variables"] = [",".join(FEATS[k] for k in o[:3]) for o in order]
    f.to_parquet(FEATURES / "explained_flagged.parquet", index=False)
    return f


# ------------------------------------------------------------------ compound co-occurrence, clusters, events
def compound_cooccurrence() -> pd.DataFrame:
    """Cell-months where both members of a configured pair are >= moderate (|z| base-rate class) in the configured directions."""
    df, A = load_table()
    uth = univariate_thresholds_model()
    z = np.asarray(A["z"])
    rows = []
    for p in load("anomaly")["compound_pairs"]:
        (va, sa), (vb, sb) = p["a"], p["b"]
        ia, ib = FEATS.index(va), FEATS.index(vb)
        ok_a = (z[:, ia] >= uth[va][1]) if sa == "+" else (z[:, ia] <= -uth[va][1])
        ok_b = (z[:, ib] >= uth[vb][1]) if sb == "+" else (z[:, ib] <= -uth[vb][1])
        hit = ok_a & ok_b & df["atm_valid"].values
        exp = float(np.mean(ok_a[df["atm_valid"].values & (df["split"] == "train").values])
                    * np.mean(ok_b[df["atm_valid"].values & (df["split"] == "train").values]))
        for i in np.flatnonzero(hit):
            rows.append({"pair": p["name"], "idx": int(i), "month": df["month"].values[i], "cell": int(df["cell"].values[i]),
                         "lat": float(df["lat"].values[i]), "lon": float(df["lon"].values[i]),
                         f"z_a": float(z[i, ia]), f"z_b": float(z[i, ib]), "expected_rate_if_independent": exp})
    out = pd.DataFrame(rows)
    out.to_parquet(FEATURES / "compound_cooccurrence.parquet", index=False)
    return out


def univariate_thresholds_model() -> dict:
    """|z| class bounds over the TRAINING period (model baseline) per variable; [mild, moderate, strong, extreme]."""
    p = MODELS / "univariate_thresholds_train.json"
    if p.exists():
        return json.loads(p.read_text())
    df, A = load_table()
    m = (df["split"] == "train").values & df["atm_valid"].values
    qs = [c["below"] for c in load("anomaly")["severity"]["classes"][:-1]]
    z = np.asarray(A["z"])[m]
    out = {v: [float(x) for x in np.nanquantile(np.abs(z[:, j]), qs)] for j, v in enumerate(FEATS)}
    p.write_text(json.dumps(out, indent=1))
    return out


def clusters_and_events(t: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """DBSCAN (haversine) of flagged cells per month -> clusters; clusters linked across consecutive months -> events."""
    from sklearn.cluster import DBSCAN
    c = load("anomaly")["clustering"]
    sel = t["selected"].iloc[0]
    f = t[t[f"sev_{sel}"].isin(["moderate", "strong", "extreme"])]
    rows = []
    for mo, g in f.groupby("month"):
        X = np.deg2rad(g[["lat", "lon"]].values)
        lab = DBSCAN(eps=c["eps_km"] / 6371.0, min_samples=c["min_samples"], metric="haversine").fit_predict(X)
        for k in set(lab) - {-1}:
            h = g[lab == k]
            w = h["area_km2"].values
            xyz = np.c_[np.cos(np.deg2rad(h.lat)) * np.cos(np.deg2rad(h.lon)), np.cos(np.deg2rad(h.lat)) * np.sin(np.deg2rad(h.lon)),
                        np.sin(np.deg2rad(h.lat))]
            m = (xyz * w[:, None]).sum(0)
            rows.append({"month": mo, "cluster": int(k), "n_cells": int(len(h)), "area_km2": float(w.sum()),
                         "centroid_lat": float(np.rad2deg(np.arcsin(m[2] / np.linalg.norm(m)))),
                         "centroid_lon": float(np.rad2deg(np.arctan2(m[1], m[0]))),
                         "peak_score": float(h[f"score_{sel}"].max()), "mean_agreement": float(h["agreement"].mean()),
                         "regions": ",".join(sorted(h["region"].value_counts().index[:3])), "cells": h["cell"].tolist()})
    cl = pd.DataFrame(rows)
    # temporal linking: a cluster continues an event if it shares >= 1 cell (or centroid within 1000 km) with a cluster
    # of the previous month
    cl = cl.sort_values(["month", "cluster"]).reset_index(drop=True)
    ev = np.full(len(cl), -1)
    nxt = 0
    prev = []
    for mo in cl["month"].unique():
        cur = np.flatnonzero(cl["month"].values == mo)
        pm = (pd.Period(mo) - 1).strftime("%Y-%m")
        prev = np.flatnonzero(cl["month"].values == pm)
        for i in cur:
            best = -1
            for j in prev:
                share = len(set(cl.at[i, "cells"]) & set(cl.at[j, "cells"]))
                d = _gc_km(cl.at[i, "centroid_lat"], cl.at[i, "centroid_lon"], cl.at[j, "centroid_lat"], cl.at[j, "centroid_lon"])
                if share > 0 or d < 1000:
                    best = ev[j]
                    break
            if best < 0:
                best, nxt = nxt, nxt + 1
            ev[i] = best
    cl["event_id"] = ev
    events = cl.groupby("event_id").agg(start=("month", "min"), end=("month", "max"), n_months=("month", "nunique"),
                                        max_area_km2=("area_km2", "max"), peak_score=("peak_score", "max"),
                                        mean_agreement=("mean_agreement", "mean"),
                                        regions=("regions", lambda s: ",".join(sorted(set(",".join(s).split(","))))))
    events = events.reset_index()
    cl.drop(columns="cells").to_parquet(FEATURES / "clusters.parquet", index=False)
    events.to_parquet(FEATURES / "events.parquet", index=False)
    return cl, events


def _gc_km(la1, lo1, la2, lo2):
    p1, p2, dl = np.deg2rad(la1), np.deg2rad(la2), np.deg2rad(lo2 - lo1)
    return float(6371 * np.arccos(np.clip(np.sin(p1) * np.sin(p2) + np.cos(p1) * np.cos(p2) * np.cos(dl), -1, 1)))


# ------------------------------------------------------------------ summaries
def monthly_summary(t: pd.DataFrame) -> pd.DataFrame:
    sel = t["selected"].iloc[0]
    _, A = load_table()
    uth = univariate_thresholds_model()
    z = np.asarray(A["z"])[t["row_idx"].values]
    t = t.copy()
    for j, v in enumerate(FEATS):
        t[f"flag_{v}"] = np.abs(z[:, j]) >= uth[v][1]
    t["flag_multivariate"] = t[f"sev_{sel}"].isin(["moderate", "strong", "extreme"])
    t["strong_plus"] = t[f"sev_{sel}"].isin(["strong", "extreme"])
    area = t["area_km2"].values
    rows = []
    for mo, g in t.groupby("month"):
        a = g["area_km2"].values
        r = {"month": mo, "split": g["split"].iloc[0], "cells": int(len(g)),
             "multivariate_flag_cells": int(g["flag_multivariate"].sum()),
             "multivariate_flag_area_fraction": float(a[g["flag_multivariate"].values].sum() / a.sum()),
             "strong_or_extreme_cells": int(g["strong_plus"].sum()),
             "most_affected_region": (g[g["flag_multivariate"]]["region"].value_counts().index[0] if g["flag_multivariate"].any() else None)}
        for v in FEATS:
            r[f"{v}_flag_area_fraction"] = float(a[g[f"flag_{v}"].values].sum() / a.sum())
        rows.append(r)
    del area
    out = pd.DataFrame(rows)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / "summaries").mkdir(exist_ok=True)
    out.to_csv(OUTPUTS / "summaries" / "monthly_summary.csv", index=False)
    return out


def seasonal_summary() -> pd.DataFrame:
    """Area-weighted seasonal-mean z (DJF/MAM/JJA/SON vs 1991-2020 seasonal climatology) per region and variable."""
    months = month_index()
    reg = regions().ravel()
    area = grid()["cell_area_km2"].ravel()
    rows = []
    for v in ALL_VARS:
        S = seasonal_z(v, "reporting").reshape(months.size, -1)
        for k in np.flatnonzero(np.isin(months.month, list(SEASONS))):
            mo = months[k]
            yr = mo.year
            for rg in ["all"] + sorted(set(reg) - {""}):
                m = np.isfinite(S[k]) & ((reg == rg) if rg != "all" else True)
                if m.sum() == 0:
                    continue
                w = area[m]
                rows.append({"season": SEASONS[mo.month], "season_year": yr, "region": rg, "variable": v,
                             "mean_z": float((S[k][m] * w).sum() / w.sum()),
                             "area_fraction_abs_z_ge_2": float(w[np.abs(S[k][m]) >= 2].sum() / w.sum())})
    out = pd.DataFrame(rows)
    (OUTPUTS / "summaries").mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUTS / "summaries" / "seasonal_summary.csv", index=False)
    return out


# ------------------------------------------------------------------ sea-ice extent anomalies + daily temperature spells
def extent_anomalies() -> pd.DataFrame:
    """Daily total/sector extent vs 1991-2020 day-of-year climatology (+-15 d): anomaly, z, percentile, record flags."""
    from .climatology import noleap_doy
    e = pd.read_csv(PROCESSED / "sea_ice_extent_daily.csv", parse_dates=["date"])
    cols = [c for c in e.columns if c not in ("date", "valid")]
    doy = noleap_doy(pd.DatetimeIndex(e["date"]))
    y0, y1 = baseline_years("reporting")
    inb = (e["date"].dt.year >= y0) & (e["date"].dt.year <= y1)
    out = e[["date"]].copy()
    for c in cols:
        x = e[c].values
        mu, sd, p, rec_lo = np.full(len(e), np.nan), np.full(len(e), np.nan), np.full(len(e), np.nan), np.zeros(len(e), bool)
        for d in range(1, 366):
            dist = np.minimum(np.abs(doy - d), 365 - np.abs(doy - d))
            base = x[(dist <= 15) & inb.values]
            base = base[np.isfinite(base)]
            k = doy == d
            mu[k], sd[k] = base.mean(), base.std(ddof=1)
            same_day = x[(doy == d) & inb.values]
            p[k] = [(np.sum(base < v) + 0.5) / (base.size + 1) if np.isfinite(v) else np.nan for v in x[k]]
            # record low for that day of year, relative to all EARLIER years only
            for i in np.flatnonzero(k):
                prior = x[(doy == d) & (e["date"].dt.year < e["date"].dt.year.values[i]).values]
                rec_lo[i] = bool(np.isfinite(x[i]) and prior[np.isfinite(prior)].size >= 10 and x[i] < np.nanmin(prior))
            del same_day
        out[f"{c}_mkm2"] = x
        out[f"{c}_anomaly_mkm2"] = x - mu
        out[f"{c}_z"] = (x - mu) / sd
        out[f"{c}_percentile"] = 100 * p
        out[f"{c}_record_low_for_date"] = rec_lo
    (OUTPUTS / "summaries").mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUTS / "summaries" / "sea_ice_extent_anomalies_daily.csv", index=False)
    return out


def daily_t2m_spells(min_days: int = 3) -> pd.DataFrame:
    """Warm / cold spells per cell: >= min_days consecutive days above the daily P90 (below P10) of 1991-2020 (+-15 d window).
    Same idea as the ETCCDI WSDI/CSDI indices, with a shorter minimum duration (3 instead of 6 days)."""
    from .climatology import load_daily_clim, noleap_doy
    from .paths import INTERIM
    from .preprocessing import calendar
    cal = calendar()
    d = np.load(INTERIM / "daily_t2m.npy", mmap_mode="r")
    c = load_daily_clim("reporting", "t2m")
    doy = noleap_doy(cal) - 1
    T = np.asarray(d).reshape(cal.size, -1)
    p90, p10 = c["p90"].reshape(365, -1)[doy], c["p10"].reshape(365, -1)[doy]
    mu, sd = c["mean"].reshape(365, -1)[doy], c["std"].reshape(365, -1)[doy]
    g = grid()
    reg = regions().ravel()
    rows = []
    for kind, ex in (("warm_spell", T > p90), ("cold_spell", T < p10)):
        for cell in range(T.shape[1]):
            e = ex[:, cell]
            if not e.any():
                continue
            de = np.diff(np.r_[0, e.astype(np.int8), 0])
            st, en = np.flatnonzero(de == 1), np.flatnonzero(de == -1)
            for a, b in zip(st, en):
                if b - a >= min_days:
                    z = (T[a:b, cell] - mu[a:b, cell]) / np.maximum(sd[a:b, cell], 0.3)
                    rows.append({"type": kind, "cell": cell, "lat": float(g["lat"][cell // 144]), "lon": float(g["lon"][cell % 144]),
                                 "region": reg[cell], "start": cal[a].date().isoformat(), "end": cal[b - 1].date().isoformat(),
                                 "days": int(b - a), "peak_abs_z": float(np.nanmax(np.abs(z))),
                                 "peak_anomaly_degC": float(np.nanmax(np.abs(T[a:b, cell] - mu[a:b, cell])) * (1 if kind == "warm_spell" else -1))})
    out = pd.DataFrame(rows)
    (OUTPUTS / "summaries").mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUTS / "summaries" / "daily_t2m_spells_1991-2020.csv", index=False)
    return out


# ------------------------------------------------------------------ independent checks
def station_agreement() -> dict:
    """GHCN-Daily station TAVG monthly anomalies (own 1981-2010 baseline) vs the NCEP cell z(t2m) (model baseline)."""
    st = pd.read_csv(ROOT / "data" / "raw" / "station_observations" / "ghcnd" / "antarctic_stations_selected.csv")
    df, A = load_table()
    z = np.asarray(A["z"])[:, FEATS.index("t2m")]
    key = pd.Series(np.arange(len(df)), index=pd.MultiIndex.from_arrays([df["month"].values, df["cell"].values]))
    g = grid()
    res, pairs = [], []
    for _, s in st.iterrows():
        f = ROOT / "data" / "raw" / "station_observations" / "ghcnd" / f"{s['id']}.csv"
        if not f.exists() or s["lat"] > -48.75:
            continue
        d = pd.read_csv(f, usecols=["DATE", "TAVG"], low_memory=False).dropna()
        if d.empty:
            continue
        d["DATE"] = pd.to_datetime(d["DATE"])
        d["TAVG"] = pd.to_numeric(d["TAVG"], errors="coerce") / 10.0
        d["m"] = d["DATE"].dt.to_period("M")
        mm = d.groupby("m")["TAVG"].agg(["mean", "count"])
        mm = mm[mm["count"] >= 20]["mean"]
        if mm.empty:
            continue
        mon = mm.index.month
        yr = mm.index.year
        base = (yr >= 1981) & (yr <= 2010)
        clim = pd.DataFrame({"v": mm.values, "mo": mon, "b": base}).query("b").groupby("mo")["v"].agg(["mean", "std", "count"])
        clim = clim[clim["count"] >= 20]
        if len(clim) < 12:
            continue
        sz = (mm.values - clim.loc[mon, "mean"].values) / clim.loc[mon, "std"].values
        row = int(np.clip(np.round((g["lat"][0] - s["lat"]) / 2.5), 0, g["lat"].size - 1))
        col = int(np.mod(np.round(np.mod(s["lon"], 360) / 2.5), 144))
        cell = row * 144 + col
        for p_, v in zip(mm.index, sz):
            k = key.get((p_.strftime("%Y-%m"), cell))
            if k is not None and np.isfinite(z[k]):
                pairs.append({"station": s["id"], "name": s["name"], "month": p_.strftime("%Y-%m"), "split": df["split"].values[k],
                              "station_z": float(v), "ncep_z": float(z[k])})
    P = pd.DataFrame(pairs)
    out = {}
    for sp, g2 in P.groupby("split"):
        a, b = g2["station_z"].values, g2["ncep_z"].values
        fa, fb = np.abs(a) >= 1.96, np.abs(b) >= 1.96
        po = np.mean(fa == fb)
        pe = fa.mean() * fb.mean() + (1 - fa.mean()) * (1 - fb.mean())
        out[sp] = {"pairs": int(len(g2)), "stations": int(g2["station"].nunique()), "pearson_r": float(np.corrcoef(a, b)[0, 1]),
                   "flag_agreement": float(po), "cohen_kappa": float((po - pe) / (1 - pe)) if pe < 1 else None,
                   "station_flag_rate": float(fa.mean()), "ncep_flag_rate": float(fb.mean())}
    P.to_csv(METRICS / "station_pairs.csv", index=False)
    out["note"] = ("GHCN-D monthly TAVG (>= 20 valid days) vs NCEP R1 sigma-0.995 temperature of the containing 2.5 deg cell; "
                   "flags at |z| >= 1.96. NCEP R1 assimilates surface pressure, not screen temperature, at these stations, "
                   "but the comparison is still not fully independent; the point-vs-cell scale mismatch lowers agreement.")
    (METRICS / "station_agreement.json").write_text(json.dumps(out, indent=1))
    return out


def literature_events(t: pd.DataFrame) -> list[dict]:
    """Qualitative recall of literature-documented events (configs/ml04/reference_events.yaml). Not labels; not used for selection."""
    import yaml
    ev = yaml.safe_load((ROOT / "configs" / "ml04" / "reference_events.yaml").read_text())["events"]
    sel = t["selected"].iloc[0]
    uth = univariate_thresholds_model()
    _, A = load_table()
    out = []
    for e in ev:
        lon = np.where(t["lon"] > 180, t["lon"] - 360, t["lon"])
        a, b = e["lon"]
        inbox = (t["lat"] >= e["lat"][0]) & (t["lat"] <= e["lat"][1]) & (((lon >= a) & (lon <= b)) if a <= b else ((lon >= a) | (lon <= b)))
        m = inbox & t["month"].isin(e["months"])
        if e["variable"] == "sic":
            m = m & t["sic_available"]
        g = t[m]
        r = {k: e[k] for k in ("name", "months", "variable", "direction", "split", "reference")}
        if g.empty:
            r["status"] = "no scored cell-months in box/period (e.g. after the NCEP R1 record ends)"
            out.append(r)
            continue
        z = np.asarray(A["z"])[g["row_idx"].values, FEATS.index(e["variable"])]
        sgn = 1 if e["direction"] == "+" else -1
        r |= {"cells": int(len(g)), "mean_z": float(np.nanmean(z)), "max_signed_z": float(np.nanmax(sgn * z) * sgn),
              "univariate_flag_fraction": float(np.mean(sgn * z >= uth[e["variable"]][1])),
              "multivariate_flag_fraction": float(g[f"sev_{sel}"].isin(["moderate", "strong", "extreme"]).mean()),
              "detected_univariate": bool(np.mean(sgn * z >= uth[e["variable"]][1]) >= 0.2),
              "detected_multivariate": bool(g[f"sev_{sel}"].isin(["moderate", "strong", "extreme"]).mean() >= 0.2)}
        out.append(r)
    (METRICS / "reference_events.json").write_text(json.dumps(out, indent=1, default=str))
    return out
