"""AETHENTRA ML-03 router: Sentinel-1 sea-ice detection, mounted under /seaice-detection.

Same conventions as ML-01/ML-02: logical identifiers only (scene ids, week starts), no filesystem paths or credentials,
every product labelled as a model prediction.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from aethentra.sar.inference import FINAL, SEG_DIR, WEEKLY_DIR
from aethentra.sar.paths import METRICS

router = APIRouter(prefix="/seaice-detection", tags=["ML-03 SAR sea-ice detection"])
SCENE_RE = re.compile(r"^S1[A-D]_EW_GRD[MH]_1S[SD]H_\d{8}T\d{6}_\d{8}T\d{6}_\d{6}_[0-9A-F]{6}$")
WEEK_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SCENE_FILES = {"probability_tif": "sea_ice_probability.tif", "class_tif": "sea_ice_class.tif", "netcdf": "segmentation.nc"}
WEEK_FILES = {"detection_frequency": "detection_frequency.tif", "valid_acquisitions": "valid_acquisitions.tif",
              "ice_detections": "ice_detections.tif", "weekly_class": "weekly_class.tif"}


class DetectRequest(BaseModel):
    scene_id: str = Field(..., description="Sentinel-1 EW GRDM HH product identifier (e.g. S1A_EW_GRDM_1SSH_20250101T...)")


def _meta() -> dict:
    p = FINAL / "final_model.meta.json"
    if not p.exists():
        raise HTTPException(503, "No ML-03 final model available")
    return json.loads(p.read_text())


def _scene_meta(sid: str) -> dict:
    p = SEG_DIR / sid / "metadata.json"
    if not SCENE_RE.match(sid) or not p.exists():
        raise HTTPException(404, "Unknown scene")
    return json.loads(p.read_text())


@router.get("/health")
def health():
    ok = (FINAL / "final_model.meta.json").exists()
    return {"status": "ok" if ok else "degraded", "model_available": ok, "time_utc": dt.datetime.now(dt.timezone.utc).isoformat()}


@router.get("/model/info")
def model_info():
    m = _meta()
    return {k: m.get(k) for k in ("model_version", "selected_from", "kind", "channels", "features", "architecture", "loss", "train_splits",
                                  "trained_utc")} | {"input": "Sentinel-1 EW GRDM HH, sigma0 (dB) + incidence angle, 400 m EPSG:3031",
                                                    "labels": "USNIC Antarctic ice charts (expert analyses; chart-scale)"}


@router.post("/detect/sea-ice")
def detect(req: DetectRequest):
    if not SCENE_RE.match(req.scene_id):
        raise HTTPException(422, "scene_id must be a Sentinel-1 EW GRD HH product identifier")
    _meta()
    from aethentra.sar.inference import classify_scene
    try:
        classify_scene(req.scene_id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"scene could not be retrieved or processed ({type(e).__name__})") from e
    return {"status": "processed", **_scene_meta(req.scene_id)}


@router.get("/detection/history")
def history(limit: int = 100):
    rows = []
    for p in sorted(SEG_DIR.glob("*/metadata.json")):
        m = json.loads(p.read_text())
        rows.append({k: m.get(k) for k in ("scene_id", "acquired", "model_version", "nominal_ice_area_km2")})
    return sorted(rows, key=lambda r: r["acquired"])[-max(1, min(limit, 1000)):]


@router.get("/detection/latest")
def latest():
    h = history(1)
    if not h:
        raise HTTPException(404, "No detection produced yet")
    return _scene_meta(h[-1]["scene_id"])


@router.get("/detection/weekly")
def weekly(week_start: str | None = None):
    weeks = sorted(p.parent.name[5:] for p in WEEKLY_DIR.glob("week_*/metadata.json"))
    if not weeks:
        raise HTTPException(404, "No weekly composite produced yet")
    w = week_start or weeks[-1]
    if not WEEK_RE.match(w) or w not in weeks:
        raise HTTPException(404, "Unknown week")
    m = json.loads((WEEKLY_DIR / f"week_{w}" / "metadata.json").read_text())
    return {**m, "available_weeks": weeks}


@router.get("/detection/metrics")
def metrics():
    p = METRICS / "test_final" / "summary.json"
    if not p.exists():
        raise HTTPException(404, "Test evaluation not available")
    t = json.loads(p.read_text())
    return {"split": "test", "n_scenes": t["n_scenes"], "charts": [t["first_chart"], t["last_chart"]], "label_source": t["label_source"],
            "metrics": {m: {k: v for k, v in x.items() if k != "confusion"} for m, x in t["metrics"].items()}, "data_type": "evaluation"}


@router.get("/detection/metadata")
def metadata():
    return {"product": "Pixel-level Antarctic sea-ice / open-water segmentation from Sentinel-1 SAR", "grid": "EPSG:3031, 400 m (scenes), 2 km (weekly)",
            "classes": {"0": "open water", "1": "sea ice", "2": "uncertain (probability in the uncertain band)", "255": "invalid / land / no data"},
            "weekly": "detection frequency = ice classifications / valid acquisitions per cell; unobserved cells are not filled",
            "nature": "model prediction; labels are chart-scale expert analyses, not pixel-perfect truth"}


@router.get("/detection/{scene_id}/files/{kind}")
def scene_file(scene_id: str, kind: str):
    _scene_meta(scene_id)
    if kind not in SCENE_FILES:
        raise HTTPException(404, "Unknown file kind")
    return FileResponse(SEG_DIR / scene_id / SCENE_FILES[kind], filename=f"{scene_id}_{SCENE_FILES[kind]}")


@router.get("/detection/weekly/{week_start}/files/{kind}")
def week_file(week_start: str, kind: str):
    if not WEEK_RE.match(week_start) or kind not in WEEK_FILES or not (WEEKLY_DIR / f"week_{week_start}" / "layers" / WEEK_FILES[kind]).exists():
        raise HTTPException(404, "Unknown week or file kind")
    return FileResponse(WEEKLY_DIR / f"week_{week_start}" / "layers" / WEEK_FILES[kind], filename=f"week_{week_start}_{WEEK_FILES[kind]}")
