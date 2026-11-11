"""ML-03 evaluation on full scenes (never on tiles): agreement with USNIC chart labels.

Pixel metrics use chart classes 0 (water) and 1 (ice) only; uncertain (2) and invalid (255) pixels are excluded.
Ice-edge metrics use the unbuffered chart raster: reference ice = chart classes 1 or 2 (>= 10 % concentration) vs 0.
Areas use the true area of each EPSG:3031 pixel (resolution^2 / areal scale factor at its latitude).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import ndimage

from .labels import ICE, INVALID, UNCERTAIN, WATER
from .paths import load


def true_pixel_area_km2(lat: np.ndarray, lon: np.ndarray, res_m: float) -> np.ndarray:
    from pyproj import Proj
    f = Proj(load("sar_preprocessing")["grid"]["crs"]).get_factors(lon, lat)
    return (res_m ** 2 / np.asarray(f.areal_scale)) / 1e6


def _edges(mask: np.ndarray, region: np.ndarray) -> np.ndarray:
    er = ndimage.binary_erosion(mask, iterations=1, border_value=1)
    di = ndimage.binary_dilation(mask, iterations=1)
    e = (mask & ~er) | (di & ~mask)
    return e & ndimage.binary_erosion(region, iterations=2)          # ignore the borders of the valid region


def edge_metrics(pred_ice: np.ndarray, raw: np.ndarray, valid: np.ndarray, res_m: float, tol_px: int) -> dict:
    region = valid & (raw != INVALID)
    ref = np.isin(raw, (ICE, UNCERTAIN)) & region
    pe, re = _edges(pred_ice & region, region), _edges(ref, region)
    if not re.any() or not pe.any():
        return {"ref_edge_px": int(re.sum()), "pred_edge_px": int(pe.sum())}
    d_to_ref = ndimage.distance_transform_edt(~re)
    d_to_pred = ndimage.distance_transform_edt(~pe)
    p = float((d_to_ref[pe] <= tol_px).mean())
    r = float((d_to_pred[re] <= tol_px).mean())
    return {"ref_edge_px": int(re.sum()), "pred_edge_px": int(pe.sum()), "boundary_precision": p, "boundary_recall": r,
            "boundary_f1": 2 * p * r / (p + r) if p + r else 0.0, "edge_displacement_km_mean": float(d_to_ref[pe].mean() * res_m / 1000),
            "edge_displacement_km_median": float(np.median(d_to_ref[pe]) * res_m / 1000)}


def scene_record(pred_ice: np.ndarray, prob: np.ndarray | None, lab: np.ndarray, raw: np.ndarray, valid: np.ndarray, area: np.ndarray,
                 res_m: float) -> dict:
    m = np.isin(lab, (WATER, ICE))
    y, p = lab[m] == ICE, pred_ice[m]
    a = area[m]
    rec = {"tp": int((y & p).sum()), "fp": int((~y & p).sum()), "fn": int((y & ~p).sum()), "tn": int((~y & ~p).sum()),
           "ref_ice_km2": float(a[y].sum()), "pred_ice_km2": float(a[p].sum()), "labelled_km2": float(a.sum()),
           "uncertain_px": int((lab == UNCERTAIN).sum()), "uncertain_pred_ice_frac": float(pred_ice[lab == UNCERTAIN].mean()) if (lab == UNCERTAIN).any() else None}
    if prob is not None:
        pr = prob[m]
        rec["brier"] = float(((pr - y) ** 2).mean()) if m.any() else None
        rec["_reliability"] = np.histogram2d(pr, y.astype(float), bins=[np.linspace(0, 1, 11), [-0.5, 0.5, 1.5]])[0]
    rec.update(edge_metrics(pred_ice, raw, valid, res_m, load("evaluation")["boundary_tolerance_px"]))
    return rec


def summarize(df: pd.DataFrame) -> dict:
    tp, fp, fn, tn = (int(df[k].sum()) for k in ("tp", "fp", "fn", "tn"))
    n = tp + fp + fn + tn
    iou_i = tp / max(tp + fp + fn, 1)
    iou_w = tn / max(tn + fn + fp, 1)
    prec, rec = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    pw, rw = tn / max(tn + fn, 1), tn / max(tn + fp, 1)
    out = {"n_scenes": int(len(df)), "n_pixels": n, "iou_ice": iou_i, "iou_water": iou_w, "miou": (iou_i + iou_w) / 2,
           "dice_ice": 2 * tp / max(2 * tp + fp + fn, 1), "precision_ice": prec, "recall_ice": rec,
           "f1_ice": 2 * prec * rec / max(prec + rec, 1e-12), "precision_water": pw, "recall_water": rw,
           "f1_water": 2 * pw * rw / max(pw + rw, 1e-12), "overall_accuracy": (tp + tn) / max(n, 1),
           "balanced_accuracy": (rec + rw) / 2, "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
           "ref_ice_km2": float(df["ref_ice_km2"].sum()), "pred_ice_km2": float(df["pred_ice_km2"].sum())}
    out["ice_area_bias_km2"] = out["pred_ice_km2"] - out["ref_ice_km2"]
    out["ice_area_bias_pct"] = 100 * out["ice_area_bias_km2"] / max(out["ref_ice_km2"], 1e-9)
    for k in ("boundary_f1", "boundary_precision", "boundary_recall", "edge_displacement_km_mean", "edge_displacement_km_median", "brier"):
        if k in df and df[k].notna().any():
            out[f"{k}_scene_mean"] = float(df[k].mean())
    if "uncertain_pred_ice_frac" in df and df["uncertain_pred_ice_frac"].notna().any():
        out["uncertain_pixels_predicted_ice_frac_scene_mean"] = float(df["uncertain_pred_ice_frac"].mean())
    s = df.assign(iou=df.tp / (df.tp + df.fp + df.fn).clip(lower=1))
    out["scene_iou_ice_median"] = float(s.loc[(df.tp + df.fn) > 0, "iou"].median()) if ((df.tp + df.fn) > 0).any() else None
    return out


def grouped(df: pd.DataFrame, col: str) -> dict:
    return {str(k): {m: v for m, v in summarize(g).items() if m != "confusion"} for k, g in df.groupby(col)}
