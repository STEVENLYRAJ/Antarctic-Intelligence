"""Handlers for sea-ice NetCDF products found in DATAS/.

* Copernicus Marine OMI Antarctic monthly sea-ice EXTENT (1-D time series, km^2)
* DMI-ASIP Antarctic SAR sea-ice CONCENTRATION mosaic (2-D polar-stereographic grid, %)
* NASA OIB Arctic form-drag coefficients (out-of-domain; validated only)

Extent and concentration are different quantities and are never mixed here.
"""
from __future__ import annotations

from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd
import xarray as xr

from .common import add_output, finish, issue, new_record, num_summary, rel, step
from .config import PROCESSED_DIR


# --------------------------------------------------------------------------- helpers
def monthly_continuity(times: pd.DatetimeIndex) -> dict:
    """Duplicates, ordering and missing months for a monthly time axis."""
    periods = times.to_period("M")
    dups = periods[periods.duplicated()].astype(str).tolist()
    full = pd.period_range(periods.min(), periods.max(), freq="M")
    missing = sorted(set(full.astype(str)) - set(periods.astype(str)))
    return {
        "n_timesteps": int(len(times)),
        "first": str(periods.min()), "last": str(periods.max()),
        "monotonic_increasing": bool(times.is_monotonic_increasing),
        "duplicate_months": dups,
        "expected_months": int(len(full)),
        "missing_months": missing,
    }


def linear_trend_per_decade(x_years: np.ndarray, y: np.ndarray) -> float | None:
    ok = np.isfinite(y)
    if ok.sum() < 3:
        return None
    slope = np.polyfit(x_years[ok], y[ok], 1)[0]
    return float(slope * 10.0)


