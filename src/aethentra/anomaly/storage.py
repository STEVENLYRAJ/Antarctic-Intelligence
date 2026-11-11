"""ML-04 Phase 14: metadata store.

No database is configured in this repository (no Supabase project, URL or key). ML-04 therefore uses a local SQLite file
(data/processed/ml04/ml04.sqlite) with the schema suggested for Supabase/PostgreSQL. configs/ml04/supabase_schema.sql holds
the equivalent PostgreSQL DDL; it has NOT been applied to any remote project. Large rasters stay in NetCDF / GeoTIFF files;
the database only stores records and logical product ids (never filesystem paths).

Tables: models, datasets, anomaly_events, processing_runs.
anomaly_events holds (a) every multivariate cell-month at >= moderate severity of the selected detector and (b) univariate
cell-month anomalies at >= strong severity (1991-2020 baseline). All other values are in the NetCDF cube.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

import numpy as np
import pandas as pd

from .paths import MODELS, PROCESSED

DB = PROCESSED / "ml04.sqlite"
SCHEMA = """
CREATE TABLE IF NOT EXISTS models (id TEXT PRIMARY KEY, name TEXT, family TEXT, params TEXT, trained_utc TEXT,
  baseline_period TEXT, train_period TEXT, thresholds TEXT, selected INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, name TEXT, version TEXT, doi TEXT, coverage_start TEXT, coverage_end TEXT,
  resolution TEXT, access TEXT, licence TEXT, recorded_utc TEXT);
CREATE TABLE IF NOT EXISTS anomaly_events (id INTEGER PRIMARY KEY AUTOINCREMENT, model_id TEXT, variable TEXT, anomaly_type TEXT,
  severity TEXT, anomaly_score REAL, confidence TEXT, latitude REAL, longitude REAL, region TEXT, observation_timestamp TEXT,
  baseline_period TEXT, source_dataset TEXT, output_file_path TEXT, created_at TEXT,
  observed_value REAL, baseline_mean REAL, percentile REAL, method TEXT, top_variables TEXT, method_agreement INTEGER, data_tier TEXT);
CREATE INDEX IF NOT EXISTS ix_ev_time ON anomaly_events(observation_timestamp);
CREATE INDEX IF NOT EXISTS ix_ev_var ON anomaly_events(variable, severity);
CREATE INDEX IF NOT EXISTS ix_ev_region ON anomaly_events(region);
CREATE TABLE IF NOT EXISTS processing_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, started_utc TEXT, finished_utc TEXT, status TEXT,
  stages TEXT, details TEXT);
"""


def connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    return c


def log_run(started: str, status: str, stages: list[str], details: dict) -> None:
    with connect() as c:
        c.execute("INSERT INTO processing_runs (started_utc, finished_utc, status, stages, details) VALUES (?,?,?,?,?)",
                  (started, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), status, json.dumps(stages),
                   json.dumps(details, default=str)))


def register_models() -> int:
    d = json.loads((MODELS / "decision.json").read_text())
    rows = []
    for p in sorted(MODELS.glob("*.meta.json")):
        m = json.loads(p.read_text())
        n = p.name[:-10]
        rows.append((n, n, m.get("family", n), json.dumps(m.get("params", {})), m.get("trained_utc"), "1981-2010",
                     "1979-2010", json.dumps(m.get("thresholds")), int(n == d["selected_multivariate"])))
    with connect() as c:
        c.executemany("INSERT OR REPLACE INTO models VALUES (?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def register_datasets(quality: dict) -> None:
    from .paths import load
    s = load("data_sources")
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    v = quality["variables"]
    rows = [("ncep_r1_daily", s["ncep_r1"]["name"], "R1", s["ncep_r1"]["doi"], v["t2m"]["first"], v["t2m"]["last"], "2.5 deg / T62",
             s["ncep_r1"]["access"], s["ncep_r1"]["licence"], now),
            ("nsidc_g02202_v6", s["sea_ice"]["name"], "6", s["sea_ice"]["doi"], v["sic"]["first"], v["sic"]["last"], "25 km EPSG:3412",
             "public HTTPS (NOAA/NSIDC)", "public domain (NOAA)", now)]
    with connect() as c:
        c.executemany("INSERT OR REPLACE INTO datasets VALUES (?,?,?,?,?,?,?,?,?,?)", rows)


def write_events(t: pd.DataFrame, explained: pd.DataFrame, cube_ds, model_version: str) -> dict:
    """Replace anomaly_events with the current product version (idempotent for reruns)."""
    from .products import DATA_TIER, univariate_thresholds
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    sel = t["selected"].iloc[0]
    e = explained
    recs = [(model_version, "multivariate", "multivariate", r.sev, float(r.score), f"{int(r.agreement)}/4 methods", float(r.lat),
             float(r.lon), r.region, f"{r.month}-01", "1981-2010", "NCEP/NCAR R1 + NSIDC CDR v6", f"anom_{r.month}", now,
             None, None, None, sel, r.top_variables, int(r.agreement), None)
            for r in e.assign(sev=e[f"sev_{sel}"], score=e[f"score_{sel}"]).itertuples()]
    thr = univariate_thresholds()
    months = pd.DatetimeIndex(cube_ds["time"].values).strftime("%Y-%m")
    lat, lon = cube_ds["lat"].values, cube_ds["lon"].values
    from .products import regions
    reg = regions()
    for v in ["t2m", "slp", "wspd", "rhum", "prate", "tcdc", "z500", "sic"]:
        z = cube_ds[f"{v}_z"].values
        x, an, pc = cube_ds[v].values, cube_ds[f"{v}_anomaly"].values, cube_ds[f"{v}_percentile"].values
        k, i, j = np.nonzero(np.abs(np.nan_to_num(z)) >= thr[v][2])            # >= strong
        sev = np.where(np.abs(z[k, i, j]) >= thr[v][3], "extreme", "strong")
        for a, b, c_, s in zip(k, i, j, sev):
            zz = float(z[a, b, c_])
            typ = {"t2m": ("warm", "cold"), "sic": ("high_ice", "low_ice")}.get(v, ("high", "low"))[0 if zz > 0 else 1]
            recs.append((f"statistical_zscore_1991-2020", v, typ, s, zz, f"tier {DATA_TIER[v]}", float(lat[b]), float(lon[c_]), reg[b, c_],
                         f"{months[a]}-01", "1991-2020", "NCEP/NCAR R1" if v != "sic" else "NSIDC CDR v6", "anomalies_monthly_1991-2020.nc",
                         now, float(x[a, b, c_]), float(x[a, b, c_] - an[a, b, c_]), float(pc[a, b, c_]), "zscore", v, None, DATA_TIER[v]))
    with connect() as c:
        c.execute("DELETE FROM anomaly_events")
        c.executemany("INSERT INTO anomaly_events (model_id, variable, anomaly_type, severity, anomaly_score, confidence, latitude, "
                      "longitude, region, observation_timestamp, baseline_period, source_dataset, output_file_path, created_at, "
                      "observed_value, baseline_mean, percentile, method, top_variables, method_agreement, data_tier) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", recs)
        n = c.execute("SELECT variable, COUNT(*) FROM anomaly_events GROUP BY variable").fetchall()
    return dict(n)


def query(sql: str, params: tuple = ()) -> list[dict]:
    with connect() as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute(sql, params).fetchall()]
