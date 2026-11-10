"""Export AETHENTRA frontend data layers (CesiumJS / Next.js) for one forecast.

outputs/forecasts/<forecast_id>/layers/
  manifest.json                      every layer with data_type, units, period, source, model version, limitations
  observed_latest_week_sic_3412.tif  observation (past 7-day mean ending at issue date), native grid
  forecast_sic_3412.tif              model prediction, native grid
  *_4326.png + bounds in manifest     display overlays reprojected to EPSG:4326 (lon -180..180, lat -90..-39) for Cesium
  ice_edge_observed.geojson / ice_edge_forecast.geojson   15 % contours (EPSG:4326)
  extent_timeseries.json             historical weekly observed extent + test-period forecast/observed/persistence
  regional_summary.json              sector extent/area of the forecast vs persistence
  test_error_mae_3412.tif            evaluation layer: per-cell test MAE of the final model
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject

from ..config import EXPERIMENTS_DIR, load
from ..inference.export_forecast import FORECAST_DIR, ice_edge_geojson
from .style import BLUE_CMAP

TRANSFORM = Affine(25000, 0, -3950000, 0, -25000, 4350000)
DST_RES = 0.25
DST_BOUNDS = (-180.0, -90.0, 180.0, -39.0)


def _tif(path, arr, nodata=-9999.0):
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype="float32",
                       crs="EPSG:3412", transform=TRANSFORM, nodata=nodata, compress="deflate") as d:
        d.write(np.where(np.isfinite(arr), arr, nodata).astype(np.float32), 1)


def _png_4326(path, arr, vmin=0, vmax=100, cmap=BLUE_CMAP, resampling=Resampling.nearest):
    w = int((DST_BOUNDS[2] - DST_BOUNDS[0]) / DST_RES); h = int((DST_BOUNDS[3] - DST_BOUNDS[1]) / DST_RES)
    dst = np.full((h, w), np.nan, np.float32)
    dt = Affine(DST_RES, 0, DST_BOUNDS[0], 0, -DST_RES, DST_BOUNDS[3])
    reproject(np.where(np.isfinite(arr), arr, np.nan).astype(np.float32), dst, src_transform=TRANSFORM, src_crs="EPSG:3412",
              dst_transform=dt, dst_crs="EPSG:4326", resampling=resampling, src_nodata=np.nan, dst_nodata=np.nan)
    rgba = (cmap(np.clip((dst - vmin) / (vmax - vmin), 0, 1)) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(np.isfinite(dst), 220, 0)
    from PIL import Image
    Image.fromarray(rgba, "RGBA").save(path)
    return {"west": DST_BOUNDS[0], "south": DST_BOUNDS[1], "east": DST_BOUNDS[2], "north": DST_BOUNDS[3], "crs": "EPSG:4326",
            "resampling": "nearest (display only)"}


def export_layers(summary, fields: dict, ctx) -> dict:
    d = FORECAST_DIR / summary.forecast_id / "layers"
    d.mkdir(parents=True, exist_ok=True)
    t = pd.Timestamp(summary.issue_date)
    F = ctx.features(t)
    obs_week = np.where(ctx.ocean, F["sic_w1"], np.nan)
    fc = fields["sic_forecast"]
    common = {"model_version": summary.model_version, "units": "percent", "source": summary.provenance["sic_source"],
              "limitations": summary.limitations}
    layers = []
    _tif(d / "observed_latest_week_sic_3412.tif", obs_week)
    b = _png_4326(d / "observed_latest_week_sic_4326.png", obs_week)
    layers.append({"id": "observed_latest_week", "data_type": "observation", "title": "Observed sea-ice concentration (7-day mean)",
                   "period": [str((t - pd.Timedelta(days=6)).date()), str(t.date())], "files": ["observed_latest_week_sic_3412.tif",
                   "observed_latest_week_sic_4326.png"], "bounds_4326": b, "units": "percent", "source": common["source"]})
    _tif(d / "forecast_sic_3412.tif", fc)
    b = _png_4326(d / "forecast_sic_4326.png", fc)
    layers.append({"id": "forecast_7day_mean", "data_type": "model_prediction", "title": "FORECAST 7-day mean sea-ice concentration",
                   "issue_date": str(summary.issue_date), "period": [str(summary.target_start), str(summary.target_end)],
                   "files": ["forecast_sic_3412.tif", "forecast_sic_4326.png"], "bounds_4326": b, **common,
                   "uncertainty": summary.uncertainty.model_dump()})
    for nm, f, dtp in [("ice_edge_observed", obs_week, "observation"), ("ice_edge_forecast", fc, "model_prediction")]:
        (d / f"{nm}.geojson").write_text(json.dumps(ice_edge_geojson(f, ctx, 15.0, {"data_type": dtp})))
        layers.append({"id": nm, "data_type": dtp, "title": f"15 % ice edge ({dtp.replace('_', ' ')})", "files": [f"{nm}.geojson"],
                       "crs": "EPSG:4326"})
    # extent time series
    cal = ctx.cube.calendar
    wk = cal[cal.present].set_index("date").extent_mkm2.resample("7D").mean().dropna()
    ts = {"historical_observed_weekly_extent_mkm2": {"data_type": "observation", "dates": [str(x.date()) for x in wk.index],
                                                     "values": [round(float(v), 4) for v in wk.values]}}
    per = EXPERIMENTS_DIR / "metrics" / "test_final" / "per_date_sums.parquet"
    if per.exists():
        p = pd.read_parquet(per)
        p = p[p.group == "all"].pivot_table(index="issue_date", columns="method", values=["ext_obs", "ext_pred"])
        ts["test_period"] = {"data_type": "evaluation", "issue_dates": [str(x.date()) for x in p.index],
                             "observed_mkm2": (p[("ext_obs", "final_model")] / 1e6).round(4).tolist(),
                             "forecast_mkm2": (p[("ext_pred", "final_model")] / 1e6).round(4).tolist(),
                             "persistence_mkm2": (p[("ext_pred", "persistence")] / 1e6).round(4).tolist()}
    ts["latest_forecast"] = {"data_type": "model_prediction", "issue_date": str(summary.issue_date),
                             "target_period": [str(summary.target_start), str(summary.target_end)], "extent_mkm2": summary.extent_km2 / 1e6}
    (d / "extent_timeseries.json").write_text(json.dumps(ts))
    layers.append({"id": "extent_timeseries", "data_type": "mixed (each series labelled)", "files": ["extent_timeseries.json"], "units": "10^6 km2"})
    (d / "regional_summary.json").write_text(json.dumps({"data_type": "model_prediction", "issue_date": str(summary.issue_date),
                                                         "sectors": [s.model_dump() for s in summary.sectors]}, indent=2))
    layers.append({"id": "regional_summary", "data_type": "model_prediction", "files": ["regional_summary.json"], "units": "km2"})
    em = EXPERIMENTS_DIR / "metrics" / "test_final" / "error_maps.npz"
    if em.exists():
        e = np.where(ctx.ocean, np.load(em)["mae_final_model"], np.nan)
        _tif(d / "test_error_mae_3412.tif", e)
        b = _png_4326(d / "test_error_mae_4326.png", e, 0, float(np.nanpercentile(e, 99)))
        layers.append({"id": "test_spatial_error", "data_type": "evaluation", "title": "Final-model MAE per cell, test 2021-2025",
                       "files": ["test_error_mae_3412.tif", "test_error_mae_4326.png"], "bounds_4326": b, "units": "percentage points"})
    man = {"forecast_id": summary.forecast_id, "issue_date": str(summary.issue_date), "issue_time_utc": summary.issue_time_utc.isoformat(),
           "target_period": [str(summary.target_start), str(summary.target_end)], "model_version": summary.model_version,
           "display_rules": ["Always label data_type; never present model_prediction layers as observations.",
                             "Show issue time, target period, model version and source with every forecast layer.",
                             "Show uncertainty only when uncertainty.validated is true."],
           "native_crs": "EPSG:3412 (NSIDC Sea Ice Polar Stereographic South, 25 km)", "layers": layers}
    (d / "manifest.json").write_text(json.dumps(man, indent=2))
    return man
