"""AETHENTRA sea-ice forecast service (FastAPI).

    uvicorn api.main:app --port 8000          (from the repository root)

Endpoints never expose model files, credentials or filesystem paths; forecast files are served by logical name.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aethentra import __version__  # noqa: E402
from aethentra.config import EXPERIMENTS_DIR, MODELS_DIR, load  # noqa: E402
from aethentra.inference.export_forecast import FORECAST_DIR  # noqa: E402
from aethentra.inference.prediction_schema import ForecastRequest, ForecastSummary  # noqa: E402

app = FastAPI(title="AETHENTRA Antarctic Sea-Ice Forecast API", version=__version__,
              description="Weekly (7-day mean) Antarctic sea-ice concentration forecasts. Model predictions are labelled "
                          "data_type='model_prediction' and must be displayed distinctly from observations.")
from api.temperature import router as temperature_router  # noqa: E402  ML-02, mounted under /temperature

app.include_router(temperature_router)
from fastapi.responses import RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from api.viewer import router as viewer_router  # noqa: E402  map layers for both products

app.include_router(viewer_router)
app.mount("/viewer", StaticFiles(directory=ROOT / "frontend", html=True), name="viewer")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/viewer/")


ID_RE = re.compile(r"^sic7d_\d{8}_[A-Za-z0-9._-]+$")
FILE_KINDS = {"netcdf": ".nc", "summary_json": ".json", "ice_edge_geojson": "_ice_edge.geojson"}


def _final_meta() -> dict:
    p = MODELS_DIR / "final" / "final_model.meta.json"
    if not p.exists():
        raise HTTPException(503, "No final model available")
    return json.loads(p.read_text())


def _summaries() -> list[dict]:
    out = []
    for f in sorted(FORECAST_DIR.glob("sic7d_*/sic7d_*.json")):
        if f.name.endswith(".geojson"):
            continue
        try:
            out.append(json.loads(f.read_text()))
        except json.JSONDecodeError:
            continue
    return sorted(out, key=lambda s: (s["issue_date"], s["generated_utc"]))


@app.get("/health")
def health():
    ok = (MODELS_DIR / "final" / "final_model.meta.json").exists()
    return {"status": "ok" if ok else "degraded", "model_available": ok, "time_utc": dt.datetime.now(dt.timezone.utc).isoformat()}


@app.get("/model/info")
def model_info():
    m = _final_meta()
    return {"model_version": m.get("model_version"), "model_family": m["kind"], "selected_candidate": m.get("selected_from"),
            "target": "7-day mean sea-ice concentration (%) for days t+1..t+7, residual over persistence" if m["target_mode"] == "residual" else m["target_mode"],
            "features": m["features"], "training_period": m.get("train_period"), "trained_utc": m.get("trained_utc"),
            "n_estimators": m.get("best_iteration"), "grid": "EPSG:3412 25 km (332 x 316)"}


@app.post("/forecast/weekly", response_model=ForecastSummary)
def forecast_weekly(req: ForecastRequest):
    from aethentra.inference.model_loader import cached_bundle
    from aethentra.inference.predict import run_forecast
    try:
        s, _ = run_forecast(req.issue_date, bundle=cached_bundle(), write=True)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except FileNotFoundError:
        raise HTTPException(503, "Model or input data not available")
    return s


@app.get("/forecast/latest", response_model=ForecastSummary)
def forecast_latest():
    s = _summaries()
    if not s:
        raise HTTPException(404, "No forecast generated yet; POST /forecast/weekly")
    return s[-1]


@app.get("/forecast/history")
def forecast_history(limit: int = 50):
    s = _summaries()[-max(1, min(limit, 500)):]
    return [{k: x[k] for k in ("forecast_id", "issue_date", "target_start", "target_end", "extent_km2", "area_km2", "model_version")} for x in s]


@app.get("/forecast/metrics")
def forecast_metrics():
    p = EXPERIMENTS_DIR / "metrics" / "test_final" / "summary.json"
    if not p.exists():
        raise HTTPException(404, "Test metrics not available")
    r = json.loads(p.read_text())
    keep = ["all", "seasonal_ice_zone", "ice_edge_band"]
    return {"evaluation_period": [r["first"], r["last"]], "issue_dates": r["n_issue_dates"], "climatology_period": r["climatology_period"],
            "metrics": {m: {g: v for g, v in groups.items() if g in keep} for m, groups in r["metrics"].items()},
            "interval_coverage": r.get("interval_coverage"),
            "note": "Single evaluation on the untouched 2021-2025 test period; SIC errors in percentage points, extent in km2."}


@app.get("/forecast/metadata")
def forecast_metadata():
    ds = load("data_sources")
    return {"observations": {k: ds["sea_ice_concentration"][k] for k in ("name", "version", "doi", "landing_page", "license")},
            "atmosphere": {k: ds["atmosphere_interim"][k] for k in ("name", "landing_page", "note")},
            "definitions": {"issue_time": "end of day t (UTC); observations through day t", "target": "mean SIC over t+1..t+7",
                            "extent": "sum of cell areas with SIC >= 15 %", "area": "sum of cell area x SIC/100 for SIC >= 15 %"},
            "units": {"sic": "percent", "extent": "km2", "area": "km2"}}


@app.get("/forecast/{forecast_id}/files/{kind}")
def forecast_file(forecast_id: str, kind: str):
    if not ID_RE.match(forecast_id) or kind not in FILE_KINDS:
        raise HTTPException(404, "Unknown forecast or file kind")
    f = FORECAST_DIR / forecast_id / f"{forecast_id}{FILE_KINDS[kind]}"
    if not f.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(f, filename=f.name)
