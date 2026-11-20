"""Build lightweight, presentation-ready climate products for the AETHENTRA web frontend.

Everything is computed from data already on disk (no downloads, nothing synthetic):
  ERA5 monthly means (Copernicus CDS, 0.25 deg, 50-90S)       -> Antarctic/sector monthly series + anomaly maps
  MERRA-2 M2TMNXSLV monthly means (NASA GES DISC, 50-90S)     -> independent cross-check series
  CMEMS C1 OSI-SAF SIC CDR/ICDR daily (EUMETSAT OSI SAF)       -> independent monthly sea-ice extent
  CMEMS C2 GLORYS12 monthly                                   -> mean sea-ice thickness (model reanalysis)

Outputs (web/public/data/):
  climate_series.json   monthly series + 1991-2020 climatology anomalies, with units, sources and definitions
  globe/*.png + globe/index.json   EPSG:4326 anomaly images (lon -180..180, lat -90..-50) for the latest month

Area weighting: cos(latitude). Domain "antarctic" = 60-90S (all longitudes) unless stated otherwise.
Sea-ice extent = total area of cells with concentration >= 15 %, south of 50S.
"""
from __future__ import annotations

import glob
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
E5 = ROOT / "data" / "raw" / "era5" / "monthly"
M2 = ROOT / "data" / "raw" / "merra2" / "M2TMNXSLV"
CM = ROOT / "data" / "raw" / "cmems"
OUT = ROOT / "web" / "public" / "data"
CLIM = (1991, 2020)
R_EARTH_KM = 6371.0
SECTORS = {  # NSIDC regional convention (longitude ranges, degrees east)
    "weddell": (-60, 20), "indian": (20, 90), "pacific": (90, 160), "ross": (160, -130), "bellingshausen_amundsen": (-130, -60)}


def _std(ds: xr.Dataset) -> xr.Dataset:
    ren = {k: v for k, v in {"valid_time": "time", "latitude": "lat", "longitude": "lon"}.items() if k in ds.dims or k in ds.coords}
    ds = ds.rename(ren)
    drop = [c for c in ("expver", "number", "step", "surface") if c in ds.coords]
    return ds.drop_vars(drop, errors="ignore")


def _sector_mask(lon: xr.DataArray, a: float, b: float) -> xr.DataArray:
    return ((lon >= a) & (lon < b)) if a < b else ((lon >= a) | (lon < b))


def _wmean(da: xr.DataArray, latmax: float = -60.0, sector: tuple | None = None) -> pd.Series:
    sel = da.where(da.lat <= latmax, drop=True)
    if sector:
        sel = sel.where(_sector_mask(sel.lon, *sector), drop=True)
    w = np.cos(np.deg2rad(sel.lat))
    s = sel.weighted(w).mean(("lat", "lon"))
    return s.to_series()


def _cell_area_km2(lat: np.ndarray, dlat: float, dlon: float) -> np.ndarray:
    return (R_EARTH_KM ** 2) * np.deg2rad(dlon) * np.abs(
        np.sin(np.deg2rad(lat + dlat / 2)) - np.sin(np.deg2rad(lat - dlat / 2)))


def _extent(conc: xr.DataArray, thr: float, sector: tuple | None = None) -> pd.Series:
    lat = conc.lat.values
    dlat = float(np.abs(np.diff(lat)).mean()); dlon = float(np.abs(np.diff(conc.lon.values)).mean())
    area = xr.DataArray(_cell_area_km2(lat, dlat, dlon), dims="lat", coords={"lat": conc.lat})
    m = (conc >= thr)
    if sector:
        m = m & _sector_mask(conc.lon, *sector)
    return (m * area).sum(("lat", "lon")).to_series()


def _anom(s: pd.Series) -> pd.Series:
    s = s.copy(); s.index = pd.to_datetime(s.index)
    base = s[(s.index.year >= CLIM[0]) & (s.index.year <= CLIM[1])]
    clim = base.groupby(base.index.month).mean()
    return s - clim.reindex(s.index.month).values


def _pack(s: pd.Series, nd: int = 3) -> dict:
    s = s.dropna(); s.index = pd.to_datetime(s.index)
    a = _anom(s)
    return {"t": [d.strftime("%Y-%m") for d in s.index], "v": [round(float(x), nd) for x in s.values],
            "anom": [round(float(x), nd) for x in a.values]}


def era5_var(name: str) -> xr.DataArray:
    f = E5 / f"era5_monthly_{name}_1979_2026.nc"
    ds = _std(xr.open_dataset(f))
    da = ds[list(ds.data_vars)[0]]
    if "expver" in da.dims:
        da = da.max("expver")
    if float(da.lon.max()) > 180:
        da = da.assign_coords(lon=((da.lon + 180) % 360) - 180).sortby("lon")
    return da


