"""Chart-derived pixel labels for ML-03 (USNIC SIGRID-3 -> classes on each scene's EPSG:3031 400 m grid).

0 open water (CT 00/01/02) · 1 sea ice (CT lower bound >= 70 %, incl. 92 = 10/10 fast ice) · 2 uncertain/mixed (10-70 % and a
buffer around every water/ice boundary, for chart scale and the 0-3 day chart-scene time mismatch) · 255 invalid (land/ice shelf,
no SAR, outside chart polygons, unknown CT).

Labels are expert chart analyses at chart scale (km), not pixel-perfect truth; every metric computed against them is
"agreement with the USNIC chart" and is reported as such.
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
from scipy import ndimage

from .acquisition import chart_path
from .paths import INTERIM, load

WATER, ICE, UNCERTAIN, INVALID = 0, 1, 2, 255


def ct_class(ct) -> int:
    """SIGRID-3 total-concentration code -> class."""
    cfg = load("labels")
    s = str(ct).strip()
    if s in cfg["water_codes"]:
        return WATER
    if s in ("91", "92"):
        return ICE
    if not s.isdigit() or len(s) != 2 or s in ("98", "99"):              # -9 / 98 / 99: undetermined -> invalid
        return INVALID
    # single value 'a0' (a/10), range 'ab' (a/10..b/10) and 'a1' (a/10..10/10): the lower bound is always a/10
    return ICE if int(s[0]) * 10 >= cfg["ice_min_concentration_pct"] else UNCERTAIN


@lru_cache(maxsize=8)
def _chart(chart_date: str):
    import geopandas as gpd
    g = gpd.read_file(chart_path(chart_date))
    g = g.to_crs(load("sar_preprocessing")["grid"]["crs"])
    g["cls"] = g["CT"].map(ct_class).astype(int)
    return g


def rasterize_chart(chart_date: str, transform, shape) -> np.ndarray:
    from rasterio.features import rasterize
    from shapely.geometry import box
    x0, y1 = transform.c, transform.f
    bb = box(x0, y1 + transform.e * shape[0], x0 + transform.a * shape[1], y1)
    g = _chart(chart_date)
    g = g[g.intersects(bb)]
    if g.empty:
        return np.full(shape, INVALID, np.uint8)
    return rasterize(((geom, int(c)) for geom, c in zip(g.geometry, g["cls"])), out_shape=shape, transform=transform,
                     fill=INVALID, dtype="uint8")


def buffer_boundaries(lab: np.ndarray, buffer_px: int) -> np.ndarray:
    """Water/ice pixels within buffer_px of the other class (or of a mixed polygon) become UNCERTAIN."""
    out = lab.copy()
    if buffer_px <= 0:
        return out
    for c in (WATER, ICE):
        other = (lab != c) & (lab != INVALID)
        if not other.any():
            continue
        near = ndimage.distance_transform_edt(~other) <= buffer_px
        out[(lab == c) & near] = UNCERTAIN
    return out


def scene_labels(scene_id: str, chart_date: str, scene: dict, meta: dict) -> tuple[np.ndarray, dict]:
    from affine import Affine
    tr = Affine(*meta["transform"])
    raw = rasterize_chart(chart_date, tr, tuple(meta["shape"]))
    bpx = int(round(load("labels")["boundary_buffer_m"] / meta["resolution_m"]))
    lab = buffer_boundaries(raw, bpx)
    lab[~scene["valid"]] = INVALID
    n = {k: int((lab == v).sum()) for k, v in (("water", WATER), ("ice", ICE), ("uncertain", UNCERTAIN), ("invalid", INVALID))}
    info = {"scene_id": scene_id, "chart_date": chart_date, "boundary_buffer_px": bpx, "counts": n,
            "chart_coverage_of_valid_sar": float(((raw != INVALID) & scene["valid"]).sum() / max(scene["valid"].sum(), 1))}
    info["_raw"] = np.where(scene["valid"], raw, INVALID).astype(np.uint8)
    return lab, info


def save_labels(scene_id: str, lab: np.ndarray, info: dict):
    d = INTERIM / "labels"
    d.mkdir(parents=True, exist_ok=True)
    raw = info.pop("_raw")
    np.savez_compressed(d / f"{scene_id}.npz", label=lab, raw=raw)        # raw = unbuffered chart classes (for ice-edge metrics)
    (d / f"{scene_id}.json").write_text(json.dumps(info))


def load_labels(scene_id: str, raw: bool = False) -> np.ndarray:
    return np.load(INTERIM / "labels" / f"{scene_id}.npz")["raw" if raw else "label"]
