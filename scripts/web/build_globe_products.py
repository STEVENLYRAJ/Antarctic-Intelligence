"""Build time-enabled globe layers and extra series for the AETHENTRA web frontend.

Everything is computed from files already on disk. Nothing is downloaded, nothing is synthetic.
Inputs (all regular lat/lon grids, so images are equirectangular EPSG:4326 and drape directly on the globe):
  C1  EUMETSAT OSI SAF SIC CDR/ICDR daily (Copernicus Marine)     -> monthly SIC frames 1979-2025, daily extent record
  C2  Mercator GLORYS12 monthly reanalysis                          -> monthly sea-ice thickness frames
  C3  Copernicus Marine multi-reanalysis ensemble (mean/std)        -> SIC ensemble spread (uncertainty) frames
  C4  DMI ASIP SAR+AMSR2 1 km SIC (97 ML-03 test dates)            -> high-resolution SIC frames (0.1 deg)
  C5  IFREMER AMSR2/AMSR-E 3-day sea-ice drift                     -> monthly drift speed frames + drift vectors
  C6  AWI merged CryoSat-2 + Sentinel-3 + SMOS sea-ice thickness  -> weekly thickness frames
  C7  MULTIOBS ARMOR3D-type observation-based ocean T/S            -> monthly upper-ocean temperature anomaly frames
  ERA5 monthly (Copernicus CDS)                                     -> 36-month t2m / MSLP / SST anomaly frames
  ERA5 daily mean t2m 2014-2026                                     -> last 92 daily frames, daily Antarctic-mean record
  ERA5 monthly t850/z500/tp/tcc/siconc/wind10 (era5m2)              -> 36-month anomaly frames, 3 new monthly series
  ERA5 daily t850/z500/msl/tcc/tp/siconc/wind10 (era5d2)            -> last 92 daily frames (+ wind arrows), 4 daily records

Outputs (web/public/data/):
  globe/layers/<id>/<frame>.png     images, lon -180..180
  globe/catalog.json                layer catalogue with frames, units, colour scale, source, method, coverage
  globe/vectors/<id>/<frame>.json   drift arrows as line segments [lon0, lat0, lon1, lat1]
  daily_series.json                 daily sea-ice extent per year (OSI SAF) and daily Antarctic-mean t2m (ERA5)
  climate_series.json               (extended in place) monthly drift speed, ocean temperature, mixed-layer depth
"""
from __future__ import annotations

import glob
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.colors import LinearSegmentedColormap, to_hex
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_climate_series import CLIM, _extent, _std, era5_var  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CM = ROOT / "data" / "raw" / "cmems"
E5D = ROOT / "data" / "raw" / "era5"
OUT = ROOT / "web" / "public" / "data"
G = OUT / "globe"
LAYERS = G / "layers"
VEC = G / "vectors"
T0 = time.time()

PRECIP_CMAP = LinearSegmentedColormap.from_list("precip", ["#173a5e", "#2f7fb8", "#48c8e8", "#b9ecf7", "#ffffff"])
SIC_CMAP = LinearSegmentedColormap.from_list("sic", ["#0d2b4f", "#1f5d93", "#4f9fd0", "#8ddcf4", "#eaf5fc"])
catalog: list[dict] = []