def osisaf_daily_extent(files: list[str]) -> pd.Series:
    """Daily extent from OSI SAF files. Days with missing data beyond the fixed land/pole mask (e.g. fully missing
    ICDR days) are DROPPED rather than counted as zero ice; the mask size is the per-file minimum NaN count."""
    daily = []
    for f in files:
        with xr.open_dataset(f) as d:
            d = d.rename({k: v for k, v in {"latitude": "lat", "longitude": "lon"}.items() if k in d.dims})
            ic = d["ice_conc"].load()
            nan = ic.isnull().sum(("lat", "lon"))
            ok = nan <= int(nan.min()) * 1.01 + 10
            daily.append(_extent(ic.isel(time=np.where(ok.values)[0]), 15.0) / 1e6)
    s = pd.concat(daily).sort_index()
    return s[~s.index.duplicated()]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    series: dict = {}
    defs = {
        "t2m": ("2 m air temperature", "degC", lambda d: d - 273.15, 2),
        "msl": ("Mean sea-level pressure", "hPa", lambda d: d / 100.0, 2),
        "tp": ("Total precipitation", "mm/day", lambda d: d * 1000.0, 3),
        "sf": ("Snowfall", "mm water equivalent/day", lambda d: d * 1000.0, 3),
        "sst": ("Sea-surface temperature (open ocean, 50-60S band excluded from Antarctic mean)", "degC", lambda d: d - 273.15, 2),
    }
    era: dict[str, xr.DataArray] = {}
    for k, (title, units, conv, nd) in defs.items():
        da = conv(era5_var(k)).load()
        era[k] = da
        latmax = -50.0 if k == "sst" else -60.0
        entry = {"title": title, "units": units, "source": "ERA5 monthly averaged reanalysis (Copernicus CDS)",
                 "domain": "50-90S" if k == "sst" else "60-90S", "antarctic": _pack(_wmean(da, latmax), nd)}
        if k != "sst":
            entry["sectors"] = {n: _pack(_wmean(da, latmax, b), nd) for n, b in SECTORS.items()}
        series[f"era5_{k}"] = entry
        print("ERA5", k, entry["antarctic"]["t"][0], "->", entry["antarctic"]["t"][-1])

    u, v = era5_var("u10").load(), era5_var("v10").load()
    ws = np.hypot(u, v)
    series["era5_wind10"] = {"title": "10 m wind: magnitude of the monthly-mean wind vector", "units": "m/s",
                             "note": "Speed of the monthly-mean vector, not the monthly mean of instantaneous speed (lower in variable winds).",
                             "source": "ERA5 monthly averaged reanalysis (Copernicus CDS)", "domain": "60-90S",
                             "antarctic": _pack(_wmean(ws, -60.0), 2),
                             "sectors": {n: _pack(_wmean(ws, -60.0, b), 2) for n, b in SECTORS.items()}}

    sic = era5_var("siconc").load()
    series["era5_sea_ice_extent"] = {"title": "Sea-ice extent (concentration >= 15 %)", "units": "million km2",
                                     "source": "ERA5 monthly sea-ice cover (OSI SAF-based boundary condition)", "domain": "50-90S",
                                     "antarctic": _pack(_extent(sic, 0.15) / 1e6, 3),
                                     "sectors": {n: _pack(_extent(sic, 0.15, b) / 1e6, 3) for n, b in SECTORS.items()}}
    print("ERA5 extent done")

    # MERRA-2 independent cross-check
    fs = sorted(M2.glob("*.nc"))
    if fs:
        m = xr.open_mfdataset([str(f) for f in fs], combine="by_coords")
        m = m.rename({k: v for k, v in {"latitude": "lat", "longitude": "lon"}.items() if k in m.dims})
        t = (m["T2M"] - 273.15).load(); p = (m["SLP"] / 100.0).load()
        t["time"] = pd.to_datetime(t.time.values).to_period("M").to_timestamp(); p["time"] = t["time"]
        series["merra2_t2m"] = {"title": "2 m air temperature", "units": "degC", "domain": "60-90S",
                                "source": "NASA MERRA-2 M2TMNXSLV monthly means (GES DISC)", "antarctic": _pack(_wmean(t, -60.0), 2)}
        series["merra2_slp"] = {"title": "Sea-level pressure", "units": "hPa", "domain": "60-90S",
                                "source": "NASA MERRA-2 M2TMNXSLV monthly means (GES DISC)", "antarctic": _pack(_wmean(p, -60.0), 2)}
        print("MERRA-2 done")

    # CMEMS C1 OSI-SAF SIC: daily extent -> monthly mean
    c1 = sorted(glob.glob(str(CM / "C1" / "*.nc")))
    if c1:
        s = osisaf_daily_extent(c1)
        s = s[~s.index.duplicated()]
        mon = s.groupby(pd.to_datetime(s.index).to_period("M")).agg(["mean", "count"])
        mon = mon[mon["count"] >= 15]["mean"]; mon.index = mon.index.to_timestamp()
        series["osisaf_sea_ice_extent"] = {"title": "Sea-ice extent (concentration >= 15 %), monthly mean of daily values",
                                           "units": "million km2", "domain": "50-90S",
                                           "note": "Months with fewer than 15 valid days are omitted (early SMMR record is every other day).",
                                           "source": "EUMETSAT OSI SAF OSI-450 CDR + OSI-430 ICDR via Copernicus Marine (C1)",
                                           "antarctic": _pack(mon, 3)}
        print("OSI-SAF done", len(mon))

    # CMEMS C2 GLORYS12: mean ice thickness where siconc >= 15 %
    c2 = sorted(glob.glob(str(CM / "C2" / "*.nc")))
    if c2:
        g = xr.open_mfdataset(c2, combine="by_coords")
        g = g.rename({k: v for k, v in {"latitude": "lat", "longitude": "lon"}.items() if k in g.dims})
        hi = g["sithick"].where(g["siconc"] >= 0.15)
        w = np.cos(np.deg2rad(g.lat))
        s = hi.weighted(w).mean(("lat", "lon")).load().to_series()
        series["glorys_sea_ice_thickness"] = {"title": "Mean sea-ice thickness over ice-covered cells (concentration >= 15 %)",
                                              "units": "m", "domain": "50-80S (GLORYS12 southern limit is 80S)",
                                              "source": "Mercator GLORYS12 reanalysis (model) via Copernicus Marine (C2)",
                                              "antarctic": _pack(s, 3)}
        print("GLORYS done")

    meta = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "climatology": f"{CLIM[0]}-{CLIM[1]} monthly mean (anom = value - climatology for that calendar month)",
            "area_weighting": "cos(latitude)", "sectors_lon_deg_east": SECTORS,
            "data_type": "reanalysis / observation (no model predictions in this file)"}
    (OUT / "climate_series.json").write_text(json.dumps({"meta": meta, "series": series}, separators=(",", ":")))
    print("wrote climate_series.json", (OUT / "climate_series.json").stat().st_size // 1024, "KB")

    # Globe anomaly images for the latest ERA5 month
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    gdir = OUT / "globe"; gdir.mkdir(exist_ok=True)
    idx = []
    specs = [("t2m", "2 m temperature anomaly", "degC", "RdBu_r", 6), ("msl", "Sea-level pressure anomaly", "hPa", "PuOr_r", 12),
             ("sst", "Sea-surface temperature anomaly", "degC", "RdBu_r", 2)]
    for k, title, units, cmap, lim in specs:
        da = era[k]
        last = da.time.values[-1]
        base = da.sel(time=(da.time.dt.year >= CLIM[0]) & (da.time.dt.year <= CLIM[1]))
        clim = base.groupby("time.month").mean()
        an = (da.sel(time=last) - clim.sel(month=pd.Timestamp(last).month)).sortby("lat", ascending=False)
        a = an.values.astype("float32")
        rgba = matplotlib.colormaps[cmap]((np.clip(a, -lim, lim) + lim) / (2 * lim))
        rgba[..., 3] = np.where(np.isfinite(a), 0.85, 0.0)
        name = f"era5_{k}_anom_{pd.Timestamp(last):%Y%m}.png"
        plt.imsave(gdir / name, rgba)
        cols = [matplotlib.colors.to_hex(matplotlib.colormaps[cmap](x)) for x in np.linspace(0, 1, 11)]
        idx.append({"id": f"era5_{k}_anom", "title": f"{title} ({pd.Timestamp(last):%B %Y} vs {CLIM[0]}-{CLIM[1]})",
                    "units": units, "vmin": -lim, "vmax": lim, "colors": cols, "month": f"{pd.Timestamp(last):%Y-%m}",
                    "data_type": "reanalysis_anomaly", "source": "ERA5 monthly averaged reanalysis (Copernicus CDS)",
                    "url": f"/data/globe/{name}",
                    "bounds": {"west": float(an.lon.min()) - 0.125, "east": float(an.lon.max()) + 0.125,
                               "south": -90.0, "north": float(an.lat.max()) + 0.125}})
    (gdir / "index.json").write_text(json.dumps(idx, indent=1))
    print("globe images", [i["id"] for i in idx])


if __name__ == "__main__":
    main()
