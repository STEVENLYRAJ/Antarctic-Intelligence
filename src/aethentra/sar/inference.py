"""ML-03 inference: Sentinel-1 scene -> sea-ice probability / class products, and weekly composites.

Acquisition products (EPSG:3031, 400 m): probability of sea ice, class (0 water, 1 ice, 2 uncertain, 255 invalid), and
binary ice / water / uncertain / invalid masks. "Uncertain" = probability within the band fixed in configs/ml03/evaluation.yaml
(not a calibrated confidence unless the reliability analysis says so).

Weekly composite (EPSG:3031, 2 km): for each cell, the number of acquisitions with a valid (non-uncertain) classification,
the number classifying it as ice, detection frequency = n_ice / n_valid, a weekly class (ice >= 2/3, water <= 1/3, otherwise
variable) and coverage = n_valid > 0. Cells never observed during the week stay unobserved - nothing is interpolated.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from functools import lru_cache

import numpy as np
import pandas as pd

from .features import scene_feature_maps
from .paths import MODELS, OUTPUTS, PROCESSED, load

LOG = logging.getLogger("aethentra.ml03.inference")
FINAL = MODELS / "final"
SEG_DIR = OUTPUTS / "segmentation"
WEEKLY_DIR = OUTPUTS / "weekly_maps"
UNCERTAIN_BAND = (0.35, 0.65)


@lru_cache(maxsize=1)
def bundle():
    from .training import load_model
    m = load_model(FINAL, "final_model")
    meta = json.loads((FINAL / "final_model.meta.json").read_text())
    slope = json.loads((PROCESSED / "tiles" / "tiles.json").read_text())["incidence_slope_db_per_deg"]
    return m, meta, slope


def validate_scene(meta: dict) -> list[str]:
    warn = []
    if meta.get("polarization") != "HH":
        raise ValueError(f"model expects HH; scene has {meta.get('polarization')}")
    if meta.get("mode") != "EW":
        warn.append(f"model trained on EW mode; scene is {meta.get('mode')}")
    if meta["valid_fraction"] < 0.02:
        warn.append("less than 2 % of the scene is valid ocean")
    return warn


def classify_scene(scene_id: str, write: bool = True) -> dict:
    from .acquisition import download_scene
    from .preprocessing import load_scene, process_scene
    download_scene(scene_id)
    process_scene(scene_id)
    scene, meta = load_scene(scene_id)
    warn = validate_scene(meta)
    model, mmeta, slope = bundle()
    F = scene_feature_maps(scene, meta, slope=slope, glcm=model.kind in ("random_forest", "xgboost"))
    prob = model.prob_map(F)
    ok = scene["valid"] & np.isfinite(prob)
    cls = np.full(prob.shape, 255, np.uint8)
    cls[ok & (prob >= 0.5)] = 1
    cls[ok & (prob < 0.5)] = 0
    cls[ok & (prob > UNCERTAIN_BAND[0]) & (prob < UNCERTAIN_BAND[1])] = 2
    res = {"scene_id": scene_id, "acquired": meta["acquired"], "prob": prob, "class": cls, "meta": meta, "warnings": warn,
           "model_version": mmeta.get("model_version"), "model_name": mmeta.get("selected_from")}
    if write:
        res["files"] = export_scene(res)
    return res


def _tif(path, arr, transform, crs, nodata, dtype):
    import rasterio
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype=dtype, crs=crs,
                       transform=transform, nodata=nodata, compress="deflate") as o:
        o.write(arr.astype(dtype), 1)


def export_scene(res: dict) -> dict:
    import xarray as xr
    from affine import Affine
    m = res["meta"]
    d = SEG_DIR / res["scene_id"]
    d.mkdir(parents=True, exist_ok=True)
    tr, crs = Affine(*m["transform"]), m["crs"]
    p = np.where(np.isfinite(res["prob"]), res["prob"], -1).astype(np.float32)
    c = res["class"]
    files = {"probability_tif": "sea_ice_probability.tif", "class_tif": "sea_ice_class.tif", "netcdf": "segmentation.nc", "metadata": "metadata.json"}
    _tif(d / files["probability_tif"], p, tr, crs, -1, "float32")
    _tif(d / files["class_tif"], c, tr, crs, 255, "uint8")
    h, w = c.shape
    x = tr.c + tr.a * (np.arange(w) + 0.5)
    y = tr.f + tr.e * (np.arange(h) + 0.5)
    ds = xr.Dataset({"sea_ice_probability": (("y", "x"), np.where(p < 0, np.nan, p), {"units": "1", "data_type": "model_prediction",
                                                                                       "note": "model output; not a calibrated confidence"}),
                     "sea_ice_class": (("y", "x"), c, {"flag_values": [0, 1, 2, 255], "flag_meanings": "open_water sea_ice uncertain invalid"}),
                     "sea_ice_mask": (("y", "x"), (c == 1).astype(np.uint8)), "open_water_mask": (("y", "x"), (c == 0).astype(np.uint8)),
                     "uncertain_mask": (("y", "x"), (c == 2).astype(np.uint8)), "invalid_mask": (("y", "x"), (c == 255).astype(np.uint8))},
                    coords={"x": ("x", x, {"units": "m"}), "y": ("y", y, {"units": "m"})},
                    attrs={"title": "AETHENTRA ML-03 Sentinel-1 sea-ice segmentation", "Conventions": "CF-1.8", "crs": crs,
                           "scene_id": res["scene_id"], "acquired": res["acquired"], "model_version": res["model_version"] or "",
                           "data_type": "model_prediction", "source": "Copernicus Sentinel-1 EW GRDM HH (ESA), via Microsoft Planetary Computer"})
    ds.to_netcdf(d / files["netcdf"], encoding={k: {"zlib": True} for k in ds.data_vars})
    area = (m["resolution_m"] ** 2) / 1e6
    md = {"scene_id": res["scene_id"], "acquired": res["acquired"], "processed_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
          "data_type": "model_prediction", "sensor": "Sentinel-1 C-SAR", "mode": m["mode"], "polarization": m["polarization"],
          "resolution_m": m["resolution_m"], "crs": crs, "model_version": res["model_version"], "model_name": res["model_name"],
          "uncertain_probability_band": list(UNCERTAIN_BAND), "warnings": res["warnings"],
          "pixel_counts": {k: int((c == v).sum()) for k, v in (("water", 0), ("ice", 1), ("uncertain", 2), ("invalid", 255))},
          "nominal_ice_area_km2": float((c == 1).sum() * area), "processing": m["processing"], "files": files}
    (d / files["metadata"]).write_text(json.dumps(md, indent=1))
    return files


# ---------------------------------------------------------------------------------------------------- weekly composite
def weekly_grid():
    from rasterio.transform import from_origin
    r = load("sar_preprocessing")["grid"]["weekly_resolution_m"]
    ext = 4_000_000
    return from_origin(-ext, ext, r, r), (2 * ext // r, 2 * ext // r)


def composite(scene_results: list[dict], week_start: str) -> dict:
    """Aggregate acquisition classes onto the 2 km weekly grid (per acquisition: cell = majority of its valid 400 m pixels)."""
    from affine import Affine
    gtr, shape = weekly_grid()
    n_valid = np.zeros(shape, np.uint16)
    n_ice = np.zeros(shape, np.uint16)
    used = []
    for r in scene_results:
        m, c = r["meta"], r["class"]
        tr = Affine(*m["transform"])
        rows, cols = np.nonzero(np.isin(c, (0, 1)))
        if rows.size == 0:
            continue
        x = tr.c + tr.a * (cols + 0.5)
        y = tr.f + tr.e * (rows + 0.5)
        gi = ((gtr.f - y) / -gtr.e).astype(int)
        gj = ((x - gtr.c) / gtr.a).astype(int)
        key = gi * shape[1] + gj
        ice = (c[rows, cols] == 1).astype(np.int64)
        u, inv = np.unique(key, return_inverse=True)
        cnt = np.bincount(inv)
        ice_cnt = np.bincount(inv, ice)
        keep = cnt >= 13                                  # >= half of the 25 pixels of a 2 km cell classified
        ui, uj = np.divmod(u[keep], shape[1])
        n_valid[ui, uj] += 1
        n_ice[ui, uj] += (ice_cnt[keep] / cnt[keep] >= 0.5).astype(np.uint16)
        used.append(r["scene_id"])
    freq = np.where(n_valid > 0, n_ice / np.maximum(n_valid, 1), np.nan).astype(np.float32)
    wcls = np.full(shape, 255, np.uint8)
    wcls[(n_valid > 0) & (freq >= 2 / 3)] = 1
    wcls[(n_valid > 0) & (freq <= 1 / 3)] = 0
    wcls[(n_valid > 0) & (freq > 1 / 3) & (freq < 2 / 3)] = 2
    return {"week_start": week_start, "n_valid": n_valid, "n_ice": n_ice, "frequency": freq, "class": wcls, "transform": gtr,
            "scenes": used}


def export_weekly(wk: dict, model_version: str) -> dict:
    d = WEEKLY_DIR / f"week_{wk['week_start']}"
    ld = d / "layers"
    ld.mkdir(parents=True, exist_ok=True)
    crs = load("sar_preprocessing")["grid"]["crs"]
    tr = wk["transform"]
    _tif(ld / "detection_frequency.tif", np.nan_to_num(wk["frequency"], nan=-1), tr, crs, -1, "float32")
    _tif(ld / "valid_acquisitions.tif", np.where(wk["n_valid"] > 0, wk["n_valid"], 0), tr, crs, 0, "uint16")
    _tif(ld / "ice_detections.tif", wk["n_ice"], tr, crs, None, "uint16")
    _tif(ld / "weekly_class.tif", wk["class"], tr, crs, 255, "uint8")
    cell_km2 = (tr.a / 1000) ** 2
    observed = int((wk["n_valid"] > 0).sum())
    md = {"week_start": wk["week_start"], "week_end": str((pd.Timestamp(wk["week_start"]) + pd.Timedelta(days=6)).date()),
          "data_type": "weekly composite of model predictions", "grid": f"{crs} {int(tr.a)} m", "n_acquisitions": len(wk["scenes"]),
          "acquisitions": wk["scenes"], "observed_cells": observed, "observed_area_km2_nominal": observed * cell_km2,
          "cells_weekly_ice": int((wk["class"] == 1).sum()), "cells_weekly_water": int((wk["class"] == 0).sum()),
          "cells_variable": int((wk["class"] == 2).sum()), "model_version": model_version,
          "methodology": "per acquisition, a 2 km cell is classified when >= 13 of its 25 pixels are water/ice (majority vote); "
                         "frequency = ice classifications / valid acquisitions; weekly class: ice >= 2/3, water <= 1/3, else variable. "
                         "Cells without a valid acquisition are unobserved (no interpolation; coverage is incomplete).",
          "files": ["detection_frequency.tif", "valid_acquisitions.tif", "ice_detections.tif", "weekly_class.tif"]}
    (d / "metadata.json").write_text(json.dumps(md, indent=1))
    period = f"{md['week_start']}..{md['week_end']}"
    layers = [("detection_frequency", "Weekly ice detection frequency (fraction of valid acquisitions)", "weekly composite of model predictions", "1"),
              ("weekly_class", "Weekly class: 0 water, 1 ice, 2 variable", "weekly composite of model predictions", "class"),
              ("valid_acquisitions", "Observation coverage: valid acquisitions per 2 km cell", "observation coverage", "count")]
    (ld / "manifest.json").write_text(json.dumps({"forecast_id": d.name, "issue_date": md["week_start"], "model_version": model_version,
        "source": "Copernicus Sentinel-1 EW GRDM HH (ESA) via Microsoft Planetary Computer; AETHENTRA ML-03 model",
        "limitations": ["Composite of the acquisitions of this week only; grey cells were not observed.",
                        "Detection frequency is not an ice concentration.", "Labels used for training are chart-scale (USNIC)."],
        "layers": [{"id": i, "title": t, "data_type": dt_, "units": u, "period": period, "geotiff": f"{i}.tif"} for i, t, dt_, u in layers]}, indent=1))
    return md
