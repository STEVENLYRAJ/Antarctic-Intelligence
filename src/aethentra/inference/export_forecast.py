"""Export a forecast as CF-NetCDF (native grid) + JSON summary + GeoJSON ice edge."""
from __future__ import annotations

import json

import numpy as np
import xarray as xr

from ..config import OUTPUTS_DIR, load
from .prediction_schema import ForecastSummary

FORECAST_DIR = OUTPUTS_DIR / "forecasts"


def ice_edge_geojson(field: np.ndarray, ctx, level: float = 15.0, props: dict | None = None) -> dict:
    """15 % contour of a field on the native grid, transformed to lon/lat (EPSG:4326)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from pyproj import Transformer
    x, y = ctx.cube.grid["x"], ctx.cube.grid["y"]
    f = np.where(ctx.ocean, np.nan_to_num(field, nan=0.0), 100.0)   # land counts as 'not open water' -> no coastline contours
    fig = plt.figure()
    cs = plt.contour(x, y, f, levels=[level])
    plt.close(fig)
    tr = Transformer.from_crs(load("preprocessing")["grid"]["proj4"], "EPSG:4326", always_xy=True)
    lines = []
    for seg in cs.allsegs[0]:
        if len(seg) < 5:
            continue
        lon, lat = tr.transform(seg[:, 0], seg[:, 1])
        lines.append([[round(float(a), 4), round(float(b), 4)] for a, b in zip(lon, lat)])
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": lines},
                          "properties": {"contour_percent": level, **(props or {})}}]}


def export(summary: ForecastSummary, fields: dict, ctx) -> ForecastSummary:
    d = FORECAST_DIR / summary.forecast_id
    d.mkdir(parents=True, exist_ok=True)
    g = ctx.cube.grid
    pre = load("preprocessing")["grid"]
    attrs_sic = {"units": "percent", "valid_min": 0.0, "valid_max": 100.0, "grid_mapping": "crs", "coordinates": "lat lon"}
    dv = {}
    descr = {"sic_forecast": ("Forecast 7-day mean sea-ice concentration", "model_prediction"),
             "sic_persistence": ("Persistence reference: latest valid observed daily SIC", "observation_derived_reference"),
             "sic_climatology": ("Climatological 7-day mean SIC for the target window", "climatology_reference"),
             "sic_forecast_q10": ("Forecast 10th percentile (validated interval)", "model_prediction"),
             "sic_forecast_q90": ("Forecast 90th percentile (validated interval)", "model_prediction")}
    for k, v in fields.items():
        dv[k] = (("y", "x"), np.where(ctx.ocean, v, np.nan).astype(np.float32), {**attrs_sic, "long_name": descr[k][0], "data_type": descr[k][1]})
    dv["ocean_mask"] = (("y", "x"), ctx.ocean.astype(np.int8), {"long_name": "static ocean mask (1 = ocean)", "grid_mapping": "crs"})
    dv["cell_area"] = (("y", "x"), ctx.area.astype(np.float32), {"units": "km2", "long_name": "grid cell area", "grid_mapping": "crs"})
    ds = xr.Dataset(dv, coords={"x": ("x", g["x"], {"units": "m", "standard_name": "projection_x_coordinate"}),
                                "y": ("y", g["y"], {"units": "m", "standard_name": "projection_y_coordinate"}),
                                "lat": (("y", "x"), g["lat"].astype(np.float32), {"units": "degrees_north"}),
                                "lon": (("y", "x"), g["lon"].astype(np.float32), {"units": "degrees_east"})})
    ds["crs"] = xr.DataArray(np.int32(0), attrs={"grid_mapping_name": "polar_stereographic", "latitude_of_projection_origin": -90.0,
                                                 "standard_parallel": -70.0, "straight_vertical_longitude_from_pole": 0.0,
                                                 "semi_major_axis": 6378273.0, "semi_minor_axis": 6356889.449, "proj4text": pre["proj4"],
                                                 "srid": "urn:ogc:def:crs:EPSG::3412"})
    ds.attrs = {"title": "AETHENTRA weekly Antarctic sea-ice concentration forecast", "Conventions": "CF-1.8",
                "forecast_id": summary.forecast_id, "issue_date": str(summary.issue_date), "target_start": str(summary.target_start),
                "target_end": str(summary.target_end), "model_version": summary.model_version, "data_type": "model_prediction",
                "source": summary.provenance["sic_source"], "history": f"generated {summary.generated_utc.isoformat()}"}
    nc = d / f"{summary.forecast_id}.nc"
    ds.to_netcdf(nc, encoding={k: {"zlib": True, "complevel": 4} for k in fields})
    edge = ice_edge_geojson(fields["sic_forecast"], ctx, 15.0, {"data_type": "model_prediction", "forecast_id": summary.forecast_id,
                                                                 "target_start": str(summary.target_start), "target_end": str(summary.target_end)})
    (d / f"{summary.forecast_id}_ice_edge.geojson").write_text(json.dumps(edge))
    summary.files = {"netcdf": nc.name, "ice_edge_geojson": f"{summary.forecast_id}_ice_edge.geojson",
                     "summary_json": f"{summary.forecast_id}.json"}
    (d / f"{summary.forecast_id}.json").write_text(summary.model_dump_json(indent=2))
    return summary
