"""ML-04 Phase 12: spatial outputs (GeoTIFF / JSON) for one month, in the layer-manifest format of the AETHENTRA viewer.

outputs/ml04/anomaly_maps/anom_YYYY-MM/
  anom_YYYY-MM.json            machine-readable summary (provenance, baseline, model version, regional statistics)
  layers/manifest.json         every layer with data_type, units, period, baseline, method
  layers/<id>_4326.tif         native 2.5 deg NCEP grid (EPSG:4326, cell centres -50 ... -87.5, 0 ... 357.5 E)
  layers/<id>_3412.tif         display copy on the 25 km EPSG:3412 grid (nearest 2.5 deg cell; display only)
  sic_anomaly_native_3412.tif  SIC anomaly on the native 25 km CDR grid (no resampling)
"""
from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import Affine

from ..config import ROOT
from .climatology import load_clim
from .paths import MODELS, OUTPUTS, PROCESSED
from .preprocessing import grid, month_index

MAP_DIR = OUTPUTS / "anomaly_maps"
T3412 = Affine(25000, 0, -3950000, 0, -25000, 4350000)
VARS_Z = ["t2m", "slp", "wspd", "rhum", "prate", "tcdc", "z500", "sic"]
TITLES = {"t2m": "Near-surface air temperature", "slp": "Sea-level pressure", "wspd": "Wind speed", "rhum": "Relative humidity",
          "prate": "Precipitation", "tcdc": "Total cloud cover", "z500": "500 hPa geopotential height", "sic": "Sea-ice concentration"}


def _sic_grid():
    z = np.load(ROOT / "data" / "interim" / "aethentra" / "grid.npz")
    return z["lat"], np.mod(z["lon"], 360), z["ocean_mask"].astype(bool)


def to_3412(a: np.ndarray) -> np.ndarray:
    """Nearest-cell display resampling of a (16, 144) 2.5 deg field onto the 332 x 316 EPSG:3412 grid."""
    lat, lon, _ = _sic_grid()
    g = grid()
    i = np.round((g["lat"][0] - lat) / 2.5).astype(int)
    j = np.mod(np.round(lon / 2.5).astype(int), g["lon"].size)
    out = np.full(lat.shape, np.nan, np.float32)
    ok = (i >= 0) & (i < g["lat"].size)
    i = np.clip(i, 0, g["lat"].size - 1)
    out[ok] = a[i[ok], j[ok]]
    return out


def _write(path, arr, crs, transform, nodata=-9999.0):
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype="float32", crs=crs,
                       transform=transform, nodata=nodata, compress="deflate") as d:
        d.write(np.where(np.isfinite(arr), arr, nodata).astype(np.float32), 1)


def _pair(layer_dir, lid, a):
    t4326 = Affine(2.5, 0, -1.25, 0, -2.5, -48.75)            # cell edges: lon -1.25 .. 358.75, lat -48.75 .. -88.75
    _write(layer_dir / f"{lid}_4326.tif", a, "EPSG:4326", t4326)
    _write(layer_dir / f"{lid}_3412.tif", to_3412(a), "EPSG:3412", T3412)
    return [f"{lid}_3412.tif", f"{lid}_4326.tif"]