# --------------------------------------------------------------------------- OMI extent
def process_omi_extent(path: Path, related: list[Path]) -> dict:
    rec = new_record("cmems_omi_si_extent", "Copernicus Marine OMI Antarctic monthly sea-ice extent",
                     [path, *related], "sea_ice_extent_timeseries",
                     "Copernicus Marine Service / EUMETSAT OSI SAF (MET Norway)")
    out_dir = PROCESSED_DIR / "sea_ice_extent"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        # Raw read to inspect fill values before CF masking.
        with netCDF4.Dataset(path) as nc:
            nc.set_auto_mask(False)
            raw_ext = nc["siextent"][:].astype("float64")
            fill = float(nc["siextent"].getncattr("_FillValue"))
            threshold = float(nc["sea_ice_area_fraction_threshold"][...])
            gattrs = {k: str(nc.getncattr(k)) for k in nc.ncattrs()}
            # clim_months_bounds has no units attribute (CF climatology bounds inherit the clim_months units),
            # so xarray does not decode it; decode explicitly.
            cb = pd.DatetimeIndex([str(d) for d in netCDF4.num2date(nc["clim_months_bounds"][:].ravel(), nc["clim_months"].units,
                                                                     only_use_cftime_datetimes=False)])
        step(rec, f"Opened {path.name} with netCDF4; global attributes: title='{gattrs.get('title')}', source='{gattrs.get('source')}'")
        n_fill = int((raw_ext == fill).sum())
        rec["metrics"]["fill_value"] = fill
        rec["metrics"]["fill_value_count"] = n_fill
        rec["metrics"]["extent_threshold_percent"] = threshold
        step(rec, f"Fill value {fill} occurs {n_fill} times in siextent; extent threshold variable = {threshold}% SIC")

        ds = xr.open_dataset(path)  # CF decoding: fill -> NaN, time -> datetime64
        times = pd.DatetimeIndex(ds["time"].values)
        tb = ds["time_bounds"].values
        ext = ds["siextent"].values.astype("float64")
        units = ds["siextent"].attrs.get("units")
        rec["metrics"]["dimensions"] = {k: int(v) for k, v in ds.sizes.items()}
        rec["metrics"]["variables"] = {v: {"dims": list(ds[v].dims), "units": ds[v].attrs.get("units"),
                                           "long_name": ds[v].attrs.get("long_name")} for v in ds.data_vars}
        rec["metrics"]["units"] = units
        cont = monthly_continuity(times)
        rec["metrics"]["time_continuity"] = cont
        step(rec, f"Time axis: {cont['n_timesteps']} months {cont['first']}..{cont['last']}, "
                  f"{len(cont['missing_months'])} missing months, {len(cont['duplicate_months'])} duplicates")
        if cont["missing_months"]:
            issue(rec, "warning", "temporal_gap", f"Missing months: {cont['missing_months']}", len(cont["missing_months"]))
        if cont["duplicate_months"]:
            issue(rec, "error", "duplicate_timestamp", f"Duplicate months: {cont['duplicate_months']}", len(cont["duplicate_months"]))

        bounds_ok = bool(np.all((tb[:, 0] <= times.values) & (times.values <= tb[:, 1])))
        rec["validation"]["time_within_bounds"] = bounds_ok
        step(rec, f"Checked each timestamp lies within its time_bounds: {bounds_ok}")

        n_nan = int(np.isnan(ext).sum())
        rec["metrics"]["missing_months_fill"] = [str(t.to_period("M")) for t in times[np.isnan(ext)]]
        if n_nan:
            issue(rec, "warning", "missing_value", f"siextent is _FillValue for {rec['metrics']['missing_months_fill']} "
                  "(retained as NaN; not interpolated)", n_nan)
        neg = int((ext < 0).sum())
        # Physical plausibility: Southern Ocean extent is ~2-21 million km^2; >40e6 km^2 is impossible.
        implausible = int((ext > 40e6).sum())
        rec["metrics"]["missing_count"] = n_nan
        rec["metrics"]["missing_percent"] = round(100 * n_nan / ext.size, 3)
        rec["metrics"]["negative_count"] = neg
        rec["metrics"]["implausible_gt_40e6_km2"] = implausible
        rec["metrics"]["siextent_summary_km2"] = num_summary(ext)
        if neg or implausible:
            issue(rec, "error", "invalid_value", f"{neg} negative and {implausible} implausibly large extents", neg + implausible)

        # Climatology check: recompute monthly means over the climatology bounds and compare.
        clim = ds["monthlyclimsiextent_mean"].values.astype("float64")
        clim_std = ds["monthlyclimsiextent_std"].values.astype("float64")
        clim_start, clim_end = cb.min(), cb.max()
        sel = (times >= clim_start) & (times <= clim_end)
        recomputed = pd.Series(ext[sel], index=times[sel]).groupby(times[sel].month).mean()
        diff_pct = (recomputed.values - clim) / clim * 100
        rec["metrics"]["climatology_period"] = [str(clim_start.date()), str(clim_end.date())]
        rec["metrics"]["climatology_recomputed_max_abs_diff_percent"] = float(np.nanmax(np.abs(diff_pct)))
        step(rec, f"Recomputed monthly climatology over {clim_start.date()}..{clim_end.date()}; "
                  f"max |difference| vs file climatology = {np.nanmax(np.abs(diff_pct)):.4f}%")

        # Flag (do not remove) statistical outliers relative to the monthly climatology.
        month_idx = times.month.values - 1
        z = (ext - clim[month_idx]) / clim_std[month_idx]
        outl = np.abs(z) > 3
        rec["metrics"]["outliers_abs_z_gt_3"] = int(np.nansum(outl))
        rec["metrics"]["outlier_months"] = [str(t.to_period("M")) for t in times[outl]]
        if outl.any():
            issue(rec, "info", "suspicious_but_valid", "Months with |z|>3 vs monthly climatology flagged for review (retained)", int(outl.sum()))

        df = pd.DataFrame({
            "time": times.strftime("%Y-%m-%d"),
            "time_bound_start": pd.DatetimeIndex(tb[:, 0]).strftime("%Y-%m-%d"),
            "time_bound_end": pd.DatetimeIndex(tb[:, 1]).strftime("%Y-%m-%d"),
            "year": times.year, "month": times.month,
            "siextent_km2": ext,
            "siextent_million_km2": ext / 1e6,
            "clim_mean_km2": clim[month_idx],
            "anomaly_km2": ext - clim[month_idx],
            "anomaly_zscore": z,
            "flag_missing": np.isnan(ext),
            "flag_outlier_abs_z_gt_3": outl,
        })
        csv = out_dir / "cmems_omi_si_extent_monthly.csv"
        df.to_csv(csv, index=False)
        clim_df = pd.DataFrame({"month": np.arange(1, 13), "clim_mean_km2": clim, "clim_std_km2": clim_std,
                                "recomputed_mean_km2": recomputed.values, "diff_percent": diff_pct})
        clim_csv = out_dir / "cmems_omi_si_extent_climatology.csv"
        clim_df.to_csv(clim_csv, index=False)
        step(rec, "Wrote tidy monthly table (original km^2 retained; derived million km^2, climatology anomaly and z-score added)")

        annual = df.groupby("year")["siextent_km2"].agg(["mean", "count"])
        annual = annual[annual["count"] == 12]
        rec["metrics"]["annual_mean_trend_million_km2_per_decade"] = linear_trend_per_decade(
            annual.index.values.astype(float), annual["mean"].values / 1e6)
        for m, name in [(2, "february_minimum"), (9, "september_maximum")]:
            s = df[df.month == m]
            rec["metrics"][f"{name}_trend_million_km2_per_decade"] = linear_trend_per_decade(
                s.year.values.astype(float), s.siextent_million_km2.values)
        rec["metrics"]["record_min"] = df.loc[df.siextent_km2.idxmin(), ["time", "siextent_km2"]].to_dict()
        rec["metrics"]["record_max"] = df.loc[df.siextent_km2.idxmax(), ["time", "siextent_km2"]].to_dict()
        ds.close()

        # Re-open and validate the outputs.
        chk = pd.read_csv(csv)
        rec["validation"].update({
            "output_reopened": True,
            "row_count_matches_source": bool(len(chk) == len(times)),
            "values_identical_to_source": bool(np.allclose(chk.siextent_km2.values, ext, equal_nan=True)),
            "required_columns_present": all(c in chk for c in ["time", "siextent_km2", "time_bound_start"]),
        })
        rec["metrics"]["records_before"] = int(len(times))
        rec["metrics"]["records_after"] = int(len(chk))
        rec["metrics"]["excluded_records"] = 0
        add_output(rec, csv, "csv", "Monthly sea-ice extent with bounds, anomaly and quality flags")
        add_output(rec, clim_csv, "csv", "Monthly climatology (file) vs recomputed climatology")
        ok = all(v for k, v in rec["validation"].items() if isinstance(v, bool))
        return finish(rec, "processed" if ok else "partially_processed")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")


