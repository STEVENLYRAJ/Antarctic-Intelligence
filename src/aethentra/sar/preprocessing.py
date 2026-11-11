"""Sentinel-1 GRD preprocessing for ML-03 (applied identically in training and inference).

1. DN (HH, x8 COG overview) -> sigma0 with the product's own calibration LUT, after subtracting thermal noise
   (noiseRangeVector x noiseAzimuthVector, IPF >= 2.9 layout; range-only for older products).
2. Incidence angle from the same LUT: sigma0 = beta0 * sin(theta)  =>  sin(theta) = A_beta^2 / A_sigma^2.
3. Geocoding with the product GCPs (EPSG:4326) to EPSG:3031 at 400 m (bilinear on linear sigma0, then dB).
4. Land / ice-shelf mask (Natural Earth 10 m + 2 km buffer) and invalid pixels (no data, incidence outside range).

Overview pixels map to full-resolution line/pixel coordinates by the stored size ratio; LUTs are interpolated there. The COG
overview averages DN (not DN^2); the resulting small, near-constant power bias is identical for every scene and documented.
"""
from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

import numpy as np

from .paths import INTERIM, RAW_AUX, RAW_S1, load

LOG = logging.getLogger("aethentra.ml03.preprocessing")
NODATA = -9999.0


def _floats(e, tag):
    return np.array(e.find(tag).text.split(), float)


def _grid_interp(lines, pixels_list, values_list, L, P) -> np.ndarray:
    """LUT given on (line, pixel) vectors -> values at the full-resolution coordinates L (rows) x P (cols)."""
    # separable bilinear: each vector along pixels, then linear along lines (equivalent to bilinear on the LUT grid)
    rows = np.stack([np.interp(P, p, v) for p, v in zip(pixels_list, values_list)])         # (n_vectors, w)
    Lc = np.clip(L, lines[0], lines[-1])
    i = np.clip(np.searchsorted(lines, Lc) - 1, 0, len(lines) - 2)
    t = ((Lc - lines[i]) / np.maximum(lines[i + 1] - lines[i], 1e-9))[:, None]
    return rows[i] * (1 - t) + rows[i + 1] * t


def calibration_luts(xml: Path, L, P) -> tuple[np.ndarray, np.ndarray]:
    root = ET.parse(xml).getroot()
    vecs = root.findall(".//calibrationVector")
    lines = np.array([int(v.find("line").text) for v in vecs], float)
    pix = [_floats(v, "pixel") for v in vecs]
    sig = _grid_interp(lines, pix, [_floats(v, "sigmaNought") for v in vecs], L, P)
    bet = _grid_interp(lines, pix, [_floats(v, "betaNought") for v in vecs], L, P)
    return sig, bet


def noise_lut(xml: Path, L, P) -> np.ndarray:
    root = ET.parse(xml).getroot()
    rv = root.findall(".//noiseRangeVector") or root.findall(".//noiseVector")
    key = "noiseRangeLut" if rv and rv[0].find("noiseRangeLut") is not None else "noiseLut"
    lines = np.array([int(v.find("line").text) for v in rv], float)
    rng = _grid_interp(lines, [_floats(v, "pixel") for v in rv], [_floats(v, key) for v in rv], L, P)
    az = np.ones_like(rng)
    for b in root.findall(".//noiseAzimuthVector"):
        l0, l1 = int(b.find("firstAzimuthLine").text), int(b.find("lastAzimuthLine").text)
        p0, p1 = int(b.find("firstRangeSample").text), int(b.find("lastRangeSample").text)
        bl, bv = _floats(b, "line"), _floats(b, "noiseAzimuthLut")
        ri = (L >= l0) & (L <= l1)
        ci = (P >= p0) & (P <= p1)
        if ri.any() and ci.any():
            col = np.interp(L[ri], bl, bv) if len(bl) > 1 else np.full(ri.sum(), bv[0])
            az[np.ix_(ri, ci)] = col[:, None]
    return rng * az


