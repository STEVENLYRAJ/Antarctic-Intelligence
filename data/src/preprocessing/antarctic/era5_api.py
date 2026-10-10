"""Integration of the existing CDS API scripts (EXTERNAL APIs/API.py, PRESSUREAPI.py) with the pipeline.

* The scripts are parsed with ``ast`` - they are NEVER imported or executed by the pipeline,
  because importing them would immediately submit a Copernicus CDS request.
* Their outputs (ERA5 NetCDF, not JSON: both requests set ``data_format = "netcdf"``) are
  searched for locally and, when present, processed by the schema-aware handlers below
  (single-level and pressure-level products are kept distinct).
* ``retrieve_era5`` is an opt-in, guarded wrapper (dry-run by default) that reuses the
  request from a script, restricts it to Antarctica and refuses oversized requests.

CLI (dry run, prints the size estimate only):
    python -m data.src.preprocessing.antarctic.era5_api --script API.py --years 2023 --months 01
"""
from __future__ import annotations

import argparse
import ast
import calendar
import datetime as dt
import os
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from .common import LOG, add_output, finish, issue, new_record, rel, step, utcnow, write_json
from .config import API_DIR, ANTARCTIC_LAT_LIMIT, ERA5_RAW_DIR, PROCESSED_DIR, RAW_DIR, ROOT

API_SCRIPTS = {
    "API.py": {"dataset_id": "era5_single_levels", "name": "ERA5 hourly data on single levels (CDS API request in API.py)"},
    "PRESSUREAPI.py": {"dataset_id": "era5_pressure_levels", "name": "ERA5 hourly data on pressure levels (CDS API request in PRESSUREAPI.py)"},
}

# ERA5 CDS variable name -> (NetCDF short name, expected units, plausible physical range)
ERA5_VARS = {
    # single levels
    "10m_u_component_of_wind": ("u10", "m s**-1", (-150, 150)),
    "10m_v_component_of_wind": ("v10", "m s**-1", (-150, 150)),
    "2m_dewpoint_temperature": ("d2m", "K", (150, 330)),
    "2m_temperature": ("t2m", "K", (150, 340)),
    "mean_sea_level_pressure": ("msl", "Pa", (85000, 110000)),
    "sea_surface_temperature": ("sst", "K", (260, 315)),
    "surface_pressure": ("sp", "Pa", (40000, 110000)),
    "total_precipitation": ("tp", "m", (0, 1)),
    "10m_u_component_of_neutral_wind": ("u10n", "m s**-1", (-150, 150)),
    "10m_v_component_of_neutral_wind": ("v10n", "m s**-1", (-150, 150)),
    "snow_depth": ("sd", "m of water equivalent", (0, 15)),
    "snowfall": ("sf", "m of water equivalent", (0, 1)),
    "cloud_base_height": ("cbh", "m", (0, 30000)),
    "lake_depth": ("dl", "m", (0, 2000)),
    "lake_ice_depth": ("licd", "m", (0, 20)),
    "boundary_layer_height": ("blh", "m", (0, 10000)),
    "land_sea_mask": ("lsm", "(0 - 1)", (0, 1)),
    "total_column_water_vapour": ("tcwv", "kg m**-2", (0, 100)),
    "surface_sensible_heat_flux": ("sshf", "J m**-2", (-1e8, 1e8)),
    "surface_net_thermal_radiation": ("str", "J m**-2", (-1e8, 1e8)),
    "surface_net_solar_radiation": ("ssr", "J m**-2", (-1e8, 1e8)),
    "surface_latent_heat_flux": ("slhf", "J m**-2", (-1e8, 1e8)),
    "total_cloud_cover": ("tcc", "(0 - 1)", (0, 1)),
    "sea_ice_cover": ("siconc", "(0 - 1)", (0, 1)),
    "skin_temperature": ("skt", "K", (150, 350)),
    # pressure levels
    "divergence": ("d", "s**-1", (-0.01, 0.01)),
    "geopotential": ("z", "m**2 s**-2", (-10000, 400000)),
    "ozone_mass_mixing_ratio": ("o3", "kg kg**-1", (0, 2e-5)),
    "potential_vorticity": ("pv", "K m**2 kg**-1 s**-1", (-1e-3, 1e-3)),
    "relative_humidity": ("r", "%", (-5, 160)),
    "specific_cloud_ice_water_content": ("ciwc", "kg kg**-1", (0, 0.01)),
    "specific_cloud_liquid_water_content": ("clwc", "kg kg**-1", (0, 0.01)),
    "specific_humidity": ("q", "kg kg**-1", (0, 0.05)),
    "temperature": ("t", "K", (150, 340)),
    "u_component_of_wind": ("u", "m s**-1", (-150, 150)),
    "v_component_of_wind": ("v", "m s**-1", (-150, 150)),
    "vertical_velocity": ("w", "Pa s**-1", (-20, 20)),
    "vorticity": ("vo", "s**-1", (-0.01, 0.01)),
}
SHORT = {v[0]: (k, v[1], v[2]) for k, v in ERA5_VARS.items()}
ERA5_STANDARD_LEVELS = [1, 2, 3, 5, 7, 10, 20, 30, 50, 70, 100, 125, 150, 175, 200, 225, 250, 300, 350, 400, 450, 500,
                        550, 600, 650, 700, 750, 775, 800, 825, 850, 875, 900, 925, 950, 975, 1000]
