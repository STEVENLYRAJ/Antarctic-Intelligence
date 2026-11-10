"""Map-layer endpoints + static web viewer for ML-01 (sea ice) and ML-02 (2 m temperature).

    GET /layers/{product}/latest                      normalised layer manifest of the newest forecast (product = sic | t2m)
    GET /layers/{product}/{forecast_id}/{layer}.png   polar-stereographic preview rendered from the native EPSG:3412 GeoTIFF
    GET /layers/{product}/{forecast_id}/{layer}.tif   native GeoTIFF
    GET /viewer/                                      browser viewer (frontend/)

Layers are addressed by logical id only; filesystem paths are never exposed. Every layer carries its data_type so the viewer
can keep model predictions visually distinct from observations / reanalysis and evaluation layers.
"""
from __future__ import annotations

import io
import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from aethentra.inference.export_forecast import FORECAST_DIR as SIC_DIR
from aethentra.temperature.inference.predict import FORECAST_DIR as T2M_DIR

router = APIRouter(tags=["map layers"])
PRODUCTS = {"sic": (SIC_DIR, "sic7d_"), "t2m": (T2M_DIR, "t2m7d_")}
ID_RE = re.compile(r"^(sic|t2m)7d_\d{8}_[A-Za-z0-9._-]+$")
LAYER_RE = re.compile(r"^[a-z0-9_]+$")
# colormap, vmin, vmax per layer id (fallback by units)
STYLE = {"forecast_7day_mean": ("Blues_r", 0, 100), "observed_latest_week": ("Blues_r", 0, 100),
         "test_spatial_error": ("magma_r", 0, 15), "test_error_mae": ("magma_r", 0, 4),
         "forecast_anomaly": ("RdBu_r", -6, 6), "observed_anomaly_latest_week": ("RdBu_r", -10, 10),
         "forecast_warm_regions": ("RdBu_r", 0, 4), "forecast_cold_regions": ("RdBu_r", 0, 4), "forecast_extreme_regions": ("RdBu_r", 0, 4)}
DEFAULT_T = ("RdYlBu_r", -60, 0)


def _forecast_dir(product: str, forecast_id: str | None = None) -> Path:
    if product not in PRODUCTS:
        raise HTTPException(404, "Unknown product (sic | t2m)")
    base, prefix = PRODUCTS[product]
    if forecast_id is None:
        dirs = sorted(d for d in base.glob(f"{prefix}*") if (d / "layers" / "manifest.json").exists())
        if not dirs:
            raise HTTPException(404, "No forecast with map layers yet")
        return max(dirs, key=lambda d: (d.name.split("_")[1], (d / "layers" / "manifest.json").stat().st_mtime))
    if not ID_RE.match(forecast_id) or not forecast_id.startswith(prefix):
        raise HTTPException(404, "Unknown forecast")
    d = base / forecast_id
    if not (d / "layers" / "manifest.json").exists():
        raise HTTPException(404, "Unknown forecast")
    return d


def _layers(d: Path) -> tuple[dict, list[dict]]:
    """Both manifest dialects (ML-01 'files' list, ML-02 'geotiff'/'png') -> one normalised list."""
    m = json.loads((d / "layers" / "manifest.json").read_text())
    out = []
    for lyr in m["layers"]:
        files = list(lyr.get("files") or []) + [lyr[k] for k in ("geotiff", "png", "geojson", "file") if lyr.get(k)]
        tif = next((f for f in files if f.endswith("_3412.tif")), None)
        other = [f for f in files if f.endswith((".json", ".geojson"))]
        cmap, lo, hi = STYLE.get(lyr["id"], DEFAULT_T if lyr.get("units") == "degC" else ("viridis", None, None))
        if lyr.get("color_range") and lyr["id"] not in STYLE:
            lo, hi = lyr["color_range"]
        out.append({"id": lyr["id"], "title": lyr.get("title") or lyr["id"].replace("_", " "), "data_type": lyr.get("data_type"),
                    "units": lyr.get("units"), "period": lyr.get("period"), "issue_date": lyr.get("issue_date") or m.get("issue_date"),
                    "raster": tif, "vector": other, "style": {"cmap": cmap, "vmin": lo, "vmax": hi}})
    return m, out


def _colors(cmap: str, n: int = 11) -> list[str]:
    import matplotlib
    c = matplotlib.colormaps[cmap]
    return ["#%02x%02x%02x" % tuple(int(255 * v) for v in c(i / (n - 1))[:3]) for i in range(n)]