@lru_cache(maxsize=1)
def _land_geoms():
    import geopandas as gpd
    from shapely.ops import unary_union
    cfg = load("sar_preprocessing")
    parts = []
    for name in ("ne_10m_land", "ne_10m_antarctic_ice_shelves_polys"):
        g = gpd.read_file(next((RAW_AUX / name).glob("*.shp")))
        g = g.cx[:, :-45].to_crs(cfg["grid"]["crs"])
        parts.append(g.geometry)
    geom = unary_union([x for p in parts for x in p]).buffer(cfg["land_mask"]["buffer_m"])
    return geom


LAND_EXTENT = 4_000_000          # m; the land raster covers [-4000, 4000] km in EPSG:3031 (everything south of ~50S)


def land_raster_path():
    return INTERIM / f"land_mask_{int(load('sar_preprocessing')['grid']['resolution_m'])}m.npy"


def build_land_raster() -> str:
    """Rasterise the buffered land + ice-shelf geometry ONCE onto the full EPSG:3031 lattice (memory-mapped uint8).
    Scene grids are snapped to the same lattice, so land_mask() is a plain array slice (cheap, no per-process geometry)."""
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    p = land_raster_path()
    if p.exists():
        return str(p)
    res = load("sar_preprocessing")["grid"]["resolution_m"]
    n = int(2 * LAND_EXTENT / res)
    arr = np.lib.format.open_memmap(p.with_suffix(".part.npy"), "w+", np.uint8, (n, n))
    geom = _land_geoms()
    step = 2000                                                       # rasterise in row blocks to bound memory
    for i in range(0, n, step):
        tr = from_origin(-LAND_EXTENT, LAND_EXTENT - i * res, res, res)
        h = min(step, n - i)
        arr[i:i + h] = rasterize([(geom, 1)], out_shape=(h, n), transform=tr, fill=0, dtype="uint8")
    arr.flush(); del arr
    p.with_suffix(".part.npy").replace(p)
    return str(p)


@lru_cache(maxsize=1)
def _land_raster():
    return np.load(land_raster_path(), mmap_mode="r")


def land_mask(transform, shape) -> np.ndarray:
    res = load("sar_preprocessing")["grid"]["resolution_m"]
    lr = _land_raster()
    i0 = int(round((LAND_EXTENT - transform.f) / res))
    j0 = int(round((transform.c + LAND_EXTENT) / res))
    out = np.zeros(shape, bool)
    a0, b0 = max(i0, 0), max(j0, 0)
    a1, b1 = min(i0 + shape[0], lr.shape[0]), min(j0 + shape[1], lr.shape[1])
    if a1 > a0 and b1 > b0:
        out[a0 - i0:a1 - i0, b0 - j0:b1 - j0] = np.asarray(lr[a0:a1, b0:b1]) > 0
    return out


def _bounds(transform, shape):
    x0, y1 = transform.c, transform.f
    return x0, y1 + transform.e * shape[0], x0 + transform.a * shape[1], y1


def target_grid(geometry: dict, res: float):
    """Snapped EPSG:3031 grid covering the scene footprint."""
    from pyproj import Transformer
    from rasterio.transform import from_origin
    tr = Transformer.from_crs("EPSG:4326", load("sar_preprocessing")["grid"]["crs"], always_xy=True)
    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    xs, ys = [], []
    for p in polys:
        if not p or not len(p[0]):
            continue
        c = np.asarray(p[0], float)
        k = np.linspace(0, len(c) - 1, 50 * len(c))                                            # densify edges
        lon = np.degrees(np.interp(k, np.arange(len(c)), np.unwrap(np.radians(c[:, 0]))))
        x, y = tr.transform(lon, np.interp(k, np.arange(len(c)), c[:, 1]))
        xs.append(x); ys.append(y)
    x, y = np.concatenate(xs), np.concatenate(ys)
    x0, x1 = np.floor(min(x) / res) * res - res, np.ceil(max(x) / res) * res + res
    y0, y1 = np.floor(min(y) / res) * res - res, np.ceil(max(y) / res) * res + res
    return from_origin(x0, y1, res, res), (int(round((y1 - y0) / res)), int(round((x1 - x0) / res)))