ERA5_LATENCY_DAYS = 5          # ERA5 (final + ERA5T) is published ~5 days behind real time
GRID_POINTS_025 = 1440 * 721   # global 0.25 deg grid
ANTARCTIC_AREA = [-60, -180, -90, 180]   # CDS order: North, West, South, East


# --------------------------------------------------------------------------- script parsing
def parse_api_script(path: Path) -> dict:
    """Extract ``dataset`` and ``request`` literals from a cdsapi script without executing it."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = {"script": rel(path), "dataset": None, "request": None, "imports": [], "calls": []}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ("dataset", "request"):
                out[node.targets[0].id] = ast.literal_eval(node.value)
        elif isinstance(node, ast.Import):
            out["imports"] += [a.name for a in node.names]
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            out["calls"].append(node.func.attr)
    out["executes_on_import"] = not any(isinstance(n, ast.If) and "__main__" in ast.dump(n) for n in tree.body)
    out["output_target"] = ("cdsapi default: .download() with no target writes a file named after the CDS result "
                            "into the current working directory")
    return out


def estimate_request(req: dict, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    last_available = today - dt.timedelta(days=ERA5_LATENCY_DAYS)
    valid, invalid, future = 0, 0, 0
    for y in req.get("year", []):
        for m in req.get("month", []):
            for d in req.get("day", []):
                y_, m_, d_ = int(y), int(m), int(d)
                if d_ > calendar.monthrange(y_, m_)[1]:
                    invalid += 1
                elif dt.date(y_, m_, d_) > last_available:
                    future += 1
                else:
                    valid += 1
    n_var = len(req.get("variable", []))
    n_time = len(req.get("time", []))
    n_lev = len(req.get("pressure_level", [])) or 1
    area = req.get("area")
    if area:
        n, w, s, e = area
        npts = (int(round((e - w) / 0.25))) * (int(round((n - s) / 0.25)) + 1)
        npts = min(npts, GRID_POINTS_025)
    else:
        npts = GRID_POINTS_025
    fields = valid * n_var * n_time * n_lev
    return {
        "variables": n_var, "years": [req.get("year", [None])[0], req.get("year", [None])[-1]],
        "valid_dates": valid, "invalid_calendar_dates_ignored": invalid, "dates_not_yet_available": future,
        "times_per_day": n_time, "pressure_levels": n_lev, "area": area or "global (not specified)",
        "grid_points_per_field": npts, "fields": fields,
        "uncompressed_float32_bytes": fields * npts * 4,
        "uncompressed_float32_TB": round(fields * npts * 4 / 1e12, 2),
        "estimated_against_date": str(today),
    }


def credential_status() -> dict:
    """Report only WHETHER credentials are configured; never read or log their values."""
    try:
        import cdsapi  # noqa: F401
        cdsapi_installed = True
    except Exception:
        cdsapi_installed = False
    return {"cdsapi_installed": cdsapi_installed,
            "cdsapirc_present": (Path.home() / ".cdsapirc").exists(),
            "env_CDSAPI_URL_set": "CDSAPI_URL" in os.environ, "env_CDSAPI_KEY_set": "CDSAPI_KEY" in os.environ}


# --------------------------------------------------------------------------- locating outputs
def _looks_like_era5(path: Path) -> str | None:
    """Return 'pressure_levels' / 'single_levels' for ERA5 NetCDF files, else None."""
    try:
        with xr.open_dataset(path, decode_times=False) as ds:
            names = set(ds.data_vars)
            if not ({"latitude", "longitude"} <= set(ds.coords) | set(ds.dims)):
                return None
            hist = " ".join(str(v) for v in ds.attrs.values()).lower()
            if not (names & set(SHORT) and ("ecmwf" in hist or "era5" in hist or "grib" in hist or names <= set(SHORT) | {"expver", "number"})):
                return None
            return "pressure_levels" if ({"pressure_level", "level", "isobaricInhPa"} & set(ds.dims)) else "single_levels"
    except Exception:
        return None


def find_era5_outputs() -> dict:
    """Search the places cdsapi may have written results. Zip results are listed, NetCDF members extracted once."""
    candidates: list[Path] = []
    for d, recursive in [(ERA5_RAW_DIR, True), (RAW_DIR, True), (API_DIR, False), (ROOT, False)]:
        if d.exists():
            it = d.rglob("*") if recursive else d.glob("*")
            candidates += [p for p in it if p.is_file() and p.suffix.lower() in {".nc", ".zip", ".grib", ".grib2", ".grb"}]
    found = {"single_levels": [], "pressure_levels": [], "grib_unsupported": [], "searched": [rel(ERA5_RAW_DIR), rel(RAW_DIR), rel(API_DIR), "."]}
    for p in sorted(set(candidates)):
        if p.suffix.lower() in {".grib", ".grib2", ".grb"}:
            found["grib_unsupported"].append(rel(p))
            continue
        if p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p) as z:
                members = [m for m in z.namelist() if m.endswith(".nc")]
                if not members:
                    continue
                dest = ERA5_RAW_DIR / "extracted" / p.stem
                for m in members:
                    if not (dest / m).exists():
                        z.extract(m, dest)
                    kind = _looks_like_era5(dest / m)
                    if kind:
                        found[kind].append(dest / m)
            continue
        kind = _looks_like_era5(p)
        if kind:
            found[kind].append(p)
    return found


# --------------------------------------------------------------------------- ERA5 processing
def _coord(ds, *names):
    for n in names:
        if n in ds.coords or n in ds.dims:
            return n
    return None


def validate_era5_coords(ds: xr.Dataset, product: str) -> dict:
    tname = _coord(ds, "valid_time", "time")
    lev = _coord(ds, "pressure_level", "level", "isobaricInhPa")
    lat, lon = ds["latitude"].values, ds["longitude"].values
    t = pd.DatetimeIndex(ds[tname].values) if tname else pd.DatetimeIndex([])
    diffs = pd.Series(t).diff().dropna()
    step_mode = diffs.mode().iloc[0] if len(diffs) else None
    gaps = diffs[diffs > step_mode] if step_mode is not None else diffs.iloc[0:0]
    out = {
        "time_coord": tname, "n_times": int(len(t)),
        "time_range": [str(t.min()), str(t.max())] if len(t) else None,
        "time_step": str(step_mode) if step_mode is not None else None,
        "time_duplicates": int(t.duplicated().sum()), "time_monotonic": bool(t.is_monotonic_increasing),
        "time_gaps": int(len(gaps)),
        "lat_range": [float(lat.min()), float(lat.max())], "lon_range": [float(lon.min()), float(lon.max())],
        "lat_order": "descending" if lat[0] > lat[-1] else "ascending",
        "lat_resolution": float(abs(np.diff(lat)).mean()) if lat.size > 1 else None,
        "lon_resolution": float(abs(np.diff(lon)).mean()) if lon.size > 1 else None,
        "lat_duplicates": int(lat.size - np.unique(lat).size), "lon_duplicates": int(lon.size - np.unique(lon).size),
        "lat_out_of_range": int(((lat < -90) | (lat > 90)).sum()),
        "level_coord": lev, "product_type_detected": "pressure_levels" if lev else "single_levels",
        "product_type_expected": product,
    }
    if lev:
        lv = ds[lev].values.astype(float)
        out.update({"levels_hPa": lv.tolist(), "level_duplicates": int(lv.size - np.unique(lv).size),
                    "levels_nonstandard": [x for x in lv.tolist() if x not in ERA5_STANDARD_LEVELS],
                    "level_order": "descending" if lv.size > 1 and lv[0] > lv[-1] else "ascending"})
    return out


def _var_stats(da: xr.DataArray, tname: str | None, block: int = 24) -> dict:
    """Streaming stats over time blocks so large files are never loaded at once."""
    short = da.name
    exp = SHORT.get(short)
    lo, hi = exp[2] if exp else (-np.inf, np.inf)
    n = nan = below = above = 0
    vmin, vmax, s, ss = np.inf, -np.inf, 0.0, 0.0
    nt = da.sizes.get(tname, 1) if tname else 1
    for i in range(0, nt, block):
        a = (da.isel({tname: slice(i, i + block)}) if tname and tname in da.dims else da).values.astype("float64")
        fin = np.isfinite(a)
        n += a.size; nan += int((~fin).sum())
        v = a[fin]
        if v.size:
            vmin, vmax = min(vmin, v.min()), max(vmax, v.max())
            s += v.sum(); ss += (v ** 2).sum()
            below += int((v < lo).sum()); above += int((v > hi).sum())
        if not (tname and tname in da.dims):
            break
    valid = n - nan
    mean = s / valid if valid else None
    return {"units": da.attrs.get("units"), "expected_units": exp[1] if exp else "unknown (not in reference table)",
            "units_match": (da.attrs.get("units") == exp[1]) if exp else None,
            "long_name": da.attrs.get("long_name"), "cells": n, "missing": nan, "missing_percent": round(100 * nan / n, 4) if n else None,
            "min": vmin if valid else None, "max": vmax if valid else None, "mean": mean,
            "std": float(np.sqrt(max(ss / valid - mean ** 2, 0))) if valid else None,
            "below_plausible": below, "above_plausible": above, "plausible_range": [lo, hi]}


def process_era5_file(path: Path, product: str) -> dict:
    did = "era5_pressure_levels" if product == "pressure_levels" else "era5_single_levels"
    rec = new_record(f"{did}__{path.stem}", f"ERA5 {product.replace('_', ' ')}: {path.name}", [path], f"reanalysis_{product}", "ECMWF / Copernicus C3S")
    out_dir = PROCESSED_DIR / "era5" / product
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        ds = xr.open_dataset(path)
        coords = validate_era5_coords(ds, product)
        rec["metrics"]["coordinates"] = coords
        rec["metrics"]["dimensions"] = {k: int(v) for k, v in ds.sizes.items()}
        step(rec, f"Opened lazily: dims {rec['metrics']['dimensions']}; time {coords['time_range']} step {coords['time_step']}")
        if coords["product_type_detected"] != product:
            issue(rec, "error", "product_mismatch", f"Expected {product} but file looks like {coords['product_type_detected']}", None)
        for k, kind in [("time_duplicates", "duplicate_timestamp"), ("time_gaps", "temporal_gap"), ("lat_duplicates", "duplicate_coordinate"),
                        ("level_duplicates", "duplicate_coordinate"), ("lat_out_of_range", "invalid_coordinate")]:
            if coords.get(k):
                issue(rec, "warning", kind, k, coords[k])
        if coords.get("levels_nonstandard"):
            issue(rec, "warning", "nonstandard_level", f"Levels not in ERA5 standard set: {coords['levels_nonstandard']}", len(coords["levels_nonstandard"]))
        tname = coords["time_coord"]
        stats = {}
        for v in ds.data_vars:
            if v in ("expver", "number") or ds[v].ndim < 2:
                continue
            stats[v] = _var_stats(ds[v], tname)
            if stats[v]["units_match"] is False:
                issue(rec, "warning", "unit_mismatch", f"{v}: units '{stats[v]['units']}' vs expected '{stats[v]['expected_units']}' (NOT converted)", None)
            nb = stats[v]["below_plausible"] + stats[v]["above_plausible"]
            if nb:
                issue(rec, "info", "suspicious_value", f"{v}: values outside plausible range {stats[v]['plausible_range']} (flagged, retained)", nb)
        rec["metrics"]["variables"] = stats
        tot = sum(s["cells"] for s in stats.values())
        rec["metrics"]["missing_count"] = sum(s["missing"] for s in stats.values())
        rec["metrics"]["missing_percent"] = round(100 * rec["metrics"]["missing_count"] / tot, 4) if tot else None
        rec["notes"].append("NaN in sst/siconc over land and cbh where no cloud base exists are expected ERA5 conventions, not data loss.")

        # Antarctic spatial subset (no regridding, native 0.25 deg grid and units preserved).
        lat = ds["latitude"]
        sub = ds.sel(latitude=lat[lat <= ANTARCTIC_LAT_LIMIT].values)
        enc = {v: {"zlib": True, "complevel": 4} for v in sub.data_vars}
        dst = out_dir / f"{path.stem}_antarctic_le60S.nc"
        sub.attrs["preprocessing_history"] = f"{utcnow()}: spatial subset latitude <= {ANTARCTIC_LAT_LIMIT} from {path.name}; no regridding/unit conversion"
        sub.to_netcdf(dst, encoding=enc)
        step(rec, f"Wrote Antarctic subset (lat <= {ANTARCTIC_LAT_LIMIT}) at native resolution to {rel(dst)}")
        # Area-weighted (cos latitude) Antarctic mean time series - documented derived product.
        w = np.cos(np.deg2rad(sub["latitude"]))
        ts = {}
        for v in stats:
            if tname in sub[v].dims:
                m = sub[v].weighted(w).mean(dim=["latitude", "longitude"], skipna=True)
                ts[v] = m.to_pandas()
        if ts:
            frames = []
            for v, s in ts.items():
                df = s.to_frame(v) if isinstance(s, pd.Series) else s.add_prefix(f"{v}_")
                frames.append(df)
            tsdf = pd.concat(frames, axis=1)
            tsdf.to_csv(out_dir / f"{path.stem}_antarctic_area_weighted_mean.csv")
            add_output(rec, out_dir / f"{path.stem}_antarctic_area_weighted_mean.csv", "csv",
                       "cos(latitude)-weighted spatial mean over lat<=-60 per time step (and level); original units")
        chk = xr.open_dataset(dst)
        rec["validation"] = {"output_reopened": True, "variables_preserved": set(stats) <= set(chk.data_vars),
                             "time_preserved": chk.sizes.get(tname) == ds.sizes.get(tname),
                             "latitudes_le_limit": bool((chk.latitude <= ANTARCTIC_LAT_LIMIT).all())}
        chk.close(); ds.close()
        add_output(rec, dst, "netcdf", "Antarctic subset, native grid, original units, zlib-compressed")
        return finish(rec, "processed" if all(rec["validation"].values()) else "partially_processed")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")


def process_api_sources() -> list[dict]:
    """Inspect both API scripts and process whatever outputs exist locally."""
    creds = credential_status()
    outputs = find_era5_outputs()
    recs = []
    for script, meta in API_SCRIPTS.items():
        path = API_DIR / script
        product = "pressure_levels" if meta["dataset_id"] == "era5_pressure_levels" else "single_levels"
        rec = new_record(meta["dataset_id"], meta["name"], [path], "api_request_and_outputs", "ECMWF / Copernicus Climate Change Service (CDS)")
        try:
            parsed = parse_api_script(path)
            est = estimate_request(parsed["request"])
            rec["metrics"]["script"] = {k: parsed[k] for k in ("script", "dataset", "imports", "calls", "executes_on_import", "output_target")}
            rec["metrics"]["request"] = parsed["request"]
            rec["metrics"]["request_estimate"] = est
            rec["metrics"]["credentials"] = creds
            rec["metrics"]["response_format"] = f"{parsed['request'].get('data_format')} ({parsed['request'].get('download_format')})"
            step(rec, f"Parsed {script} with ast (not executed): dataset '{parsed['dataset']}', {est['variables']} variables, "
                      f"{est['valid_dates']:,} valid dates x {est['times_per_day']} times x {est['pressure_levels']} level(s), area {est['area']}")
            step(rec, f"Estimated {est['fields']:,} fields ~ {est['uncompressed_float32_TB']} TB uncompressed float32")
            issue(rec, "info", "format_note", f"Script requests '{parsed['request'].get('data_format')}' output, i.e. NetCDF - not JSON", None)
            if est["invalid_calendar_dates_ignored"]:
                issue(rec, "info", "request_note", "Request lists non-existent calendar dates (e.g. 30 Feb); CDS ignores them", est["invalid_calendar_dates_ignored"])
            if est["dates_not_yet_available"]:
                issue(rec, "info", "request_note", "Requested dates later than the ERA5 publication horizon", est["dates_not_yet_available"])
            if not parsed["request"].get("area") or parsed["request"].get("area") == [90, -180, -90, 180]:
                issue(rec, "warning", "request_scope", "Request is GLOBAL; an Antarctic area [-60,-180,-90,180] would cut volume ~6x", None)
            if est["fields"] > 120_000:
                issue(rec, "warning", "request_size", "Request far exceeds typical CDS per-request limits and would need to be split "
                      "(e.g. per year/month); not executed by this pipeline", est["fields"])
            if parsed["executes_on_import"]:
                issue(rec, "info", "script_design", "Script runs client.retrieve() at module import (no __main__ guard); the pipeline "
                      "therefore parses it instead of importing it", None)
            if not (creds["cdsapi_installed"] and (creds["cdsapirc_present"] or creds["env_CDSAPI_KEY_set"])):
                issue(rec, "warning", "missing_credentials", "cdsapi not installed and/or no CDS credentials configured in this environment", None)
            files = outputs[product]
            rec["metrics"]["local_outputs_found"] = [rel(f) for f in files]
            rec["metrics"]["search_locations"] = outputs["searched"]
            if outputs["grib_unsupported"]:
                issue(rec, "warning", "unsupported_format", f"GRIB files found but cfgrib is not installed: {outputs['grib_unsupported']}", len(outputs["grib_unsupported"]))
            if not files:
                issue(rec, "error", "output_missing", f"No ERA5 {product.replace('_', '-')} output (NetCDF/zip) found in any search location; "
                      "nothing to preprocess. No JSON output is produced by this script.", None)
                rec["validation"] = {"script_parsed": True, "outputs_present": False}
                rec["metrics"]["records_before"] = 0
                rec["metrics"]["records_after"] = 0
                recs.append(finish(rec, "not_available"))
                continue
            sub = [process_era5_file(f, product) for f in files]
            rec["metrics"]["file_results"] = [{"file": s["source_files"][0], "status": s["status"]} for s in sub]
            for s in sub:
                rec["outputs"] += s["outputs"]
            n_ok = sum(s["status"] == "processed" for s in sub)
            rec["validation"] = {"script_parsed": True, "outputs_present": True, "all_files_processed": n_ok == len(sub)}
            recs.append(finish(rec, "processed" if n_ok == len(sub) else ("partially_processed" if n_ok else "failed")))
        except Exception as e:
            rec["errors"].append(f"{type(e).__name__}: {e}")
            recs.append(finish(rec, "failed"))
    return recs


# --------------------------------------------------------------------------- guarded retrieval (opt-in)
def retrieve_era5(script: str, years=None, months=None, area=ANTARCTIC_AREA, max_fields: int = 100_000,
                  dry_run: bool = True, retries: int = 3, backoff_s: float = 30.0) -> dict:
    """Reuse the request in an existing API script, restricted in space/time, with safety checks.

    Never overwrites an existing file. Returns a provenance dict; writes a sidecar JSON next to the download.
    """
    parsed = parse_api_script(API_DIR / script)
    req = dict(parsed["request"])
    if years:
        req["year"] = [str(y) for y in years]
    if months:
        req["month"] = [f"{int(m):02d}" for m in months]
    if area:
        req["area"] = list(area)
    est = estimate_request(req)
    prov = {"script": script, "dataset": parsed["dataset"], "request": req, "estimate": est, "dry_run": dry_run, "requested_utc": utcnow()}
    if est["fields"] > max_fields:
        prov["status"] = "refused_too_large"
        return prov
    if dry_run:
        prov["status"] = "dry_run"
        return prov
    creds = credential_status()
    if not creds["cdsapi_installed"]:
        prov["status"] = "failed_cdsapi_not_installed"
        return prov
    if not (creds["cdsapirc_present"] or creds["env_CDSAPI_KEY_set"]):
        prov["status"] = "failed_missing_credentials"
        return prov
    import cdsapi
    ERA5_RAW_DIR.mkdir(parents=True, exist_ok=True)
    tag = f"{API_SCRIPTS[script]['dataset_id']}_{req['year'][0]}-{req['year'][-1]}_{req['month'][0]}-{req['month'][-1]}"
    target = ERA5_RAW_DIR / f"{tag}.nc"
    if target.exists():
        prov["status"] = "skipped_exists"
        prov["target"] = rel(target)
        return prov
    for attempt in range(1, retries + 1):
        try:
            cdsapi.Client(timeout=600, retry_max=5).retrieve(parsed["dataset"], req).download(str(target))
            prov.update({"status": "downloaded", "target": rel(target), "attempts": attempt, "completed_utc": utcnow()})
            break
        except Exception as e:   # HTTP errors, rate limits (429), timeouts, malformed responses
            LOG.warning("CDS attempt %d failed: %s", attempt, type(e).__name__)
            prov.setdefault("errors", []).append(f"attempt {attempt}: {type(e).__name__}: {str(e)[:300]}")
            if attempt == retries:
                prov["status"] = "failed"
            else:
                time.sleep(backoff_s * attempt)
    write_json(prov, ERA5_RAW_DIR / f"{tag}.provenance.json")
    return prov


def main():
    ap = argparse.ArgumentParser(description="Guarded ERA5 retrieval reusing EXTERNAL APIs scripts (dry-run by default)")
    ap.add_argument("--script", choices=list(API_SCRIPTS), required=True)
    ap.add_argument("--years", nargs="+")
    ap.add_argument("--months", nargs="+")
    ap.add_argument("--max-fields", type=int, default=100_000)
    ap.add_argument("--execute", action="store_true", help="actually submit the CDS request")
    a = ap.parse_args()
    import json
    print(json.dumps(retrieve_era5(a.script, a.years, a.months, max_fields=a.max_fields, dry_run=not a.execute), indent=2, default=str))


if __name__ == "__main__":
    main()