# --------------------------------------------------------------------------- DMI-ASIP SIC
def process_dmi_asip_sic(path: Path, related: list[Path], row_chunk: int = 512) -> dict:
    rec = new_record("cmems_dmi_asip_sic",
                     "DMI-ASIP Antarctic SAR sea-ice concentration mosaic (CMEMS SEAICE_ANT_PHY_AUTO_L3_NRT_011_012)",
                     [path, *related], "sea_ice_concentration_grid", "Danish Meteorological Institute / Copernicus Marine Service")
    out_dir = PROCESSED_DIR / "sea_ice_concentration"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        nc = netCDF4.Dataset(path)
        nc.set_auto_mask(False)
        ny, nx = len(nc.dimensions["y"]), len(nc.dimensions["x"])
        nt = len(nc.dimensions["time"])
        gattrs = {k: str(nc.getncattr(k)) for k in nc.ncattrs()}
        rec["metrics"]["global_attributes"] = {k: gattrs[k] for k in ["title", "start_date", "stop_date", "product_status",
                                                                       "spatial_resolution_latitude", "institution"] if k in gattrs}
        rec["metrics"]["dimensions"] = {"time": nt, "y": ny, "x": nx}
        rec["metrics"]["crs_proj4"] = nc["crs"].getncattr("proj4_string")
        rec["metrics"]["variables"] = {v: {"dims": list(nc[v].dimensions), "dtype": str(nc[v].dtype),
                                           "units": getattr(nc[v], "units", None),
                                           "_FillValue": getattr(nc[v], "_FillValue", None)} for v in nc.variables}
        tvals = nc["time"][:]
        time = netCDF4.num2date(tvals, nc["time"].units, getattr(nc["time"], "calendar", "standard"))
        rec["metrics"]["time"] = [str(t) for t in time]
        step(rec, f"Opened grid {nt}x{ny}x{nx} (time,y,x); CRS {rec['metrics']['crs_proj4']}; time {rec['metrics']['time']}")

        x, y = nc["x"][:], nc["y"][:]
        dx, dy = np.diff(x), np.diff(y)
        rec["metrics"]["grid"] = {
            "x_range_m": [float(x.min()), float(x.max())], "y_range_m": [float(y.min()), float(y.max())],
            "dx_unique_m": sorted(set(np.round(dx, 3).tolist()))[:5], "dy_unique_m": sorted(set(np.round(dy, 3).tolist()))[:5],
            "x_monotonic": bool(np.all(dx > 0) or np.all(dx < 0)), "y_monotonic": bool(np.all(dy > 0) or np.all(dy < 0)),
            "x_duplicates": int(len(x) - len(np.unique(x))), "y_duplicates": int(len(y) - len(np.unique(y))),
        }
        step(rec, f"Grid spacing dx={rec['metrics']['grid']['dx_unique_m']} m, dy={rec['metrics']['grid']['dy_unique_m']} m; "
                  f"monotonic x/y = {rec['metrics']['grid']['x_monotonic']}/{rec['metrics']['grid']['y_monotonic']}")

        sic_fill = int(nc["ice_concentration"].getncattr("_FillValue"))
        conf_fill = int(nc["confidence"].getncattr("_FillValue"))
        acq_fill = float(nc["acq_time"].getncattr("_FillValue"))
        hist = np.zeros(256, dtype=np.int64)        # int8 value + 128
        conf_hist = np.zeros(256, dtype=np.int64)
        cls = dict(total=0, sic_fill=0, sic_zero=0, sic_ice=0, sic_invalid=0,
                   fill_with_acq=0, fill_without_acq=0, sic_valid_conf_missing=0, sic_fill_conf_present=0,
                   acq_valid=0, lat_out_of_range=0, lon_out_of_range=0, latlon_nan=0)
        acq_min, acq_max = np.inf, -np.inf
        lat_min, lat_max = np.inf, -np.inf
        conf_sum, conf_n = 0.0, 0
        for t in range(nt):
            for r0 in range(0, ny, row_chunk):
                r1 = min(ny, r0 + row_chunk)
                sic = nc["ice_concentration"][t, r0:r1, :].astype(np.int16)
                conf = nc["confidence"][t, r0:r1, :].astype(np.int16)
                acq = nc["acq_time"][t, r0:r1, :]
                lat = nc["lat"][r0:r1, :]
                lon = nc["lon"][r0:r1, :]
                hist += np.bincount((sic + 128).ravel(), minlength=256)
                conf_hist += np.bincount((conf + 128).ravel(), minlength=256)
                is_fill = sic == sic_fill
                valid = ~is_fill & (sic >= 0) & (sic <= 100)
                has_acq = (acq != acq_fill) & np.isfinite(acq)
                cls["total"] += sic.size
                cls["sic_fill"] += int(is_fill.sum())
                cls["sic_zero"] += int((valid & (sic == 0)).sum())
                cls["sic_ice"] += int((valid & (sic > 0)).sum())
                cls["sic_invalid"] += int((~is_fill & ~valid).sum())
                cls["fill_with_acq"] += int((is_fill & has_acq).sum())
                cls["fill_without_acq"] += int((is_fill & ~has_acq).sum())
                cls["sic_valid_conf_missing"] += int((valid & (conf == conf_fill)).sum())
                cls["sic_fill_conf_present"] += int((is_fill & (conf != conf_fill)).sum())
                cls["acq_valid"] += int(has_acq.sum())
                cv = conf[valid & (conf != conf_fill)]
                conf_sum += float(cv.sum()); conf_n += int(cv.size)
                if has_acq.any():
                    acq_min = min(acq_min, float(acq[has_acq].min())); acq_max = max(acq_max, float(acq[has_acq].max()))
                fin = np.isfinite(lat) & np.isfinite(lon)
                cls["latlon_nan"] += int((~fin).sum())
                cls["lat_out_of_range"] += int((fin & ((lat < -90) | (lat > 90))).sum())
                cls["lon_out_of_range"] += int((fin & ((lon < -180) | (lon > 180))).sum())
                lat_min = min(lat_min, float(np.nanmin(lat))); lat_max = max(lat_max, float(np.nanmax(lat)))
        nc.close()
        total = cls["total"]
        values = {int(v - 128): int(c) for v, c in enumerate(hist) if c}
        conf_values = {int(v - 128): int(c) for v, c in enumerate(conf_hist) if c}
        rec["metrics"]["cell_classes"] = cls
        rec["metrics"]["cell_class_percent"] = {k: round(100 * v / total, 4) for k, v in cls.items() if k != "total"}
        rec["metrics"]["sic_distinct_values"] = len(values)
        rec["metrics"]["sic_value_counts"] = values
        rec["metrics"]["confidence_value_counts"] = conf_values
        rec["metrics"]["confidence_mean_over_valid_sic"] = conf_sum / conf_n if conf_n else None
        rec["metrics"]["acq_time_range_utc"] = [str(pd.to_datetime(acq_min, unit="s", utc=True)),
                                                str(pd.to_datetime(acq_max, unit="s", utc=True))] if np.isfinite(acq_min) else None
        rec["metrics"]["lat_range"] = [lat_min, lat_max]
        rec["metrics"]["missing_count"] = cls["sic_fill"]
        rec["metrics"]["missing_percent"] = round(100 * cls["sic_fill"] / total, 3)
        step(rec, f"Scanned {total:,} cells in {row_chunk}-row chunks: valid zero={cls['sic_zero']:,}, ice>0={cls['sic_ice']:,}, "
                  f"fill={cls['sic_fill']:,}, invalid={cls['sic_invalid']:,}")
        step(rec, "Fill cells split heuristically by acq_time: fill WITH an acquisition time (inside SAR swath: land/ice-shelf mask or "
                  "unclassified) vs fill WITHOUT acquisition time (outside SAR coverage). The product has no explicit land-mask variable.")
        if cls["sic_invalid"]:
            issue(rec, "error", "invalid_value", "ice_concentration outside 0..100 % and not fill", cls["sic_invalid"])
        if cls["sic_valid_conf_missing"]:
            issue(rec, "warning", "inconsistent_quality_field", "Valid SIC without confidence value", cls["sic_valid_conf_missing"])
        if cls["sic_fill_conf_present"]:
            issue(rec, "info", "inconsistent_quality_field", "Fill SIC cells that still carry a confidence value", cls["sic_fill_conf_present"])
        issue(rec, "info", "no_land_mask", "Product has no separate land-mask flag; land and no-coverage are both _FillValue=-1", None)

        pd.DataFrame({"ice_concentration_percent": list(values.keys()), "cell_count": list(values.values())}) \
            .to_csv(out_dir / "dmi_asip_sic_value_histogram.csv", index=False)
        pd.DataFrame({"confidence_percent": list(conf_values.keys()), "cell_count": list(conf_values.values())}) \
            .to_csv(out_dir / "dmi_asip_confidence_histogram.csv", index=False)
        pd.DataFrame([{"class": k, "cells": v, "percent": round(100 * v / total, 4)} for k, v in cls.items() if k != "total"]) \
            .to_csv(out_dir / "dmi_asip_sic_cell_classes.csv", index=False)
        for f, d in [("dmi_asip_sic_value_histogram.csv", "Exact counts of every ice_concentration value (fill = -1)"),
                     ("dmi_asip_confidence_histogram.csv", "Exact counts of every confidence value (fill = -1)"),
                     ("dmi_asip_sic_cell_classes.csv", "Cell classification: valid zero / ice / fill / invalid")]:
            add_output(rec, out_dir / f, "csv", d)
        rec["notes"].append("Native NetCDF retained as the analysis-ready product (155 MB, CF-1.4 compliant grid); no regridded "
                            "or duplicated copy was written. Outputs are validation summaries only.")
        chk = pd.read_csv(out_dir / "dmi_asip_sic_value_histogram.csv")
        rec["validation"] = {
            "summaries_reopened": True,
            "histogram_total_equals_grid_cells": bool(int(chk.cell_count.sum()) == total == nt * ny * nx),
            "grid_regular": rec["metrics"]["grid"]["x_monotonic"] and rec["metrics"]["grid"]["y_monotonic"],
            "no_invalid_sic_values": cls["sic_invalid"] == 0,
            "coordinates_in_range": cls["lat_out_of_range"] == 0 and cls["lon_out_of_range"] == 0,
        }
        rec["metrics"]["records_before"] = f"{nt}x{ny}x{nx} cells"
        rec["metrics"]["records_after"] = "unchanged (validated in native format)"
        return finish(rec, "validated")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")


