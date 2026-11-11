"""ML-03 features (computed from the preprocessed scene only - no information from after the acquisition).

Pixel features (threshold / Random Forest / XGBoost): HH sigma0 (dB), incidence angle, incidence-normalised sigma0, local means
(3/7/15 px), local std (7/15 px), gradient magnitude, block GLCM contrast / homogeneity / entropy (16 px blocks, 32 grey levels),
latitude, sin/cos longitude, distance to coast, sin/cos day of year.
U-Net channels: normalised sigma0, incidence angle, local std (7 px), valid mask.
HV / VV / VH channels are optional: Antarctic EW acquisitions are HH-only, so no model depends on them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import ndimage

PIXEL_FEATURES = ["s0", "inc", "s0_norm", "mean3", "mean7", "mean15", "std7", "std15", "grad", "glcm_contrast",
                  "glcm_homogeneity", "glcm_entropy", "lat", "lon_sin", "lon_cos", "dist_coast_km", "doy_sin", "doy_cos"]
UNET_CHANNELS = ["s0_norm", "inc", "std7", "valid"]
INC_REF = 35.0


def _masked_mean(a, ok, size):
    num = ndimage.uniform_filter(np.where(ok, a, 0.0), size, mode="constant")
    den = ndimage.uniform_filter(ok.astype(float), size, mode="constant")
    return np.where(den > 0.2, num / np.maximum(den, 1e-6), np.nan)


def glcm_blocks(s0, ok, block=16, levels=32, lo=-30.0, hi=0.0):
    from skimage.feature import graycomatrix, graycoprops
    h, w = s0.shape
    q = np.clip(((np.nan_to_num(s0, nan=lo) - lo) / (hi - lo) * (levels - 1)).round(), 0, levels - 1).astype(np.uint8)
    out = {k: np.full((h, w), np.nan, np.float32) for k in ("contrast", "homogeneity", "entropy")}
    for i in range(0, h, block):
        for j in range(0, w, block):
            m = ok[i:i + block, j:j + block]
            if m.mean() < 0.5:
                continue
            g = graycomatrix(q[i:i + block, j:j + block], [1], [0, np.pi / 2], levels=levels, symmetric=True, normed=True)
            p = g.mean(axis=3)[:, :, 0]
            out["contrast"][i:i + block, j:j + block] = graycoprops(g, "contrast").mean()
            out["homogeneity"][i:i + block, j:j + block] = graycoprops(g, "homogeneity").mean()
            out["entropy"][i:i + block, j:j + block] = -(p[p > 0] * np.log2(p[p > 0])).sum()
    return out


def scene_feature_maps(scene: dict, meta: dict, slope: float = 0.0, glcm: bool = True) -> dict:
    """slope (dB / degree) for incidence normalisation is fitted on TRAINING scenes only (baselines module)."""
    from affine import Affine
    from pyproj import Transformer
    ok = scene["valid"]
    s0 = scene["s0_db"].astype(np.float64)
    F = {"s0": s0, "inc": scene["inc"].astype(np.float64), "valid": ok.astype(np.float32)}
    F["s0_norm"] = s0 + slope * (F["inc"] - INC_REF)
    for k in (3, 7, 15):
        F[f"mean{k}"] = _masked_mean(s0, ok, k)
    for k in (7, 15):
        F[f"std{k}"] = np.sqrt(np.maximum(_masked_mean(s0 ** 2, ok, k) - _masked_mean(s0, ok, k) ** 2, 0))
    m3 = np.nan_to_num(F["mean3"], nan=np.nanmedian(s0) if ok.any() else -20)
    F["grad"] = np.where(ok, np.hypot(ndimage.sobel(m3, 0), ndimage.sobel(m3, 1)), np.nan)
    if glcm:
        g = glcm_blocks(s0, ok)
        F.update({f"glcm_{k}": v for k, v in g.items()})
    h, w = s0.shape
    tr = Affine(*meta["transform"])
    xs = tr.c + tr.a * (np.arange(w) + 0.5)
    ys = tr.f + tr.e * (np.arange(h) + 0.5)
    X, Y = np.meshgrid(xs, ys)
    lon, lat = Transformer.from_crs(meta["crs"], "EPSG:4326", always_xy=True).transform(X, Y)
    F["lat"], F["lon_sin"], F["lon_cos"] = lat, np.sin(np.radians(lon)), np.cos(np.radians(lon))
    F["lon"] = lon
    F["dist_coast_km"] = ndimage.distance_transform_edt(~scene["land"]) * meta["resolution_m"] / 1000 if scene["land"].any() else np.full((h, w), 500.0)
    doy = pd.Timestamp(meta["acquired"]).dayofyear
    F["doy_sin"], F["doy_cos"] = np.full((h, w), np.sin(2 * np.pi * doy / 365.25)), np.full((h, w), np.cos(2 * np.pi * doy / 365.25))
    return F


def unet_input(F: dict, norm: dict) -> np.ndarray:
    """(C, H, W) float32; normalisation statistics from TRAINING tiles; NaN -> 0 after normalisation."""
    ch = []
    for k in UNET_CHANNELS:
        if k == "valid":
            ch.append(F["valid"].astype(np.float32))
        else:
            m, s = norm[k]
            ch.append(np.nan_to_num((F[k] - m) / s).astype(np.float32))
    return np.stack(ch)