@router.get("/layers/{product}/latest")
def layers_latest(product: str):
    d = _forecast_dir(product)
    m, layers = _layers(d)
    for lyr in layers:
        if lyr["raster"]:
            lyr["png_url"] = f"/layers/{product}/{d.name}/{lyr['id']}.png"
            lyr["tif_url"] = f"/layers/{product}/{d.name}/{lyr['id']}.tif"
            lyr["style"]["colors"] = _colors(lyr["style"]["cmap"])
        lyr["vector_urls"] = [f"/layers/{product}/{d.name}/files/{f}" for f in lyr.pop("vector")]
        lyr.pop("raster")
    summary = next(iter(sorted(d.glob(f"{d.name}.json"))), None)
    return {"product": product, "forecast_id": d.name, "issue_date": m.get("issue_date"), "model_version": m.get("model_version"),
            "source": m.get("source"), "limitations": m.get("limitations"), "display_rules": m.get("display_rules"),
            "summary": json.loads(summary.read_text()) if summary else None, "layers": layers}


@lru_cache(maxsize=1)
def _land() -> np.ndarray | None:
    """Land mask on the 332 x 316 EPSG:3412 grid (from the ML-02 grid file; None if not built)."""
    from aethentra.temperature.paths import INTERIM
    f = next(iter(sorted(INTERIM.glob("*/grid.npz"))), None)
    if f is None:
        return None
    z = np.load(f)
    g = np.zeros(tuple(z["shape"]), bool)
    g[z["rows"], z["cols"]] = z["land"].astype(bool)
    return g


@lru_cache(maxsize=64)
def _render(tif: str, mtime: float, cmap: str, vmin, vmax) -> bytes:
    import matplotlib
    import rasterio
    with rasterio.open(tif) as r:
        a = r.read(1, masked=True).astype("float32").filled(np.nan)
    if vmin is None:
        vmin, vmax = np.nanpercentile(a, [2, 98])
    rgba = matplotlib.colormaps[cmap]((np.clip(a, vmin, vmax) - vmin) / max(vmax - vmin, 1e-9))
    rgba[~np.isfinite(a)] = 0
    land = _land()
    if land is not None and land.shape == a.shape:
        rgba[land & ~np.isfinite(a)] = (0.62, 0.65, 0.69, 1.0)        # land without data: grey
        coast = land & ~(np.roll(land, 1, 0) & np.roll(land, -1, 0) & np.roll(land, 1, 1) & np.roll(land, -1, 1))
        rgba[coast] = (0.15, 0.17, 0.2, 1.0)                           # coastline
    buf = io.BytesIO()
    matplotlib.pyplot.imsave(buf, rgba, format="png")
    return buf.getvalue()


def _layer_tif(product, forecast_id, layer) -> tuple[Path, dict]:
    if not LAYER_RE.match(layer):
        raise HTTPException(404, "Unknown layer")
    d = _forecast_dir(product, forecast_id)
    m, layers = _layers(d)
    lyr = next((x for x in layers if x["id"] == layer and x["raster"]), None)
    if lyr is None or not (d / "layers" / lyr["raster"]).exists():
        raise HTTPException(404, "Unknown layer")
    return d / "layers" / lyr["raster"], lyr


@router.get("/layers/{product}/{forecast_id}/{layer}.png")
def layer_png(product: str, forecast_id: str, layer: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot  # noqa: F401
    p, lyr = _layer_tif(product, forecast_id, layer)
    s = lyr["style"]
    png = _render(str(p), p.stat().st_mtime, s["cmap"], s["vmin"], s["vmax"])
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=300"})


@router.get("/layers/{product}/{forecast_id}/{layer}.tif")
def layer_tif(product: str, forecast_id: str, layer: str):
    p, _ = _layer_tif(product, forecast_id, layer)
    return FileResponse(p, filename=p.name, media_type="image/tiff")


@router.get("/layers/{product}/{forecast_id}/files/{name}")
def layer_file(product: str, forecast_id: str, name: str):
    d = _forecast_dir(product, forecast_id)
    _, layers = _layers(d)
    allowed = {f for x in layers for f in x["vector"]}
    if name not in allowed or not (d / "layers" / name).exists():
        raise HTTPException(404, "Unknown file")
    return FileResponse(d / "layers" / name, media_type="application/json")
