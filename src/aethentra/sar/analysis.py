"""ML-03 error analysis on the TEST scenes (after the single test evaluation; nothing here feeds back into training/selection).

* errors of the final model vs incidence angle, distance to coast, HH sigma0 (wind-roughened water -> false ice) and month,
* behaviour on chart-uncertain pixels (10-70 % concentration) split by their chart concentration code,
* comparison with the DMI-ASIP automated product (only the one locally available day; pseudo-label agreement, not truth),
* feature importances of the tree baselines.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..config import ROOT
from .evaluation import edge_metrics
from .features import scene_feature_maps
from .labels import ICE, UNCERTAIN, WATER, load_labels
from .paths import INTERIM, METRICS, PROCESSED
from .preprocessing import load_scene


def _bins(x, err, n, edges):
    i = np.digitize(x, edges) - 1
    out = []
    for k in range(len(edges) - 1):
        m = i == k
        if m.sum() >= 500:
            out.append({"bin": [float(edges[k]), float(edges[k + 1])], "pixels": int(m.sum()), "error_rate": float(err[m].mean())})
    return out


SAMPLE_PER_SCENE = 200_000


def error_analysis(max_scenes: int = 400) -> dict:
    cat = pd.read_csv(METRICS / "test_final" / "per_scene.csv").query("model == 'final_model'")
    slope = json.loads((PROCESSED / "tiles" / "tiles.json").read_text())["incidence_slope_db_per_deg"]
    acc = {k: [] for k in ("inc", "dist", "s0", "err", "y", "month")}
    unc, edge = [], {4: [], 10: []}
    for sid in cat["scene_id"].unique()[:max_scenes]:
        p = METRICS / "test_final" / "maps" / f"{sid}__final_model.npz"
        if not p.exists():
            continue
        prob = np.load(p)["prob"].astype(np.float32)
        scene, meta = load_scene(sid)
        lab = load_labels(sid)
        F = scene_feature_maps(scene, meta, slope=slope, glcm=False)
        m = np.isin(lab, (WATER, ICE)) & np.isfinite(prob)
        pred = prob >= 0.5
        idx = np.flatnonzero(m)                            # fixed random sample per scene (bounded memory; seed 42)
        if idx.size > SAMPLE_PER_SCENE:
            idx = np.sort(np.random.default_rng(42).choice(idx, SAMPLE_PER_SCENE, replace=False))
        m = np.zeros(m.shape, bool); m.ravel()[idx] = True
        acc["inc"].append(F["inc"][m].astype(np.float32)); acc["dist"].append(F["dist_coast_km"][m].astype(np.float32))
        acc["s0"].append(F["s0"][m].astype(np.float32)); acc["err"].append(pred[m] != (lab[m] == ICE)); acc["y"].append(lab[m])
        acc["month"].append(np.full(m.sum(), pd.Timestamp(meta["acquired"]).month, np.int8))
        del F
        raw = load_labels(sid, raw=True)
        for km in edge:                                   # post-test sensitivity of the edge score to the tolerance (analysis only)
            e = edge_metrics(pred & np.isfinite(prob), raw, scene["valid"], meta["resolution_m"], int(km * 1000 / meta["resolution_m"]))
            if "boundary_f1" in e:
                edge[km].append(e["boundary_f1"])
        u = (lab == UNCERTAIN) & np.isfinite(prob)
        if u.any():
            unc.append(pred[u])
    A = {k: np.concatenate(v) for k, v in acc.items()}
    water = A["y"] == WATER
    res = {"pixels": int(A["err"].size), "sampling": f"up to {SAMPLE_PER_SCENE:,} random labelled pixels per test scene (seed 42)", "overall_error_rate": float(A["err"].mean()),
           "by_incidence_deg": _bins(A["inc"], A["err"], 0, np.arange(18, 50, 3)),
           "by_distance_to_coast_km": _bins(A["dist"], A["err"], 0, np.array([0, 10, 25, 50, 100, 200, 400, 2000])),
           "by_month": [{"month": int(mo), "pixels": int((A["month"] == mo).sum()), "error_rate": float(A["err"][A["month"] == mo].mean())}
                        for mo in np.unique(A["month"])],
           "water_false_ice_rate_by_sigma0_db": _bins(A["s0"][water], A["err"][water], 0, np.arange(-30, 2, 2)),
           "ice_missed_rate_by_sigma0_db": _bins(A["s0"][~water], A["err"][~water], 0, np.arange(-30, 2, 2)),
           "chart_uncertain_pixels_predicted_ice_fraction": float(np.concatenate(unc).mean()) if unc else None,
           "boundary_f1_by_tolerance_km": {"2 (evaluation setting)": float(cat["boundary_f1"].mean()),
                                           **{str(k): float(np.mean(v)) if v else None for k, v in edge.items()}}}
    res["feature_importance"] = {}
    for n in ("rf", "xgb"):
        p = ROOT / "models" / "ml03" / "checkpoints" / f"{n}.meta.json"
        if p.exists():
            res["feature_importance"][n] = json.loads(p.read_text()).get("feature_importance")
    del A, acc, unc                                        # free the pooled pixel arrays before the DMI comparison
    res["dmi_asip_comparison"] = dmi_asip_comparison()
    (METRICS / "error_analysis_test.json").write_text(json.dumps(res, indent=1))
    return res


def dmi_asip_comparison() -> dict:
    """Agreement of the final model with the DMI-ASIP 1 km SIC (>= 15 % = ice) for every processed scene acquired on its day."""
    import xarray as xr
    from affine import Affine
    from rasterio.warp import Resampling, reproject
    from .inference import FINAL
    from .training import load_model
    f = ROOT / "DATAS" / "dmi_asip_seaice_mosaic_ant_20230202.nc"
    if not f.exists():
        return {"status": "file not available"}
    day = "2023-02-02"
    ids = [p.stem for p in (INTERIM / "scenes").glob("*.json") if json.loads(p.read_text())["acquired"].startswith(day)]
    if not ids:
        return {"status": f"no processed scene acquired {day}"}
    ds = xr.open_dataset(f)
    x, y = ds["x"].values, ds["y"].values
    src_tr = Affine(float(x[1] - x[0]), 0, float(x[0] - (x[1] - x[0]) / 2), 0, float(y[1] - y[0]), float(y[0] - (y[1] - y[0]) / 2))
    a = ds["crs"].attrs
    src_crs = a.get("proj4_string") or a.get("spatial_ref") or a.get("crs_wkt")
    if not src_crs:
        return {"status": "DMI file has no usable grid-mapping attributes"}
    model = load_model(FINAL, "final_model")
    slope = json.loads((PROCESSED / "tiles" / "tiles.json").read_text())["incidence_slope_db_per_deg"]
    tp = fp = fn = tn = 0
    used = []
    from pyproj import Transformer
    for sid in ids:
        scene, meta = load_scene(sid)
        tr = Affine(*meta["transform"])
        h, w = meta["shape"]
        cx = np.array([tr.c, tr.c + tr.a * w, tr.c, tr.c + tr.a * w]); cy = np.array([tr.f, tr.f, tr.f + tr.e * h, tr.f + tr.e * h])
        sx, sy = Transformer.from_crs(meta["crs"], src_crs, always_xy=True).transform(cx, cy)
        j = np.searchsorted(x, [sx.min() - 20_000, sx.max() + 20_000]).clip(0, len(x))         # read only the scene window
        i = np.sort(np.searchsorted(-y, [-(sy.max() + 20_000), -(sy.min() - 20_000)]).clip(0, len(y)))
        if j[1] <= j[0] or i[1] <= i[0]:
            continue
        sic = ds["ice_concentration"].isel(time=0, y=slice(i[0], i[1]), x=slice(j[0], j[1])).values.astype(np.float32)
        wtr = Affine(src_tr.a, 0, src_tr.c + j[0] * src_tr.a, 0, src_tr.e, src_tr.f + i[0] * src_tr.e)
        dst = np.full((h, w), np.nan, np.float32)
        reproject(sic, dst, src_transform=wtr, src_crs=src_crs, dst_transform=tr, dst_crs=meta["crs"],
                  src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.nearest)
        F = scene_feature_maps(scene, meta, slope=slope, glcm=model.kind in ("random_forest", "xgboost"))
        prob = model.prob_map(F)
        m = scene["valid"] & np.isfinite(dst) & np.isfinite(prob) & (dst >= 0) & (dst <= 100)
        if m.sum() < 1000:
            continue
        r, p = dst[m] >= 15, prob[m] >= 0.5
        tp += int((r & p).sum()); fp += int((~r & p).sum()); fn += int((r & ~p).sum()); tn += int((~r & ~p).sum())
        used.append(sid)
    n = tp + fp + fn + tn
    if not n:
        cov = float(np.isfinite(ds["ice_concentration"].isel(time=0).values[::10, ::10]).mean())
        return {"status": f"no overlap: the DMI-ASIP file has valid data over only {cov:.1%} of its Antarctic grid on {day}, "
                          f"none of it within the {len(ids)} processed Sentinel-1 scene(s) of that day", "scenes_checked": ids}
    return {"status": "computed", "day": day, "scenes": used, "pixels": n, "agreement": (tp + tn) / n,
            "iou_ice": tp / max(tp + fp + fn, 1), "iou_water": tn / max(tn + fp + fn, 1),
            "note": "DMI-ASIP is an automated CNN product from the same Sentinel-1 data (+AMSR2); agreement is not independent validation. "
                    "Projection taken from the file's proj4_string (polar stereographic, lat_ts -70)."}
