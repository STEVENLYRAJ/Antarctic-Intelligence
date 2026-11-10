"""AETHENTRA ML-02 router: weekly Antarctic 2 m temperature & anomaly forecasts, mounted under /temperature.

Same conventions as the ML-01 service: logical file names only, no filesystem paths, model predictions labelled.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from aethentra.temperature.inference.predict import FINAL, FORECAST_DIR, cached_bundle, run_forecast
from aethentra.temperature.inference.schema import T2mForecastRequest, T2mForecastSummary
from aethentra.temperature.paths import METRICS

router = APIRouter(prefix="/temperature", tags=["ML-02 temperature"])
ID_RE = re.compile(r"^t2m7d_\d{8}_[A-Za-z0-9._-]+$")
FILE_KINDS = {"netcdf": ".nc", "summary_json": ".json"}


def _meta() -> dict:
    p = FINAL / "final_model.meta.json"
    if not p.exists():
        raise HTTPException(503, "No ML-02 final model available")
    return json.loads(p.read_text())


def _summaries() -> list[dict]:
    out = []
    for f in sorted(FORECAST_DIR.glob("t2m7d_*/t2m7d_*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except json.JSONDecodeError:
            continue
    return sorted(out, key=lambda s: (s["issue_date"], s["generated_utc"]))


@router.get("/health")
def health():
    ok = (FINAL / "final_model.meta.json").exists()
    return {"status": "ok" if ok else "degraded", "model_available": ok, "time_utc": dt.datetime.now(dt.timezone.utc).isoformat()}


@router.get("/model/info")
def model_info():
    m = _meta()
    sel = METRICS / "selection_record.json"
    return {"model_version": m.get("model_version"), "selected_from": m.get("selected_from"), "kind": m["kind"], "n_features": len(m["features"]),
            "features": m["features"], "train_period": m.get("train_period"), "source": m.get("source"),
            "climatology_period": m.get("climatology_period"), "selection": json.loads(sel.read_text()).get("selection_basis") if sel.exists() else None}


@router.post("/forecast/weekly", response_model=T2mForecastSummary)
def forecast_weekly(req: T2mForecastRequest):
    _meta()
    try:
        s, _ = run_forecast(req.issue_date, bundle=cached_bundle(), write=True, layers=req.write_layers)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return s


@router.get("/forecast/latest", response_model=T2mForecastSummary)
def forecast_latest():
    s = _summaries()
    if not s:
        raise HTTPException(404, "No ML-02 forecast generated yet")
    return s[-1]


@router.get("/forecast/history")
def forecast_history():
    return [{k: x[k] for k in ("forecast_id", "issue_date", "target_start", "target_end", "model_version")} for x in _summaries()]


@router.get("/forecast/metrics")
def forecast_metrics():
    p = METRICS / "test_final" / "summary.json"
    if not p.exists():
        raise HTTPException(404, "Test evaluation not available")
    t = json.loads(p.read_text())
    keep = ("all", "antarctica_land", "southern_ocean", "antarctic_peninsula", "west_antarctica", "east_antarctica", "coastal_land", "inland")
    return {"split": "test", "issue_dates": [t["first"], t["last"]], "n_issue_dates": t["n_issue_dates"], "source": t["source"],
            "metrics": {m: {r: {k: v for k, v in x[r].items() if k not in ("by_season", "categories")} for r in keep if r in x}
                        for m, x in t["metrics"].items()},
            "interval_coverage": t.get("interval_coverage"), "data_type": "evaluation"}


@router.get("/forecast/metadata")
def forecast_metadata():
    m = _meta()
    return {"product": "Weekly-mean 2 m temperature and anomaly, Antarctica south of 60S", "grid": "EPSG:3412 25 km",
            "target": "mean of days t+1..t+7 (UTC); anomaly vs climatology of the same days", "climatology_period": m.get("climatology_period"),
            "units": {"t2m": "degC", "anomaly": "degC"}, "model_version": m.get("model_version"), "source": m.get("source"),
            "nature": "statistical forecast trained on reanalysis; not a numerical weather prediction"}


@router.get("/forecast/{forecast_id}/files/{kind}")
def forecast_file(forecast_id: str, kind: str):
    if not ID_RE.match(forecast_id) or kind not in FILE_KINDS:
        raise HTTPException(404, "Unknown forecast or file kind")
    p = FORECAST_DIR / forecast_id / f"{forecast_id}{FILE_KINDS[kind]}"
    if not p.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(p, filename=p.name)