def export_month(month: str) -> dict:
    import xarray as xr
    from .products import CLASS_NAMES, regions
    months = month_index()
    k = int(np.flatnonzero(months.strftime("%Y-%m") == month)[0])
    d = json.loads((MODELS / "decision.json").read_text())
    sel = d["selected_multivariate"]
    version = model_version()
    ds = xr.open_dataset(OUTPUTS / "anomalies_monthly_1991-2020.nc")
    pid = f"anom_{month}"
    out = MAP_DIR / pid
    ld = out / "layers"
    ld.mkdir(parents=True, exist_ok=True)
    period = [str(months[k].date()), str((months[k] + pd.offsets.MonthEnd(0)).date())]
    layers, stats = [], {}
    atm = bool(np.isfinite(ds["t2m_z"].isel(time=k).values).any())
    sc = pd.read_parquet(ROOT / "data" / "processed" / "ml04" / "features" / "scores.parquet")
    tab = pd.read_parquet(ROOT / "data" / "processed" / "ml04" / "features" / "table.parquet", columns=["month", "cell"])
    sc = sc.assign(month=tab["month"].values[sc["idx"].values], cell=tab["cell"].values[sc["idx"].values])
    g = sc[sc["month"] == month]
    shape = (grid()["lat"].size, grid()["lon"].size)
    if atm and len(g):
        sev = np.full(shape[0] * shape[1], np.nan, np.float32)
        sev[g["cell"].values] = pd.Categorical(g[f"sev_{sel}"], categories=CLASS_NAMES).codes
        flags = sum(g[f"sev_{n}"].isin(["moderate", "strong", "extreme"]).astype(int).values for n in ("zscore", "percentile", "mad", sel))
        agr = np.full(shape[0] * shape[1], np.nan, np.float32)
        agr[g["cell"].values] = flags
        layers.append({"id": "multivariate_severity", "title": f"Multivariate anomaly severity ({sel.replace('_', ' ')})",
                       "data_type": "anomaly_detection", "units": "class 0 normal ... 4 extreme", "period": period,
                       "files": _pair(ld, "multivariate_severity", sev.reshape(shape)), "color_range": [0, 4],
                       "method": sel, "baseline": "1981-2010 (model)"})
        layers.append({"id": "method_agreement", "title": "Detector agreement (z, percentile, MAD, multivariate)",
                       "data_type": "anomaly_detection", "units": "methods flagging (0-4)", "period": period,
                       "files": _pair(ld, "method_agreement", agr.reshape(shape)), "color_range": [0, 4]})
        stats["multivariate_flag_cells"] = int(g[f"sev_{sel}"].isin(["moderate", "strong", "extreme"]).sum())
        stats["strong_or_extreme_cells"] = int(g[f"sev_{sel}"].isin(["strong", "extreme"]).sum())
    for v in VARS_Z:
        a = ds[f"{v}_z"].isel(time=k).values
        if not np.isfinite(a).any():
            continue
        layers.append({"id": f"{v}_z", "title": f"{TITLES[v]}: standardised anomaly", "data_type": "statistical_anomaly",
                       "units": "z (sigma)", "period": period, "files": _pair(ld, f"{v}_z", a), "color_range": [-3, 3],
                       "baseline": "1991-2020", "method": "z-score"})
        stats[f"{v}_area_weighted_mean_z"] = float(np.nansum(a * grid()["cell_area_km2"]) / np.nansum(np.isfinite(a) * grid()["cell_area_km2"]))
    if atm:
        c = load_clim("reporting", "t2m")["mean"][months[k].month - 1]
        layers.append({"id": "t2m_normal", "title": "Normal-condition reference: 1991-2020 mean temperature", "data_type": "climatology",
                       "units": "degC", "period": period, "files": _pair(ld, "t2m_normal", c), "color_range": [-60, 0]})
    native = np.load(PROCESSED / "monthly_sic_native25km.npy", mmap_mode="r")[k]
    base_years = (months.year >= 1991) & (months.year <= 2020) & (months.month == months[k].month)
    if np.isfinite(native).any():
        nb = np.load(PROCESSED / "monthly_sic_native25km.npy", mmap_mode="r")[np.flatnonzero(base_years)]
        an = np.asarray(native) - np.nanmean(nb, 0)
        _write(ld / "sic_anomaly_native_3412.tif", an, "EPSG:3412", T3412)
        layers.append({"id": "sic_anomaly_native", "title": "Sea-ice concentration anomaly (native 25 km)", "data_type": "statistical_anomaly",
                       "units": "percentage points", "period": period, "files": ["sic_anomaly_native_3412.tif"], "color_range": [-40, 40],
                       "baseline": "1991-2020"})
    manifest = {"forecast_id": pid, "issue_date": period[1], "model_version": version, "baseline_reporting": "1991-2020",
                "baseline_model": "1981-2010", "source": "NCEP/NCAR Reanalysis 1 (NOAA PSL) daily means; NOAA/NSIDC SIC CDR v6",
                "native_crs": "EPSG:4326 2.5 deg (NCEP R1); SIC native EPSG:3412 25 km", "display_crs": "EPSG:3412 (nearest-cell display copy)",
                "limitations": limitations(atm), "display_rules": ["Statistical anomalies are not confirmed extreme events and imply no cause.",
                                                                     "Show baseline period and detection method with every layer."],
                "layers": layers}
    (ld / "manifest.json").write_text(json.dumps(manifest, indent=1))
    reg = regions().ravel()
    regional = []
    if atm and len(g):
        gg = g.assign(region=reg[g["cell"].values])
        for r, h in gg.groupby("region"):
            regional.append({"region": r, "cells": int(len(h)), "flagged": int(h[f"sev_{sel}"].isin(["moderate", "strong", "extreme"]).sum())})
    summary = {"product": "ml04_monthly_anomaly", "month": month, "period": period, "model_version": version, "selected_method": sel,
               "baselines": {"reporting": "1991-2020", "model": "1981-2010"}, "atmosphere_available": atm,
               "statistics": stats, "regions": regional, "limitations": limitations(atm),
               "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "methodology": "Univariate z vs 1991-2020 calendar-month climatology; multivariate detector on 9 standardised "
                              "features vs 1981-2010; severity = base-rate classes from the 1979-2010 score distribution."}
    (out / f"{pid}.json").write_text(json.dumps(summary, indent=1))
    return summary


def model_version() -> str:
    d = json.loads((MODELS / "decision.json").read_text())
    return f"aethentra-ml04-{d['selected_multivariate'].replace('_', '-')}-{d['frozen_utc'][:10].replace('-', '')}-v{d.get('version', 1)}"


def limitations(atm: bool = True) -> list[str]:
    L = ["Statistical unusualness relative to a fixed baseline; not a confirmed extreme event and not evidence of a cause or of climate change.",
         "Atmospheric fields are NCEP/NCAR Reanalysis 1 (2.5 deg); precipitation and cloud are model forecast fields with large known errors over Antarctica.",
         "NCEP R1 at NOAA PSL ends 2026-03-17: no atmospheric or multivariate anomalies after February 2026.",
         "Severity classes are base-rate classes (P90/P95/P98/P99.5 of the 1979-2010 score distribution), not impact categories.",
         "Detectors were evaluated with SYNTHETIC injected anomalies; no labelled set of real Antarctic anomalies exists."]
    if not atm:
        L.insert(0, "This month has sea-ice data only (atmospheric record ended); multivariate detection is unavailable.")
    return L
