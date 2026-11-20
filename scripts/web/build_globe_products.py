"""Build time-enabled globe layers and extra series for the AETHENTRA web frontend.

Everything is computed from files already on disk. Nothing is downloaded, nothing is synthetic.
Inputs (all regular lat/lon grids, so images are equirectangular EPSG:4326 and drape directly on the globe):
  C1  EUMETSAT OSI SAF SIC CDR/ICDR daily (Copernicus Marine)     -> monthly SIC frames 1979-2025, daily extent record
  C2  Mercator GLORYS12 monthly reanalysis                          -> monthly sea-ice thickness frames
  C3  Copernicus Marine multi-reanalysis ensemble (mean/std)        -> SIC ensemble spread (uncertainty) frames
  C4  DMI ASIP SAR+AMSR2 1 km SIC (97 ML-03 test dates)            -> high-resolution SIC frames (0.1 deg)
  C5  IFREMER AMSR2/AMSR-E 3-day sea-ice drift                     -> monthly drift speed frames + drift vectors
  C6  SMOS (+CryoSat-2) sea-ice thickness daily                    -> weekly thin-ice thickness frames
  C7  MULTIOBS ARMOR3D-type observation-based ocean T/S            -> monthly upper-ocean temperature anomaly frames
  ERA5 monthly (Copernicus CDS)                                     -> 36-month t2m / MSLP / SST anomaly frames
  ERA5 daily mean t2m 2014-2026                                     -> last 92 daily frames, daily Antarctic-mean record

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
        a = coarsen(a, 4); latc = coarsen(lat[:, None], 4)[:, 0]; lonc = coarsen(lon[None, :], 4)[0]
        if np.isfinite(a).sum() < 1000:
            continue
        key = Path(f).stem.split("_")[-1]; key = f"{key[:4]}-{key[4:6]}-{key[6:]}"
        save_png(a, latc, SIC_CMAP, 15, 100, LAYERS / "dmi_asip" / f"{key}.png", mask=a >= 15)
        frames.append({"t": key, "url": f"/data/globe/layers/dmi_asip/{key}.png"})
        b = bounds_of(latc, lonc)
    add_layer("dmi_asip", "Sea ice · observations", "Sea-ice concentration from SAR + AMSR2 (DMI ASIP, ML-03 test dates)", "%", "observation",
              "DMI ASIP automated sea-ice product (Sentinel-1 SAR + AMSR2), 1 km, via Copernicus Marine (C4)",
              "Daily analysis on the 97 dates of the ML-03 test scenes; averaged from 0.025° to 0.1° for the globe. Cells below 15 % are transparent. Swath gaps leave holes.",
              SIC_CMAP, 15, 100, frames, b, default=frames[-1]["t"] if frames else None)


# ---------------------------------------------------------------- C5 IFREMER drift: speed frames + vectors
def drift_vectors(u: np.ndarray, v: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> list[list[float]]:
    segs = []
    k_km = 1500.0  # arrow length per (m/s): 0.1 m/s -> 150 km
    for la in np.arange(-79.0, -52.0, 1.6):
        i = int(np.argmin(np.abs(lat - la)))
        step = 1.6 / max(np.cos(np.deg2rad(la)), 0.12)
        for lo in np.arange(-180.0, 180.0, step):
            j = int(np.argmin(np.abs(lon - lo)))
            uu, vv = float(u[i, j]), float(v[i, j])
            if not (np.isfinite(uu) and np.isfinite(vv)):
                continue
            sp = np.hypot(uu, vv)
            if sp < 0.01:
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
    vmax = 1.0
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
        add_layer("smos_sit", "Sea ice · observations", "Thin sea-ice thickness from SMOS L-band radiometry (weekly samples)", "m", "observation",
                  "ESA SMOS sea-ice thickness product, via Copernicus Marine (C6)",
                  "L-band brightness temperature retrieval, sensitive to thin ice (≲ 1 m); thicker ice saturates. One daily field every 7 days.",
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
            save_png(a, da.lat.values, cmap, -lim, lim, LAYERS / f"era5_{k}_anom" / f"{key}.png", alpha=0.85)
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
    return {"t": [d.strftime("%Y-%m") for d in s.index], "v": [round(float(x), nd) for x in s.values],
            "anom": [round(float(x), nd) for x in a.values]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    run = lambda name: not only or name in only
    daily: dict = {"meta": {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "day_index": "day of year 1-365 (31 Dec of leap years folded onto day 365)"}}
    extra: dict = {}
    if run("c1"):
        ext = c1()
        daily["sea_ice_extent"] = {"title": "Daily Antarctic sea-ice extent (concentration ≥ 15 %)", "units": "million km²",
                                   "source": "EUMETSAT OSI SAF OSI-450-a CDR + OSI-430-a ICDR via Copernicus Marine (C1)",
                                   "data_type": "observation",
                                   "note": "Days with missing swaths are omitted. Before 1987 the SMMR record is every other day.",
                                   **by_year(ext, (1991, 2020), 3)}
    if run("c2"): c2()
    if run("c3"): c3()
    if run("c4"): c4()
    if run("c5"):
        ds = c5()
        extra["ifremer_drift_speed"] = {"title": "Mean sea-ice drift speed (monthly mean of daily speeds, ice-covered cells)", "units": "cm/s",
                                        "domain": "50-90S", "clim": "2003-2020",
                                        "source": "IFREMER AMSR-E/AMSR2 3-day sea-ice drift via Copernicus Marine (C5)",
                                        "antarctic": pack_monthly(ds, (2003, 2020), 2)}
    if run("c6"): c6()
    if run("c7"):
        sst, mld = c7()
        extra["multiobs_sst"] = {"title": "Near-surface ocean temperature, Southern Ocean mean", "units": "degC", "domain": "50-82S", "clim": "1993-2020",
                                 "source": "Copernicus Marine MULTIOBS observation-based T/S reconstruction (C7)", "antarctic": pack_monthly(sst, (1993, 2020), 3)}
        extra["multiobs_mld"] = {"title": "Ocean mixed-layer depth, Southern Ocean mean", "units": "m", "domain": "50-82S", "clim": "1993-2020",
                                 "source": "Copernicus Marine MULTIOBS observation-based T/S reconstruction (C7)", "antarctic": pack_monthly(mld, (1993, 2020), 1)}
    if run("era5m"): era5_monthly()
    if run("era5d"):
        t = era5_daily()
        daily["t2m"] = {"title": "Daily Antarctic-mean 2 m air temperature (60–90° S, area-weighted)", "units": "°C",
                        "source": "ECMWF ERA5 daily means (Copernicus CDS)", "data_type": "reanalysis",
                        "note": "Daily ERA5 on disk starts in 2014, so the reference envelope uses 2014–2025 (short baseline).",
                        **by_year(t, (2014, 2025), 2)}

    # merge outputs with any previous run so partial rebuilds keep the other layers
    cpath = G / "catalog.json"
    old = json.loads(cpath.read_text()) if cpath.exists() else {"layers": []}
    ids = {l["id"] for l in catalog}
    layers = [l for l in old["layers"] if l["id"] not in ids] + catalog
    cpath.write_text(json.dumps({"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "layers": layers}, separators=(",", ":")))
    dpath = OUT / "daily_series.json"
    if len(daily) > 1:
        prev = json.loads(dpath.read_text()) if dpath.exists() else {}
        prev.update(daily)
        dpath.write_text(json.dumps(prev, separators=(",", ":")))
    if extra:
        cs = json.loads((OUT / "climate_series.json").read_text())
        cs["series"].update(extra)
        (OUT / "climate_series.json").write_text(json.dumps(cs, separators=(",", ":")))
    log("done", len(layers), "layers")


if __name__ == "__main__":
    main()