def log(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def ll(ds):
    return ds.rename({k: v for k, v in {"latitude": "lat", "longitude": "lon", "valid_time": "time"}.items() if k in ds.dims or k in ds.coords})


def bounds_of(lat: np.ndarray, lon: np.ndarray) -> dict:
    dl = float(np.abs(np.diff(lat)).mean()); dn = float(np.abs(np.diff(lon)).mean())
    return {"west": max(-180.0, float(lon.min()) - dn / 2), "east": min(180.0, float(lon.max()) + dn / 2),
            "south": max(-90.0, float(lat.min()) - dl / 2), "north": float(lat.max()) + dl / 2}


def save_png(a: np.ndarray, lat: np.ndarray, cmap, vmin: float, vmax: float, path: Path, mask=None, alpha=0.88) -> None:
    """a[lat, lon] -> RGBA PNG with north at the top. Transparent where NaN or mask is False."""
    if lat[0] < lat[-1]:
        a = a[::-1]
        mask = None if mask is None else mask[::-1]
    cm = matplotlib.colormaps[cmap] if isinstance(cmap, str) else cmap
    rgba = cm(np.clip((a - vmin) / (vmax - vmin), 0, 1))
    ok = np.isfinite(a) if mask is None else (np.isfinite(a) & mask)
    rgba[..., 3] = np.where(ok, alpha, 0.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((rgba * 255).astype("uint8"), "RGBA").save(path, optimize=True)


def colors_of(cmap, n=9) -> list[str]:
    cm = matplotlib.colormaps[cmap] if isinstance(cmap, str) else cmap
    return [to_hex(cm(x)) for x in np.linspace(0, 1, n)]


def add_layer(id, group, title, units, data_type, source, method, cmap, vmin, vmax, frames, bounds, **extra):
    catalog.append({"id": id, "group": group, "title": title, "units": units, "data_type": data_type, "source": source,
                    "method": method, "colors": colors_of(cmap), "vmin": vmin, "vmax": vmax, "bounds": bounds,
                    "coverage": f"{frames[0]['t']} → {frames[-1]['t']}" if frames else "", "frames": frames, **extra})
    log("layer", id, len(frames), "frames")


def coarsen(a: np.ndarray, f: int) -> np.ndarray:
    h, w = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    b = a[:h, :w].reshape(h // f, f, w // f, f)
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        return np.nanmean(b, axis=(1, 3))


# ---------------------------------------------------------------- C1 OSI SAF: monthly SIC frames + daily extent
def c1():
    files = sorted(glob.glob(str(CM / "C1" / "*.nc")))
    frames, daily = [], []
    lat = lon = None
    for f in files:
        with xr.open_dataset(f) as d:
            d = ll(d)
            ic = d["ice_conc"].load()
            nan = ic.isnull().sum(("lat", "lon"))
            ok = nan <= int(nan.min()) * 1.01 + 10
            ic = ic.isel(time=np.where(ok.values)[0])
            daily.append(_extent(ic, 15.0) / 1e6)
            lat, lon = ic.lat.values, ic.lon.values
            cnt = ic.time.to_series().resample("MS").count()
            mm = ic.resample(time="MS").mean("time")
            for t in mm.time.values:
                ts = pd.Timestamp(t)
                if cnt.get(ts, 0) < 10:
                    continue
                key = ts.strftime("%Y-%m")
                a = mm.sel(time=t).values
                save_png(a, lat, SIC_CMAP, 15, 100, LAYERS / "osisaf_sic" / f"{key}.png", mask=a >= 15)
                frames.append({"t": key, "url": f"/data/globe/layers/osisaf_sic/{key}.png"})
        log("C1", Path(f).name)
    add_layer("osisaf_sic", "Sea ice · observations", "Sea-ice concentration, monthly mean (OSI SAF climate record)", "%",
              "observation", "EUMETSAT OSI SAF OSI-450-a CDR + OSI-430-a ICDR, via Copernicus Marine (C1)",
              "Monthly mean of daily passive-microwave concentration; cells below 15 % are transparent. Days with missing swaths are excluded.",
              SIC_CMAP, 15, 100, frames, bounds_of(lat, lon), default="2025-09")
    s = pd.concat(daily).sort_index()
    return s[~s.index.duplicated()]


# ---------------------------------------------------------------- C2 GLORYS12: monthly ice thickness frames
def c2():
    files = sorted(glob.glob(str(CM / "C2" / "*.nc")))[-2:]
    g = ll(xr.open_mfdataset(files, combine="by_coords"))
    g = g.isel(lat=slice(None, None, 2), lon=slice(None, None, 2))
    frames = []
    for t in g.time.values:
        key = pd.Timestamp(t).strftime("%Y-%m")
        h = g["sithick"].sel(time=t).values; c = g["siconc"].sel(time=t).values
        save_png(h, g.lat.values, "viridis", 0, 2.5, LAYERS / "glorys_sithick" / f"{key}.png", mask=c >= 0.15)
        frames.append({"t": key, "url": f"/data/globe/layers/glorys_sithick/{key}.png"})
    add_layer("glorys_sithick", "Sea ice · reanalysis", "Sea-ice thickness, monthly mean (GLORYS12)", "m", "model_reanalysis",
              "Mercator Ocean GLORYS12V1 1/12° ocean–sea-ice reanalysis, via Copernicus Marine (C2)",
              "Model reanalysis with data assimilation (not a direct observation). Shown where concentration ≥ 15 %. Southern limit 80° S. Sub-sampled to 1/6°.",
              "viridis", 0, 2.5, frames, bounds_of(g.lat.values, g.lon.values), default=frames[-1]["t"])


# ---------------------------------------------------------------- C3 ensemble spread
def c3():
    f = sorted(glob.glob(str(CM / "C3" / "*.nc")))[-1]
    d = ll(xr.open_dataset(f))
    frames = []
    for t in d.time.values[-24:]:
        key = pd.Timestamp(t).strftime("%Y-%m")
        sd = d["siconc_std"].sel(time=t).values * 100; mn = d["siconc_mean"].sel(time=t).values
        save_png(sd, d.lat.values, "magma", 0, 25, LAYERS / "ens_sic_spread" / f"{key}.png", mask=mn >= 0.05)
        frames.append({"t": key, "url": f"/data/globe/layers/ens_sic_spread/{key}.png"})
    add_layer("ens_sic_spread", "Sea ice · reanalysis", "Sea-ice concentration uncertainty: multi-reanalysis ensemble spread", "% (1 std)",
              "model_reanalysis", "Copernicus Marine global ocean ensemble reanalysis, mean & standard deviation product (C3)",
              "Standard deviation of monthly sea-ice concentration across the reanalysis ensemble members — a measure of disagreement, not an error bar against observations.",
              "magma", 0, 25, frames, bounds_of(d.lat.values, d.lon.values), default=frames[-1]["t"])


# ---------------------------------------------------------------- C4 DMI ASIP 1 km SIC, 97 dates
def c4():
    frames, b = [], None
    for f in sorted(glob.glob(str(CM / "C4" / "*.nc"))):
        with xr.open_dataset(f) as d:
            d = ll(d)
            a = d["ice_concentration"].isel(time=0).values.astype("float32")
            lat = d.lat.values; lon = d.lon.values
        a = coarsen(a, 4); latc = lat[: len(lat) // 4 * 4].reshape(-1, 4).mean(1); lonc = lon[: len(lon) // 4 * 4].reshape(-1, 4).mean(1)
        if np.isfinite(a).sum() < 1000:
            continue
        key = Path(f).stem.split("_")[-1]; key = f"{key[:4]}-{key[4:6]}-{key[6:]}"
        save_png(a, latc, SIC_CMAP, 15, 100, LAYERS / "dmi_asip" / f"{key}.png", mask=a >= 15)
        frames.append({"t": key, "url": f"/data/globe/layers/dmi_asip/{key}.png"})
        b = bounds_of(latc, lonc)
    add_layer("dmi_asip", "Sea ice · observations", "Sea-ice concentration from SAR + AMSR2 (DMI ASIP, ML-03 test dates)", "%", "observation",
              "DMI ASIP automated sea-ice product (Sentinel-1 SAR + AMSR2), 1 km, via Copernicus Marine (C4)",
              "Daily analysis on the ML-03 test-scene dates (dates with almost no valid data are skipped); averaged from 0.025° to 0.1° for the globe. Cells below 15 % are transparent. Swath gaps leave holes.",
              SIC_CMAP, 15, 100, frames, b, default=frames[-1]["t"] if frames else None)


# ---------------------------------------------------------------- C5 IFREMER drift: speed frames + vectors
def drift_vectors(u: np.ndarray, v: np.ndarray, lat: np.ndarray, lon: np.ndarray, k_km: float = 1500.0,
                  lat0: float = -79.0, spacing: float = 1.6, vmin: float = 0.01) -> list[list[float]]:
    """Arrows as line segments. k_km = arrow length per (m/s); default 0.1 m/s -> 150 km (ice drift)."""
    segs = []
    for la in np.arange(lat0, -52.0, spacing):
        i = int(np.argmin(np.abs(lat - la)))
        step = spacing / max(np.cos(np.deg2rad(la)), 0.12)
        for lo in np.arange(-180.0, 180.0, step):
            j = int(np.argmin(np.abs(lon - lo)))
            uu, vv = float(u[i, j]), float(v[i, j])
            if not (np.isfinite(uu) and np.isfinite(vv)):
                continue
            sp = np.hypot(uu, vv)
            if sp < vmin:
                continue
            cl = np.cos(np.deg2rad(lat[i]))
            def pt(e_km, n_km, a=lat[i], o=lon[j]):
                return [round(float(o + e_km / (111.32 * cl)), 3), round(float(a + n_km / 110.57), 3)]
            e, n = uu * k_km, vv * k_km
            p0, p1 = pt(0, 0), pt(e, n)
            segs.append(p0 + p1)
            ang = np.arctan2(n, e); hl = 0.32 * np.hypot(e, n)
            for da in (2.6, -2.6):
                h = pt(e + hl * np.cos(ang + da), n + hl * np.sin(ang + da))
                segs.append(p1 + h)
    return segs


def c5():
    files = sorted(glob.glob(str(CM / "C5" / "*.nc")))
    frames, monthly = [], {}
    lat = lon = None
    for f in files:
        with xr.open_dataset(f) as d:
            d = ll(d).isel(depth=0)
            u = d["eastward_sea_ice_velocity"].load(); v = d["northward_sea_ice_velocity"].load()
            lat, lon = d.lat.values, d.lon.values
            spd = np.hypot(u, v)
            sm = spd.resample(time="MS").mean("time")
            um = u.resample(time="MS").mean("time"); vm = v.resample(time="MS").mean("time")
            cnt = spd.time.to_series().resample("MS").count()
            w = np.cos(np.deg2rad(spd.lat))
            for t in sm.time.values:
                ts = pd.Timestamp(t)
                if cnt.get(ts, 0) < 10:
                    continue
                key = ts.strftime("%Y-%m")
                a = sm.sel(time=t).values * 100
                monthly[key] = float(sm.sel(time=t).weighted(w).mean().values) * 100
                if np.isfinite(a).sum() < 500:
                    continue
                save_png(a, lat, "magma", 0, 20, LAYERS / "drift_speed" / f"{key}.png")
                fr = {"t": key, "url": f"/data/globe/layers/drift_speed/{key}.png"}
                if ts.year >= 2023:
                    segs = drift_vectors(um.sel(time=t).values, vm.sel(time=t).values, lat, lon)
                    p = VEC / "drift" / f"{key}.json"; p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(json.dumps({"segments": segs}, separators=(",", ":")))
                    fr["vectors"] = f"/data/globe/vectors/drift/{key}.json"
                frames.append(fr)
        log("C5", Path(f).name)
    add_layer("drift_speed", "Sea ice · observations", "Sea-ice drift: monthly mean speed and direction", "cm/s", "observation",
              "IFREMER / CERSAT AMSR-E + AMSR2 3-day sea-ice drift (P3D), via Copernicus Marine (C5)",
              "Colour: monthly mean of daily drift speed. Arrows (2023 onwards): monthly-mean drift vector; 0.1 m/s ≈ 150 km arrow. Passive-microwave drift is unreliable in summer melt.",
              "magma", 0, 20, frames, bounds_of(lat, lon), default=frames[-1]["t"])
    return pd.Series(monthly)


# ---------------------------------------------------------------- C6 SMOS thin-ice thickness, weekly
def c6():
    frames, lat, lon = [], None, None
    vmax = 3.0
    for f in sorted(glob.glob(str(CM / "C6" / "*.nc"))):
        with xr.open_dataset(f) as d:
            d = ll(d)
            lat, lon = d.lat.values, d.lon.values
            for t in d.time.values[::7]:
                a = d["sea_ice_thickness"].sel(time=t).values
                if np.isfinite(a).sum() < 2000:
                    continue
                key = pd.Timestamp(t).strftime("%Y-%m-%d")
                save_png(a, lat, "viridis", 0, vmax, LAYERS / "smos_sit" / f"{key}.png")
                frames.append({"t": key, "url": f"/data/globe/layers/smos_sit/{key}.png"})
    if frames:
        add_layer("smos_sit", "Sea ice · observations", "Sea-ice thickness, merged CryoSat-2 + Sentinel-3 + SMOS (weekly samples)", "m", "observation",
                  "AWI merged sea-ice thickness (CryoSat-2, Sentinel-3A/B altimetry + SMOS L-band), ESA product via Copernicus Marine (C6)",
                  "Daily L4 optimal-interpolation analysis; one field every 7 days is shown. Altimetry constrains thick ice, SMOS thin ice. Antarctic snow-depth assumptions dominate the uncertainty.",
                  "viridis", 0, vmax, frames, bounds_of(lat, lon), default=frames[-1]["t"])


# ---------------------------------------------------------------- C7 MULTIOBS ocean temperature anomaly
def c7():
    files = sorted(glob.glob(str(CM / "C7" / "*.nc")))
    m = ll(xr.open_mfdataset(files, combine="by_coords")).isel(depth=0)
    to = m["to"].isel(lat=slice(None, None, 2), lon=slice(None, None, 2)).load()
    base = to.sel(time=(to.time.dt.year >= 1993) & (to.time.dt.year <= 2020))
    clim = base.groupby("time.month").mean("time")
    frames = []
    for t in to.time.values[-36:]:
        ts = pd.Timestamp(t); key = ts.strftime("%Y-%m")
        a = (to.sel(time=t) - clim.sel(month=ts.month)).values
        save_png(a, to.lat.values, "RdBu_r", -2, 2, LAYERS / "multiobs_sst_anom" / f"{key}.png")
        frames.append({"t": key, "url": f"/data/globe/layers/multiobs_sst_anom/{key}.png"})
    add_layer("multiobs_sst_anom", "Ocean · observations", "Near-surface ocean temperature anomaly vs 1993–2020 (MULTIOBS)", "°C", "observation",
              "Copernicus Marine MULTIOBS global ocean T/S reconstruction from in-situ and satellite observations (C7)",
              "Monthly near-surface temperature minus the 1993–2020 mean of the same calendar month. Under sea ice, values are mostly interpolated from sparse profiles.",
              "RdBu_r", -2, 2, frames, bounds_of(to.lat.values, to.lon.values), default=frames[-1]["t"])
    w = np.cos(np.deg2rad(m.lat))
    sst = m["to"].weighted(w).mean(("lat", "lon")).load().to_series()
    mld = m["mlotst"].weighted(w).mean(("lat", "lon")).load().to_series()
    return sst, mld


# ---------------------------------------------------------------- ERA5 monthly anomaly frames (36 months)
def era5_monthly():
    specs = [("t2m", "2 m air temperature anomaly", "°C", "RdBu_r", 6, lambda d: d - 273.15),
             ("msl", "Mean sea-level pressure anomaly", "hPa", "PuOr_r", 12, lambda d: d / 100.0),
             ("sst", "Sea-surface temperature anomaly", "°C", "RdBu_r", 2, lambda d: d - 273.15)]
    for k, title, units, cmap, lim, conv in specs:
        da = conv(era5_var(k)).load().sortby("lat")
        base = da.sel(time=(da.time.dt.year >= CLIM[0]) & (da.time.dt.year <= CLIM[1]))
        clim = base.groupby("time.month").mean("time")
        frames = []
        for t in da.time.values[-36:]:
            ts = pd.Timestamp(t); key = ts.strftime("%Y-%m")
            a = (da.sel(time=t) - clim.sel(month=ts.month)).values
            mask = (np.abs(a) >= 2) if k == "siconc" else None  # no ice in either period -> transparent, not "zero anomaly" white
            save_png(a, da.lat.values, cmap, -lim, lim, LAYERS / f"era5_{k}_anom" / f"{key}.png", mask=mask, alpha=0.85)
            frames.append({"t": key, "url": f"/data/globe/layers/era5_{k}_anom/{key}.png"})
        add_layer(f"era5_{k}_anom_series", "Atmosphere · reanalysis", f"{title} vs {CLIM[0]}–{CLIM[1]} (ERA5, monthly)", units, "reanalysis_anomaly",
                  "ECMWF ERA5 monthly averaged reanalysis, Copernicus Climate Data Store",
                  f"Monthly mean minus the {CLIM[0]}–{CLIM[1]} mean of the same calendar month. 0.25° grid.",
                  cmap, -lim, lim, frames, bounds_of(da.lat.values, da.lon.values), default=frames[-1]["t"])


# ---------------------------------------------------------------- ERA5 daily t2m: frames + daily record
def era5_daily():
    files = sorted(glob.glob(str(E5D / "t2m" / "era5_daily_mean_t2m_*.nc")))
    parts = []
    last = None
    for f in files:
        with xr.open_dataset(f) as d:
            d = _std(d)
            da = (d["t2m"] - 273.15).load()
            w = np.cos(np.deg2rad(da.lat))
            parts.append(da.where(da.lat <= -60, drop=True).weighted(np.cos(np.deg2rad(da.where(da.lat <= -60, drop=True).lat))).mean(("lat", "lon")).to_series())
            last = da
    frames = []
    for t in last.time.values[-92:]:
        key = pd.Timestamp(t).strftime("%Y-%m-%d")
        save_png(last.sel(time=t).values, last.lat.values, "RdYlBu_r", -60, 5, LAYERS / "era5_t2m_daily" / f"{key}.png", alpha=0.82)
        frames.append({"t": key, "url": f"/data/globe/layers/era5_t2m_daily/{key}.png"})
    add_layer("era5_t2m_daily", "Atmosphere · reanalysis", "2 m air temperature, daily mean (ERA5)", "°C", "reanalysis",
              "ECMWF ERA5 hourly reanalysis aggregated to daily means (Copernicus CDS), 0.5° grid",
              "Absolute daily-mean temperature for the latest 92 days available on disk.",
              "RdYlBu_r", -60, 5, frames, bounds_of(last.lat.values, last.lon.values), default=frames[-1]["t"])
    s = pd.concat(parts).sort_index()
    return s[~s.index.duplicated()]


# ---------------------------------------------------------------- ERA5 monthly: more anomaly maps + series
def era5_monthly_more() -> dict:
    """Anomaly frames (last 36 months) for upper-air, cloud, precipitation, sea ice and wind, plus three new
    Antarctic-mean series (with NSIDC sectors) for the climate explorer."""
    from build_climate_series import SECTORS, _pack, _wmean
    G0 = 9.80665
    specs = [("t850", "850 hPa temperature anomaly", "°C", "RdBu_r", 6, lambda d: d - 273.15),
             ("z500", "500 hPa geopotential height anomaly", "dam", "PuOr_r", 15, lambda d: d / G0 / 10.0),
             ("tp", "Precipitation anomaly", "mm/day", "BrBG", 1.5, lambda d: d * 1000.0),
             ("tcc", "Total cloud cover anomaly", "%", "PiYG_r", 20, lambda d: d * 100.0),
             ("siconc", "Sea-ice concentration anomaly", "%", "RdBu", 40, lambda d: d * 100.0)]
    series: dict = {}
    for k, title, units, cmap, lim, conv in specs:
        da = conv(era5_var(k)).load().sortby("lat")
        base = da.sel(time=(da.time.dt.year >= CLIM[0]) & (da.time.dt.year <= CLIM[1]))
        clim = base.groupby("time.month").mean("time")
        frames = []
        for t in da.time.values[-36:]:
            ts = pd.Timestamp(t); key = ts.strftime("%Y-%m")
            a = (da.sel(time=t) - clim.sel(month=ts.month)).values
            mask = (np.abs(a) >= 2) if k == "siconc" else None  # no ice in either period -> transparent, not "zero anomaly" white
            save_png(a, da.lat.values, cmap, -lim, lim, LAYERS / f"era5_{k}_anom" / f"{key}.png", mask=mask, alpha=0.85)
            frames.append({"t": key, "url": f"/data/globe/layers/era5_{k}_anom/{key}.png"})
        note = {"siconc": " ERA5 sea ice is the OSI SAF-based boundary condition, not an independent observation. Changes smaller than 2 % are transparent.",
                "tp": " Precipitation is a model forecast field, the least constrained ERA5 variable over Antarctica."}.get(k, "")
        add_layer(f"era5_{k}_anom_series", "Sea ice · reanalysis" if k == "siconc" else "Atmosphere · reanalysis",
                  f"{title} vs {CLIM[0]}–{CLIM[1]} (ERA5, monthly)", units, "reanalysis_anomaly",
                  "ECMWF ERA5 monthly averaged reanalysis, Copernicus Climate Data Store",
                  f"Monthly mean minus the {CLIM[0]}–{CLIM[1]} mean of the same calendar month. 0.25° grid.{note}",
                  cmap, -lim, lim, frames, bounds_of(da.lat.values, da.lon.values), default=frames[-1]["t"])
        if k in ("t850", "z500", "tcc"):
            nd = 2 if k != "z500" else 1
            series[f"era5_{k}"] = {"title": {"t850": "850 hPa air temperature", "z500": "500 hPa geopotential height",
                                             "tcc": "Total cloud cover"}[k],
                                   "units": {"t850": "degC", "z500": "dam", "tcc": "%"}[k],
                                   "source": "ERA5 monthly averaged reanalysis (Copernicus CDS)", "domain": "60-90S",
                                   "antarctic": _pack(_wmean(da, -60.0), nd),
                                   "sectors": {n: _pack(_wmean(da, -60.0, b), nd) for n, b in SECTORS.items()}}
        del da, base, clim
    # 10 m wind: speed of the monthly-mean vector
    u, v = era5_var("u10").load().sortby("lat"), era5_var("v10").load().sortby("lat")
    ws = np.hypot(u, v)
    base = ws.sel(time=(ws.time.dt.year >= CLIM[0]) & (ws.time.dt.year <= CLIM[1]))
    clim = base.groupby("time.month").mean("time")
    frames = []
    for t in ws.time.values[-36:]:
        ts = pd.Timestamp(t); key = ts.strftime("%Y-%m")
        save_png((ws.sel(time=t) - clim.sel(month=ts.month)).values, ws.lat.values, "PRGn_r", -3, 3,
                 LAYERS / "era5_wind10_anom" / f"{key}.png", alpha=0.85)
        frames.append({"t": key, "url": f"/data/globe/layers/era5_wind10_anom/{key}.png"})
    add_layer("era5_wind10_anom_series", "Atmosphere · reanalysis", f"10 m wind speed anomaly vs {CLIM[0]}–{CLIM[1]} (ERA5, monthly)",
              "m/s", "reanalysis_anomaly", "ECMWF ERA5 monthly averaged reanalysis, Copernicus Climate Data Store",
              "Speed of the monthly-mean 10 m wind vector minus its 1991–2020 calendar-month mean. Speed of the mean vector is lower than mean speed in variable winds.",
              "PRGn_r", -3, 3, frames, bounds_of(ws.lat.values, ws.lon.values), default=frames[-1]["t"])
    return series


# ---------------------------------------------------------------- ERA5 daily: more map layers + daily records
def _daily_files(v: str) -> list[str]:
    return sorted(glob.glob(str(E5D / v / f"era5_daily_mean_{v}_*.nc")))


def _daily_mean_series(v: str, conv) -> pd.Series:
    parts = []
    for f in _daily_files(v):
        with xr.open_dataset(f) as d:
            da = conv(_std(d)[v]).load()
            sel = da.where(da.lat <= -60, drop=True)
            parts.append(sel.weighted(np.cos(np.deg2rad(sel.lat))).mean(("lat", "lon")).to_series())
    s = pd.concat(parts).sort_index()
    return s[~s.index.duplicated()]


def era5_daily_more() -> dict:
    G0 = 9.80665
    specs = [  # var, layer id, title, units, conversion, cmap, vmin, vmax, mask rule, note
        ("t850", "era5_t850_daily", "850 hPa air temperature, daily mean (ERA5)", "°C", lambda d: d - 273.15, "RdYlBu_r", -40, 5, None,
         " Over the high plateau the 850 hPa surface is below ground and values are extrapolated."),
        ("z500", "era5_z500_daily", "500 hPa geopotential height, daily mean (ERA5)", "dam", lambda d: d / G0 / 10.0, "Spectral_r", 480, 570, None,
         " Lows (troughs) in blue, ridges in red: the westerly jet lies where the colours change fastest."),
        ("msl", "era5_msl_daily", "Mean sea-level pressure, daily mean (ERA5)", "hPa", lambda d: d / 100.0, "viridis", 950, 1030, None,
         " Over the ice sheet sea-level pressure is a reduction to a fictitious sea level and should not be read literally."),
        ("tcc", "era5_tcc_daily", "Total cloud cover, daily mean (ERA5)", "%", lambda d: d * 100.0, "bone", 0, 100, None, ""),
        ("tp", "era5_tp_daily", "Total precipitation, daily total (ERA5)", "mm/day", lambda d: d * 1000.0, PRECIP_CMAP, 0, 10, "tp",
         " Daily total estimated from four 6-hourly samples (00/06/12/18 UTC × 24); a model forecast field. Below 0.2 mm/day is transparent."),
        ("siconc", "era5_siconc_daily", "Sea-ice concentration, daily (ERA5 boundary condition)", "%", lambda d: d * 100.0, SIC_CMAP, 15, 100, "sic",
         " ERA5 prescribes sea ice from OSI SAF; this is not an independent observation. Below 15 % is transparent."),
    ]
    for v, lid, title, units, conv, cmap, vmin, vmax, mrule, note in specs:
        fs = _daily_files(v)
        if not fs:
            continue
        with xr.open_dataset(fs[-1]) as d:
            da = conv(_std(d)[v]).load()
        frames = []
        for t in da.time.values[-92:]:
            key = pd.Timestamp(t).strftime("%Y-%m-%d")
            a = da.sel(time=t).values
            mask = (a >= 0.2) if mrule == "tp" else (a >= 15) if mrule == "sic" else None
            save_png(a, da.lat.values, cmap, vmin, vmax, LAYERS / lid / f"{key}.png", mask=mask, alpha=0.82)
            frames.append({"t": key, "url": f"/data/globe/layers/{lid}/{key}.png"})
        add_layer(lid, "Sea ice · reanalysis" if v == "siconc" else "Atmosphere · reanalysis", title, units, "reanalysis",
                  "ECMWF ERA5 hourly reanalysis aggregated to daily means (Copernicus CDS), 0.5° grid",
                  f"Daily values for the latest {len(frames)} days available on disk.{note}",
                  cmap, vmin, vmax, frames, bounds_of(da.lat.values, da.lon.values), default=frames[-1]["t"])
        del da

    # 10 m wind: speed + arrows (latest 92 days)
    with xr.open_dataset(_daily_files("u10")[-1]) as du, xr.open_dataset(_daily_files("v10")[-1]) as dv:
        u, v = _std(du)["u10"].load(), _std(dv)["v10"].load()
    frames = []
    for t in u.time.values[-92:]:
        key = pd.Timestamp(t).strftime("%Y-%m-%d")
        uu, vv = u.sel(time=t).values, v.sel(time=t).values
        save_png(np.hypot(uu, vv), u.lat.values, "YlGnBu_r", 0, 20, LAYERS / "era5_wind10_daily" / f"{key}.png", alpha=0.78)
        segs = drift_vectors(uu, vv, u.lat.values, u.lon.values, k_km=14.0, lat0=-87.0, spacing=2.6, vmin=1.0)
        p = VEC / "wind10" / f"{key}.json"; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"segments": segs}, separators=(",", ":")), encoding="utf-8")
        frames.append({"t": key, "url": f"/data/globe/layers/era5_wind10_daily/{key}.png", "vectors": f"/data/globe/vectors/wind10/{key}.json"})
    add_layer("era5_wind10_daily", "Atmosphere · reanalysis", "10 m wind speed and direction, daily mean (ERA5)", "m/s", "reanalysis",
              "ECMWF ERA5 hourly reanalysis aggregated to daily means (Copernicus CDS), 0.5° grid",
              "Speed of the daily-mean 10 m wind vector; arrows show direction (10 m/s ≈ 140 km). Katabatic winds flow off the plateau toward the coast.",
              "YlGnBu_r", 0, 20, frames, bounds_of(u.lat.values, u.lon.values), default=frames[-1]["t"])

    # daily Antarctic-mean records (60–90° S)
    rec = {"msl": _daily_mean_series("msl", lambda d: d / 100.0),
           "t850": _daily_mean_series("t850", lambda d: d - 273.15),
           "z500": _daily_mean_series("z500", lambda d: d / G0 / 10.0)}
    ws = []
    years_u = {Path(f).stem[-4:]: f for f in _daily_files("u10")}
    for f in _daily_files("v10"):
        y = Path(f).stem[-4:]
        if y not in years_u:
            continue
        with xr.open_dataset(years_u[y]) as du, xr.open_dataset(f) as dv:
            sp = np.hypot(_std(du)["u10"].load(), _std(dv)["v10"].load())
            sel = sp.where(sp.lat <= -60, drop=True)
            ws.append(sel.weighted(np.cos(np.deg2rad(sel.lat))).mean(("lat", "lon")).to_series())
    if ws:
        s = pd.concat(ws).sort_index(); rec["wind10"] = s[~s.index.duplicated()]
    for k, s in rec.items():
        log("daily record", k, str(s.index[0])[:10], "->", str(s.index[-1])[:10], len(s))
    return rec


def by_year(s: pd.Series, base: tuple[int, int], nd: int) -> dict:
    s = s.dropna(); s.index = pd.to_datetime(s.index)
    doy = np.minimum(s.index.dayofyear.values, 365)
    df = pd.DataFrame({"y": s.index.year, "d": doy, "v": s.values})
    years = {}
    for y, g in df.groupby("y"):
        arr = [None] * 365
        for d, v in zip(g.d, g.v):
            arr[d - 1] = round(float(v), nd)
        years[str(y)] = arr
    b = df[(df.y >= base[0]) & (df.y <= base[1])].groupby("d")["v"]
    q = b.quantile([0.1, 0.9]).unstack()
    stat = lambda x: [round(float(v), nd) if np.isfinite(v) else None for v in x.reindex(range(1, 366)).values]
    return {"years": years, "clim": {"base": f"{base[0]}-{base[1]}", "mean": stat(b.mean()), "min": stat(b.min()), "max": stat(b.max()),
                                     "p10": stat(q[0.1]), "p90": stat(q[0.9])}}


def pack_monthly(s: pd.Series, base: tuple[int, int], nd: int) -> dict:
    s = s.dropna(); s.index = pd.to_datetime(s.index); s = s.sort_index()
    b = s[(s.index.year >= base[0]) & (s.index.year <= base[1])]
    clim = b.groupby(b.index.month).mean()
    a = s - clim.reindex(s.index.month).values
    ok = np.isfinite(a.values) & np.isfinite(s.values)  # months with no reference climatology are dropped, never NaN
    s, a = s[ok], a[ok]
    return {"t": [d.strftime("%Y-%m") for d in s.index], "v": [round(float(x), nd) for x in s.values],
            "anom": [round(float(x), nd) for x in a.values]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    failed: list[str] = []

    def run(name: str) -> bool:
        return not only or name in only

    def safe(name, fn):
        try:
            return fn()
        except Exception as e:  # one product failing must not lose the others
            import traceback
            traceback.print_exc()
            failed.append(f"{name}: {e}")
            return None
    daily: dict = {"meta": {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "day_index": "day of year 1-365 (31 Dec of leap years folded onto day 365)"}}
    extra: dict = {}
    ext = safe("c1", c1) if run("c1") else None
    if ext is not None:
        daily["sea_ice_extent"] = {"title": "Daily Antarctic sea-ice extent (concentration ≥ 15 %)", "units": "million km²",
                                   "source": "EUMETSAT OSI SAF OSI-450-a CDR + OSI-430-a ICDR via Copernicus Marine (C1)",
                                   "data_type": "observation",
                                   "note": "Days with missing swaths are omitted. Before 1987 the SMMR record is every other day.",
                                   **by_year(ext, (1991, 2020), 3)}
    if run("c2"): safe("c2", c2)
    if run("c3"): safe("c3", c3)
    if run("c4"): safe("c4", c4)
    ds = safe("c5", c5) if run("c5") else None
    if ds is not None:
        extra["ifremer_drift_speed"] = {"title": "Mean sea-ice drift speed (monthly mean of daily speeds, ice-covered cells)", "units": "cm/s",
                                        "domain": "50-90S", "clim": "2003-2020",
                                        "source": "IFREMER AMSR-E/AMSR2 3-day sea-ice drift via Copernicus Marine (C5)",
                                        "antarctic": pack_monthly(ds, (2003, 2020), 2)}
    if run("c6"): safe("c6", c6)
    r7 = safe("c7", c7) if run("c7") else None
    if r7 is not None:
        sst, mld = r7
        extra["multiobs_sst"] = {"title": "Near-surface ocean temperature, Southern Ocean mean", "units": "degC", "domain": "50-82S", "clim": "1993-2020",
                                 "source": "Copernicus Marine MULTIOBS observation-based T/S reconstruction (C7)", "antarctic": pack_monthly(sst, (1993, 2020), 3)}
        extra["multiobs_mld"] = {"title": "Ocean mixed-layer depth, Southern Ocean mean", "units": "m", "domain": "50-82S", "clim": "1993-2020",
                                 "source": "Copernicus Marine MULTIOBS observation-based T/S reconstruction (C7)", "antarctic": pack_monthly(mld, (1993, 2020), 1)}
    if run("era5m"): safe("era5m", era5_monthly)
    t = safe("era5d", era5_daily) if run("era5d") else None
    if t is not None:
        daily["t2m"] = {"title": "Daily Antarctic-mean 2 m air temperature (60–90° S, area-weighted)", "units": "°C",
                        "source": "ECMWF ERA5 daily means (Copernicus CDS)", "data_type": "reanalysis",
                        "note": "Daily ERA5 on disk starts in 2014, so the reference envelope uses 2014–2025 (short baseline).",
                        **by_year(t, (2014, 2025), 2)}
    mm = safe("era5m2", era5_monthly_more) if run("era5m2") else None
    if mm:
        extra.update(mm)
    rec = safe("era5d2", era5_daily_more) if run("era5d2") else None
    if rec:
        meta = {"msl": ("Daily Antarctic-mean sea-level pressure (60–90° S, area-weighted)", "hPa", 1, " Includes sea-level-reduced values over the ice sheet."),
                "t850": ("Daily Antarctic-mean 850 hPa temperature (60–90° S, area-weighted)", "°C", 2, " Includes values extrapolated below the plateau surface."),
                "z500": ("Daily Antarctic-mean 500 hPa geopotential height (60–90° S, area-weighted)", "dam", 1, " Low values mean a deep polar vortex; high values mean ridging/blocking."),
                "wind10": ("Daily Antarctic-mean 10 m wind speed (60–90° S, area-weighted)", "m/s", 2, " Speed of the daily-mean vector at each cell, then averaged.")}
        for k, s in rec.items():
            title, units, nd, extra_note = meta[k]
            y0 = int(str(s.index.min())[:4])
            have = sorted({int(str(x)[:4]) for x in s.index})
            gaps = [y for y in range(y0, have[-1] + 1) if y not in have]
            daily[f"era5_{k}"] = {"title": title, "units": units, "source": "ECMWF ERA5 daily means (Copernicus CDS)", "data_type": "reanalysis",
                                  "note": f"Daily ERA5 on disk for this variable starts in {y0}, so the reference envelope uses {y0}–2025 (short baseline)."
                                          + (f" Years not yet downloaded: {', '.join(map(str, gaps))}." if gaps else "") + extra_note,
                                  **by_year(s, (y0, 2025), nd)}

    # merge outputs with any previous run so partial rebuilds keep the other layers
    cpath = G / "catalog.json"
    old = json.loads(cpath.read_text(encoding="utf-8")) if cpath.exists() else {"layers": []}
    ids = {l["id"] for l in catalog}
    layers = [l for l in old["layers"] if l["id"] not in ids] + catalog
    cpath.write_text(json.dumps({"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "layers": layers}, separators=(",", ":")), encoding="utf-8")
    dpath = OUT / "daily_series.json"
    if len(daily) > 1:
        prev = json.loads(dpath.read_text(encoding="utf-8")) if dpath.exists() else {}
        prev.update(daily)
        dpath.write_text(json.dumps(prev, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    if extra:
        cs = json.loads((OUT / "climate_series.json").read_text(encoding="utf-8"))
        cs["series"].update(extra)
        (OUT / "climate_series.json").write_text(json.dumps(cs, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    log("done", len(layers), "layers", "FAILED: " + "; ".join(failed) if failed else "")


if __name__ == "__main__":
    main()