def process_scene(scene_id: str, overwrite: bool = False) -> dict:
    """Raw overview + annotations -> interim EPSG:3031 stack (sigma0_db, incidence_deg, valid, land) + metadata."""
    import rasterio
    from rasterio.warp import Resampling, reproject
    cfg = load("sar_preprocessing")
    out = INTERIM / "scenes" / f"{scene_id}.npz"
    meta_p = out.with_suffix(".json")
    if meta_p.exists() and not overwrite:
        return json.loads(meta_p.read_text())
    d = RAW_S1 / scene_id
    prov = json.loads((d / "provenance.json").read_text())
    pol = prov["polarizations"][0].lower() if "HH" not in prov["polarizations"] else "hh"
    with rasterio.open(d / f"{pol}_ov{prov['overview_factor']}.tif") as r:
        dn = r.read(1).astype(np.float64)
        gcps, gcrs = r.gcps
    h, w = dn.shape
    H, W = prov["full_size"]
    L = (np.arange(h) + 0.5) * H / h - 0.5
    P = (np.arange(w) + 0.5) * W / w - 0.5
    a_sig, a_bet = calibration_luts(d / f"schema-calibration-{pol}.xml", L, P)
    nz = noise_lut(d / f"schema-noise-{pol}.xml", L, P) if cfg["thermal_noise_removal"] else 0.0
    valid = dn > 0
    floor = 10 ** (cfg["noise_floor_db"] / 10)
    s0 = np.where(valid, np.maximum((dn ** 2 - nz) / a_sig ** 2, floor), np.nan)
    inc = np.degrees(np.arcsin(np.clip(a_bet ** 2 / a_sig ** 2, 0, 1)))
    res = cfg["grid"]["resolution_m"]
    transform, shape = target_grid(prov["geometry"], res)
    dst = {}
    for name, arr in (("s0", s0), ("inc", inc), ("valid", valid.astype(np.float32))):
        o = np.full(shape, np.nan, np.float32)
        reproject(arr.astype(np.float32), o, gcps=gcps, src_crs=gcrs, src_nodata=np.nan, dst_transform=transform,
                  dst_crs=cfg["grid"]["crs"], dst_nodata=np.nan, resampling=Resampling.bilinear)
        dst[name] = o
    lo, hi = cfg["valid_incidence_deg"]
    land = land_mask(transform, shape)
    ok = (dst["valid"] > 0.99) & np.isfinite(dst["s0"]) & (dst["inc"] >= lo) & (dst["inc"] <= hi)
    s0_db = np.where(ok, 10 * np.log10(np.maximum(dst["s0"], floor)), np.nan).astype(np.float32)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, s0_db=s0_db, inc=np.where(ok, dst["inc"], np.nan).astype(np.float32), land=land, valid=ok & ~land)
    meta = {"scene_id": scene_id, "acquired": prov["acquired"], "crs": cfg["grid"]["crs"], "transform": list(transform)[:6],
            "shape": list(shape), "resolution_m": res, "polarization": pol.upper(), "mode": prov["mode"],
            "valid_fraction": float((ok & ~land).mean()), "ocean_valid_pixels": int((ok & ~land).sum()),
            "sigma0_db_p5_p50_p95": [float(np.nanpercentile(s0_db, q)) for q in (5, 50, 95)] if ok.any() else None,
            "incidence_range_deg": [float(np.nanmin(dst["inc"][ok])), float(np.nanmax(dst["inc"][ok]))] if ok.any() else None,
            "processing": {"calibration": "sigma0 from product LUT", "thermal_noise": bool(cfg["thermal_noise_removal"]),
                           "noise_floor_db": cfg["noise_floor_db"], "incidence": "asin(A_beta^2/A_sigma^2)",
                           "geocoding": "GCP warp (EPSG:4326 GCPs) -> EPSG:3031 bilinear", "speckle_filter": cfg["speckle"],
                           "terrain_correction": cfg["terrain_correction"], "land_mask": cfg["land_mask"]["source"]},
            "source_files": prov["files"]}
    meta_p.write_text(json.dumps(meta, indent=1))
    return meta


def load_scene(scene_id: str) -> tuple[dict, dict]:
    z = np.load(INTERIM / "scenes" / f"{scene_id}.npz")
    return {k: z[k] for k in z.files}, json.loads((INTERIM / "scenes" / f"{scene_id}.json").read_text())