# --------------------------------------------------------------------------- OIB Arctic form drag
def process_oib_cda(path: Path) -> dict:
    rec = new_record("oib_arctic_form_drag", "NASA Operation IceBridge Arctic atmospheric form-drag coefficients",
                     [path], "sea_ice_derived_grid", "NASA GSFC (A. Petty)")
    try:
        ds = xr.open_dataset(path)
        lat, lon = ds["latitude"].values, ds["longitude"].values
        rec["metrics"]["dimensions"] = {k: int(v) for k, v in ds.sizes.items()}
        rec["metrics"]["global_attributes"] = {k: str(v)[:300] for k, v in ds.attrs.items()}
        rec["metrics"]["lat_range"] = [float(np.nanmin(lat)), float(np.nanmax(lat))]
        rec["metrics"]["lon_range"] = [float(np.nanmin(lon)), float(np.nanmax(lon))]
        rec["metrics"]["year"] = int(ds["year"].values)
        for v in ["Cda", "Cdafr"]:
            a = ds[v].values.astype("float64")
            rec["metrics"][v] = {"missing_count": int(np.isnan(a).sum()), "missing_percent": round(100 * np.isnan(a).mean(), 3),
                                 "negative_count": int((a < 0).sum()), "units": ds[v].attrs.get("units", "dimensionless (not stated)"),
                                 "summary": num_summary(a)}
        step(rec, f"Opened 2-D curvilinear grid {rec['metrics']['dimensions']}; latitude range {rec['metrics']['lat_range']}")
        rec["domain_relevance"] = "out_of_domain_arctic"
        issue(rec, "warning", "out_of_domain", "File covers the ARCTIC (OIB spring 2009 campaign, latitudes north of "
              f"{rec['metrics']['lat_range'][0]:.1f}N); not used in Antarctic outputs", None)
        issue(rec, "info", "missing_metadata", "No CRS/grid_mapping, no units attributes and no _FillValue declared", None)
        rec["validation"] = {"opened": True, "lat_lon_in_range": bool(np.nanmin(lat) >= -90 and np.nanmax(lat) <= 90)}
        rec["metrics"]["records_before"] = "x".join(str(v) for v in ds.sizes.values())
        rec["metrics"]["records_after"] = "not transformed (out of domain)"
        ds.close()
        return finish(rec, "validated")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")
