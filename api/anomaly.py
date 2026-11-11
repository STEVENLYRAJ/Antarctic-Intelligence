"""AETHENTRA ML-04 router: Antarctic climate anomaly detection, mounted under /api/ml04.

Conventions shared with ML-01...03: logical identifiers only (months, product ids, event ids), never filesystem paths or
credentials; every value is labelled with its baseline period and detection method; statistical anomalies are never presented
as confirmed extreme events or as evidence of a cause. Data are updated periodically (monthly), not in real time.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from functools import lru_cache

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from aethentra.anomaly.paths import FEATURES, METRICS, MODELS, OUTPUTS, PROCESSED

router = APIRouter(prefix="/api/ml04", tags=["ML-04 climate anomaly detection"])
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
VARS = ["t2m", "slp", "wspd", "rhum", "prate", "tcdc", "z500", "sic"]
SEVERITIES = ["mild", "moderate", "strong", "extreme"]
FIELDS = {"value": "", "anomaly": "_anomaly", "z": "_z", "percentile": "_percentile", "severity": "_severity"}
NOTE = "Statistical anomaly relative to a fixed baseline; not a confirmed extreme event; no causal attribution."


def _json(p):
    if not p.exists():
        raise HTTPException(404, "Not available yet (pipeline stage not run)")
    return json.loads(p.read_text())


def _month(m: str | None, name="month"):
    if m is not None and not MONTH_RE.match(m):
        raise HTTPException(422, f"{name} must be YYYY-MM")
    return m


@lru_cache(maxsize=1)
def _cube(mtime: float):
    import xarray as xr
    return xr.open_dataset(OUTPUTS / "anomalies_monthly_1991-2020.nc")


def cube():
    p = OUTPUTS / "anomalies_monthly_1991-2020.nc"
    if not p.exists():
        raise HTTPException(404, "Anomaly cube not built yet")
    return _cube(p.stat().st_mtime)


class Observation(BaseModel):
    month: str = Field(..., description="YYYY-MM of the monthly-mean observation")
    latitude: float = Field(..., ge=-90, le=-48.75)
    longitude: float = Field(..., ge=-180, le=360)
    t2m: float = Field(..., ge=-90, le=25, description="monthly mean near-surface air temperature, degC")
    slp: float = Field(..., ge=900, le=1080, description="hPa")
    wspd: float = Field(..., ge=0, le=40, description="m/s")
    rhum: float = Field(..., ge=0, le=110, description="%")
    prate: float = Field(..., ge=0, le=200, description="mm/day")
    tcdc: float = Field(..., ge=0, le=100, description="%")
    z500: float = Field(..., ge=4000, le=6200, description="m")
    sic: float | None = Field(None, ge=0, le=100, description="% (ocean cells only)")
    sic_previous_month: float | None = Field(None, ge=0, le=100)


class DetectRequest(BaseModel):
    observations: list[Observation] = Field(..., min_length=1, max_length=5000)


@router.get("/health")
def health():
    ok = (MODELS / "decision.json").exists() and (FEATURES / "scores.parquet").exists()
    return {"status": "ok" if ok else "degraded", "models_available": ok,
            "time_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "update_frequency": "monthly (batch); not real time"}


@router.get("/model-info")
def model_info():
    from aethentra.anomaly.export import model_version
    d = _json(MODELS / "decision.json")
    sel = d["selected_multivariate"]
    meta = _json(MODELS / f"{sel}.meta.json")
    return {"model_version": model_version(), "selected_multivariate": sel, "family": meta.get("family"), "params": meta.get("params"),
            "features": meta.get("features"), "train_period": "1979-2010", "baseline_model": "1981-2010", "baseline_reporting": "1991-2020",
            "severity_thresholds": meta.get("thresholds"), "decision_frozen_utc": d["frozen_utc"], "selection_rule": d["rule"],
            "reference_methods": ["zscore", "percentile", "mad", "mahalanobis", "seasonal (trailing 3-month)", "rolling (trailing 30-yr)"],
            "evaluated_candidates": d["family_best"], "rank_sum_validation": d["rank_sum"]}


@router.post("/detect")
def detect(req: DetectRequest):
    from aethentra.anomaly.inference import detect_observations
    try:
        return {"results": detect_observations([o.model_dump() for o in req.observations]), "note": NOTE}
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/latest")
def latest():
    maps = sorted((OUTPUTS / "anomaly_maps").glob("anom_*/anom_*.json"))
    if not maps:
        raise HTTPException(404, "No anomaly product exported yet")
    out = [json.loads(p.read_text()) for p in maps]
    atm = [o for o in out if o["atmosphere_available"]]
    return {"latest_multivariate": atm[-1] if atm else None, "latest_any": out[-1],
            "available_products": [o["month"] for o in out], "note": NOTE}


@router.get("/anomalies")
def anomalies(start: str | None = None, end: str | None = None, region: str | None = None,
              variable: str | None = Query(None, description="t2m|slp|wspd|rhum|prate|tcdc|z500|sic|multivariate"),
              severity: str | None = Query(None, description="minimum severity: moderate|strong|extreme"),
              limit: int = Query(200, ge=1, le=5000), offset: int = Query(0, ge=0)):
    from aethentra.anomaly.storage import query
    _month(start, "start"), _month(end, "end")
    if variable and variable not in VARS + ["multivariate"]:
        raise HTTPException(422, "unknown variable")
    if severity and severity not in SEVERITIES:
        raise HTTPException(422, "unknown severity")
    w, p = ["1=1"], []
    if start:
        w.append("observation_timestamp >= ?"); p.append(f"{start}-01")
    if end:
        w.append("observation_timestamp <= ?"); p.append(f"{end}-01")
    if region:
        w.append("region = ?"); p.append(region)
    if variable:
        w.append("variable = ?"); p.append(variable)
    if severity:
        w.append("severity IN (%s)" % ",".join("?" * len(SEVERITIES[SEVERITIES.index(severity):])))
        p += SEVERITIES[SEVERITIES.index(severity):]
    sql = f"FROM anomaly_events WHERE {' AND '.join(w)}"
    n = query(f"SELECT COUNT(*) AS n {sql}", tuple(p))[0]["n"]
    rows = query(f"SELECT * {sql} ORDER BY observation_timestamp DESC, ABS(anomaly_score) DESC LIMIT ? OFFSET ?", tuple(p + [limit, offset]))
    return {"total": n, "limit": limit, "offset": offset, "records": rows, "note": NOTE}


@router.get("/monthly-summary")
def monthly_summary(start: str | None = None, end: str | None = None):
    _month(start, "start"), _month(end, "end")
    p = OUTPUTS / "summaries" / "monthly_summary.csv"
    if not p.exists():
        raise HTTPException(404, "summary not built")
    df = pd.read_csv(p)
    if start:
        df = df[df["month"] >= start]
    if end:
        df = df[df["month"] <= end]
    return {"baseline": "1981-2010 (model features); flags >= moderate", "rows": json.loads(df.to_json(orient="records")), "note": NOTE}


@router.get("/seasonal-summary")
def seasonal_summary(season: str | None = Query(None, pattern="^(DJF|MAM|JJA|SON)$"), year: int | None = None,
                     region: str | None = None, variable: str | None = None):
    p = OUTPUTS / "summaries" / "seasonal_summary.csv"
    if not p.exists():
        raise HTTPException(404, "summary not built")
    df = pd.read_csv(p)
    for k, v in (("season", season), ("season_year", year), ("region", region), ("variable", variable)):
        if v is not None:
            df = df[df[k] == v]
    return {"baseline": "1991-2020 seasonal-mean climatology", "season_year_convention": "DJF belongs to the year of its February",
            "rows": json.loads(df.to_json(orient="records")), "note": NOTE}


@router.get("/spatial-data")
def spatial_data(month: str, variable: str = "t2m", field: str = Query("z", description="value|anomaly|z|percentile|severity")):
    _month(month)
    if variable not in VARS or field not in FIELDS:
        raise HTTPException(422, "unknown variable or field")
    ds = cube()
    t = pd.DatetimeIndex(ds["time"].values).strftime("%Y-%m")
    if month not in set(t):
        raise HTTPException(404, "month outside the record")
    da = ds[variable + FIELDS[field]].isel(time=int(np.flatnonzero(t == month)[0]))
    a = da.values.astype(float)
    return {"month": month, "variable": variable, "field": field, "units": da.attrs.get("units"), "baseline": "1991-2020",
            "crs": "EPSG:4326", "grid": "NCEP R1 2.5 deg cell centres", "lat": ds["lat"].values.tolist(), "lon": ds["lon"].values.tolist(),
            "values": [[None if not np.isfinite(x) else round(x, 3) for x in row] for row in a],
            "geotiff": f"/api/ml04/maps/anom_{month}/files/{variable}_z_4326.tif" if (OUTPUTS / "anomaly_maps" / f"anom_{month}").exists() else None,
            "note": NOTE}


@router.get("/maps/{product_id}/files/{name}")
def map_file(product_id: str, name: str):
    if not re.match(r"^anom_\d{4}-\d{2}$", product_id) or not re.match(r"^[a-z0-9_]+_(3412|4326)\.tif$", name):
        raise HTTPException(404, "unknown file")
    p = OUTPUTS / "anomaly_maps" / product_id / "layers" / name
    if not p.exists():
        raise HTTPException(404, "unknown file")
    return FileResponse(p, filename=f"{product_id}_{name}", media_type="image/tiff")


@router.get("/events")
def events(start: str | None = None, end: str | None = None, min_months: int = Query(1, ge=1), limit: int = Query(100, ge=1, le=2000)):
    _month(start, "start"), _month(end, "end")
    p = FEATURES / "events.parquet"
    if not p.exists():
        raise HTTPException(404, "events not built")
    ev = pd.read_parquet(p)
    if start:
        ev = ev[ev["end"] >= start]
    if end:
        ev = ev[ev["start"] <= end]
    ev = ev[ev["n_months"] >= min_months].sort_values(["start", "peak_score"], ascending=[False, False]).head(limit)
    return {"definition": "DBSCAN clusters (haversine, eps 450 km, >= 3 cells) of multivariate-flagged cells, linked across consecutive "
                          "months; spatial co-occurrence only", "events": json.loads(ev.to_json(orient="records")), "note": NOTE}


@router.get("/compound")
def compound(month: str | None = None, pair: str | None = None, limit: int = Query(500, ge=1, le=5000)):
    _month(month)
    p = FEATURES / "compound_cooccurrence.parquet"
    if not p.exists():
        raise HTTPException(404, "not built")
    df = pd.read_parquet(p)
    if month:
        df = df[df["month"] == month]
    if pair:
        df = df[df["pair"] == pair]
    counts = df.groupby("pair").size().to_dict()
    return {"definition": "both variables of the pair >= moderate (|z| base-rate class, 1981-2010) in the configured directions",
            "counts": counts, "rows": json.loads(df.drop(columns=["idx"]).tail(limit).to_json(orient="records")),
            "causality": "co-occurrence only; no causal relation is implied", "note": NOTE}


@router.get("/sea-ice-extent")
def sea_ice_extent(start: str | None = None, end: str | None = None):
    p = OUTPUTS / "summaries" / "sea_ice_extent_anomalies_daily.csv"
    if not p.exists():
        raise HTTPException(404, "not built")
    df = pd.read_csv(p)
    if start:
        df = df[df["date"] >= start]
    if end:
        df = df[df["date"] <= end + "-31" if len(end) == 7 else end]
    return {"source": "NOAA/NSIDC SIC CDR v6, extent = area of cells with SIC >= 15 %", "baseline": "1991-2020, +-15 day window",
            "rows": json.loads(df.tail(4000).to_json(orient="records"))}


@router.get("/metrics")
def metrics():
    v, t = _json(METRICS / "validation.json"), (METRICS / "test.json")
    d = _json(MODELS / "decision.json")
    keep = lambda m: {k: m[k] for k in m if k.startswith(("pr_auc", "roc_auc", "recall", "flag_rate"))}  # noqa: E731
    out = {"evaluation": "SYNTHETIC injected anomalies (no labelled real anomalies exist); see docs/ml_task_04",
           "decision": {k: d[k] for k in ("selected_multivariate", "frozen_utc", "rank_sum", "rule")},
           "validation": {n: keep(m) for n, m in v["metrics"].items()}, "stability_seed7": v.get("stability_seed7"),
           "data_type": "evaluation"}
    if t.exists():
        tt = json.loads(t.read_text())
        out["test"] = {n: keep(m) for n, m in tt["metrics"].items()}
        out["test_evaluated_utc"] = tt["evaluated_utc"]
    for k in ("station_agreement", "reference_events"):
        p = METRICS / f"{k}.json"
        if p.exists():
            out[k] = json.loads(p.read_text())
    return out


@router.get("/data-coverage")
def data_coverage():
    q = _json(PROCESSED / "quality_report.json")
    meta = _json(FEATURES / "table.json")
    return {"grid": q["grid"], "variables": {k: {x: v[x] for x in ("first", "last", "days_with_data", "missing_days_inside_record", "range_ok")}
                                             for k, v in q["variables"].items()},
            "feature_table": meta, "update_note": "NCEP R1 (NOAA PSL) ends 2026-03-17; SIC CDR continues (latest daily file)",
            "missing_sources": ["ERA5 (needs CDS token)", "MERRA-2 (needs Earthdata login)", "Copernicus Marine (needs account)"]}
