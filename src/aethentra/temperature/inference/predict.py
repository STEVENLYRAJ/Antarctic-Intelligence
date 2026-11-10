"""ML-02 weekly forecast: load the frozen bundle, validate inputs, build features, predict, export NetCDF + JSON (+ layers).

    python scripts/ml02/predict.py [--issue-date YYYY-MM-DD] [--layers]
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from ..baselines.baselines import predict_baseline
from ..climatology.climatology import Climatology
from ..evaluation.metrics import region_masks
from ..features.build import FeatureContext
from ..labels.labels import Sigma, categorize, target_season
from ..models.anomaly_model import AnomalyModel
from ..paths import METRICS, MODELS, OUTPUTS, load
from ..preprocessing.cube import Cube

FINAL = MODELS / "final"
FORECAST_DIR = OUTPUTS / "forecasts"
CATS = ["strong_cold", "cold", "near_normal", "warm", "strong_warm"]
LIMITATIONS = [
    "Statistical forecast of the 7-day MEAN 2 m temperature anomaly learnt from reanalysis; it is NOT a numerical weather forecast "
    "and uses no forecast of the target-week atmosphere.",
    "Truth for training and evaluation is a reanalysis (gridded model-data blend), not direct observation; reanalysis 2 m temperature "
    "over the Antarctic plateau has known biases (strong surface inversions).",
    "25 km cells: station-scale and steep-topography effects (Peninsula, Transantarctic Mountains) are smoothed.",
    "Anomaly categories use training-period (1981-2010) sigma per cell and season; under a warming trend the 'warm' class becomes more frequent.",
    "Not reviewed by an independent Antarctic meteorology expert; not for operational or safety-critical use.",
]


@dataclass
class Bundle:
    model: AnomalyModel
    q_lo: AnomalyModel | None
    q_hi: AnomalyModel | None
    meta: dict
    ctx: FeatureContext
    alpha: dict
    test: dict | None


def load_bundle(directory: Path = FINAL) -> Bundle:
    if not (directory / "final_model.meta.json").exists():
        raise FileNotFoundError("No ML-02 final model; run scripts/ml02/train.py final")
    model = AnomalyModel.load(directory, "final_model")
    meta = model.meta
    src = meta["source"]
    q = sorted(directory.glob("final_q*.meta.json"))
    q_lo = AnomalyModel.load(directory, q[0].name[:-10]) if len(q) == 2 else None
    q_hi = AnomalyModel.load(directory, q[1].name[:-10]) if len(q) == 2 else None
    clim = Climatology.load(directory / f"t2m_climatology_{src}.npz")
    sigma = Sigma.load(directory / f"anomaly_sigma_{src}.npz")
    sic = None
    if any(f.startswith("sic_") for f in model.features):
        from ...preprocessing.cube import Cube as SicCube
        sic = SicCube()
    ctx = FeatureContext(Cube(src), clim, sigma, sic)
    alpha = json.loads((directory / f"damped_persistence_alpha_{src}.json").read_text())
    tp = METRICS / "test_final" / "summary.json"
    return Bundle(model, q_lo, q_hi, meta, ctx, alpha, json.loads(tp.read_text()) if tp.exists() else None)


@lru_cache(maxsize=1)
def cached_bundle() -> Bundle:
    return load_bundle()


def validate_inputs(b: Bundle, t: pd.Timestamp, F: dict) -> dict:
    cube = b.ctx.cube
    if tuple(cube.grid["shape"]) != (332, 316):
        raise ValueError("unexpected grid")
    hist = load("features")["issue"]["history_days"]
    if t > cube.dates[-1] or t - pd.Timedelta(days=hist - 1) < cube.dates[0]:
        raise ValueError(f"issue date {t.date()} outside {cube.dates[0].date()}..{cube.dates[-1].date()} minus {hist} days of history")
    cal = cube.calendar.set_index("date")
    t2m_days = int(cal.loc[t - pd.Timedelta(days=hist - 1):t, "t2m"].sum())
    valid = float(np.isfinite(F["anom_w1"]).mean())
    missing = [f for f in b.model.features if not np.isfinite(F[f]).any() and not f.startswith("sic_")]
    warn = []
    if valid < 0.99:
        warn.append(f"Only {valid:.1%} of cells have a last-week anomaly; other cells are not forecast.")
    if t2m_days < hist:
        warn.append(f"T2m history has {t2m_days}/{hist} days.")
    if missing:
        warn.append("Predictors unavailable for this issue date (set to missing; tree model handles NaN, skill may degrade): " + ", ".join(missing))
    if b.ctx.sic_cube is not None and t > b.ctx.sic_cube.dates[-1]:
        warn.append("Sea-ice observations end before the issue date; sea-ice predictors missing.")
    last = cal.index[cal["t2m"] & (cal.index <= t)].max()
    return {"latest_input_date": last.date(), "t2m_cells_valid_fraction": valid, "history_days_available_of_56": t2m_days,
            "predictors_missing": missing, "warnings": warn}


def run_forecast(issue_date=None, bundle: Bundle | None = None, write: bool = True, layers: bool = False):
    from .schema import InputQuality, RegionSummary, T2mForecastSummary, Uncertainty
    b = bundle or load_bundle()
    ctx, cube = b.ctx, b.ctx.cube
    t = pd.Timestamp(issue_date) if issue_date else cube.dates[cube.calendar["t2m"].to_numpy()][-1]
    F = ctx.features(t)
    iq = validate_inputs(b, t, F)
    h = load("features")["labels"]["horizon_days"]
    anom = b.model.predict_cells(F)
    clim_week = F["clim_target"]
    t2m = clim_week + anom
    sig = ctx.sigma.for_date(t)
    cat = categorize(anom, sig)
    pers = predict_baseline("persistence", F)
    unc = Uncertainty(validated=False, method="none", note="No interval provided.")
    lo = hi = None
    cov = (b.test or {}).get("interval_coverage")
    if b.q_lo is not None and cov:
        ok = abs(cov["empirical_coverage"] - cov["nominal_coverage"]) <= 0.05
        unc = Uncertainty(validated=ok, method="LightGBM quantile regression (q10, q90) of the weekly anomaly",
                          nominal_coverage=cov["nominal_coverage"], empirical_test_coverage=cov["empirical_coverage"],
                          note="Test-period coverage within 5 pp of nominal; interval exported." if ok else
                          "Test-period coverage differs from nominal by more than 5 pp; interval NOT exported.")
        if ok:
            lo, hi = b.q_lo.predict_cells(F), b.q_hi.predict_cells(F)
            lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)
    regions = []
    for name, m in region_masks(cube.grid).items():
        m = m & np.isfinite(anom)
        w = ctx.area[m]
        if not w.sum():
            continue
        wm = lambda v: float((v[m] * w).sum() / w.sum())  # noqa: E731
        z = anom[m] / sig[m]
        regions.append(RegionSummary(region=name, area_km2=float(w.sum()), forecast_mean_t2m_degC=wm(t2m), climatology_mean_t2m_degC=wm(clim_week),
                                     forecast_mean_anomaly_degC=wm(anom), last_week_observed_anomaly_degC=wm(F["anom_w1"]),
                                     fraction_warm_ge_1sigma=float((w * (z >= 1)).sum() / w.sum()),
                                     fraction_cold_le_minus1sigma=float((w * (z <= -1)).sum() / w.sum()),
                                     fraction_extreme_abs_ge_2sigma=float((w * (np.abs(z) >= 2)).sum() / w.sum())))
    src_name = {"era5": "ERA5 daily statistics (Copernicus C3S/ECMWF), doi:10.24381/cds.4991cf48",
                "ncep_r1": "NCEP/NCAR Reanalysis 1 daily means (NOAA PSL) - INTERIM substitute for ERA5"}[cube.source]
    fid = f"t2m7d_{t:%Y%m%d}_{b.meta.get('model_version', 'v1')}"
    tm = None
    if b.test:
        a = b.test["metrics"]["final_model"]["all"]
        tm = {k: a[k] for k in ("area_weighted_mae_degC", "area_weighted_rmse_degC", "acc_pattern_mean", "msss_vs_climatology")}
        tm["period"] = f"{b.test['first']}..{b.test['last']} issue dates"
    s = T2mForecastSummary(
        forecast_id=fid, issue_date=t.date(), issue_time_utc=dt.datetime.combine(t.date(), dt.time(23, 59, 59), dt.timezone.utc),
        target_start=(t + pd.Timedelta(days=1)).date(), target_end=(t + pd.Timedelta(days=h)).date(),
        units={"t2m": "degC", "anomaly": "degC", "category": "0 strong_cold .. 4 strong_warm (sigma bins)"},
        climatology_reference_period=list(map(int, ctx.clim.period)), model_version=b.meta.get("model_version", "unknown"),
        model_name=b.meta.get("selected_from", b.model.name), reanalysis_source=src_name, regions=regions, input_quality=InputQuality(**iq),
        uncertainty=unc, test_metrics_reference=tm,
        provenance={"inputs_through": str(iq["latest_input_date"]), "training_period": b.meta.get("train_period"),
                    "climatology": f"{ctx.clim.period[0]}-{ctx.clim.period[1]} daily, +-{ctx.clim.half} day smoothing",
                    "grid": "NSIDC polar stereographic 25 km (EPSG:3412), cells south of 60S", "target_season": target_season(t)},
        limitations=LIMITATIONS, generated_utc=dt.datetime.now(dt.timezone.utc).replace(microsecond=0))
    fields = {"t2m_forecast": t2m, "t2m_anomaly_forecast": anom, "anomaly_category": cat.astype(np.float32), "t2m_climatology_week": clim_week,
              "anomaly_persistence_reference": pers, "observed_anomaly_last_week": F["anom_w1"], "observed_t2m_last_week": F["t2m_w1"]}
    if lo is not None:
        fields.update(t2m_anomaly_q10=lo, t2m_anomaly_q90=hi)
    if write:
        s = export(s, fields, ctx)
        if layers:
            from .layers import export_layers
            export_layers(s, fields, ctx)
    return s, fields


DESCR = {"t2m_forecast": ("Forecast 7-day mean 2 m air temperature", "degC", "model_prediction"),
         "t2m_anomaly_forecast": ("Forecast 7-day mean 2 m temperature anomaly", "degC", "model_prediction"),
         "anomaly_category": ("Forecast anomaly category (0 strong cold <-2s, 1 cold, 2 near normal, 3 warm, 4 strong warm >=2s)", "1", "model_prediction"),
         "t2m_climatology_week": ("Climatological 7-day mean T2m of the target week", "degC", "climatology_reference"),
         "anomaly_persistence_reference": ("Persistence reference: anomaly of the issue day", "degC", "observation_derived_reference"),
         "observed_anomaly_last_week": ("Reanalysis 7-day mean anomaly ending at issue date", "degC", "reanalysis_observation"),
         "observed_t2m_last_week": ("Reanalysis 7-day mean T2m ending at issue date", "degC", "reanalysis_observation"),
         "t2m_anomaly_q10": ("Forecast anomaly 10th percentile (validated)", "degC", "model_prediction"),
         "t2m_anomaly_q90": ("Forecast anomaly 90th percentile (validated)", "degC", "model_prediction")}


def export(s, fields: dict, ctx):
    from ...config import ROOT, load as load01
    d = FORECAST_DIR / s.forecast_id
    d.mkdir(parents=True, exist_ok=True)
    g, cube = ctx.cube.grid, ctx.cube
    g01 = np.load(ROOT / load("preprocessing")["grid_source"])               # x/y/lat/lon of the full ML-01 grid
    dv = {k: (("y", "x"), cube.to_grid(v), {"long_name": DESCR[k][0], "units": DESCR[k][1], "data_type": DESCR[k][2],
                                            "grid_mapping": "crs", "coordinates": "lat lon"}) for k, v in fields.items()}
    dv["land_mask"] = (("y", "x"), cube.to_grid(g["land"].astype(np.float32)), {"long_name": "1 = Antarctic land/ice shelf (CDR mask), 0 = ocean"})
    dv["region"] = (("y", "x"), cube.to_grid(g["region"].astype(np.float32)), {"long_name": "0 southern ocean, 1 peninsula, 2 west, 3 east"})
    ds = xr.Dataset(dv, coords={"x": ("x", g01["x"], {"units": "m", "standard_name": "projection_x_coordinate"}),
                                "y": ("y", g01["y"], {"units": "m", "standard_name": "projection_y_coordinate"}),
                                "lat": (("y", "x"), g01["lat"].astype(np.float32), {"units": "degrees_north"}),
                                "lon": (("y", "x"), g01["lon"].astype(np.float32), {"units": "degrees_east"})})
    ds["crs"] = xr.DataArray(np.int32(0), attrs={"grid_mapping_name": "polar_stereographic", "latitude_of_projection_origin": -90.0,
                                                 "standard_parallel": -70.0, "straight_vertical_longitude_from_pole": 0.0,
                                                 "semi_major_axis": 6378273.0, "semi_minor_axis": 6356889.449,
                                                 "proj4text": load01("preprocessing")["grid"]["proj4"], "srid": "urn:ogc:def:crs:EPSG::3412"})
    ds.attrs = {"title": "AETHENTRA ML-02 weekly Antarctic 2 m temperature and anomaly forecast", "Conventions": "CF-1.8",
                "forecast_id": s.forecast_id, "issue_date": str(s.issue_date), "target_start": str(s.target_start), "target_end": str(s.target_end),
                "model_version": s.model_version, "data_type": "model_prediction (statistical, reanalysis-trained)", "source": s.reanalysis_source,
                "climatology_reference_period": f"{s.climatology_reference_period[0]}-{s.climatology_reference_period[1]}",
                "history": f"generated {s.generated_utc.isoformat()}"}
    nc = d / f"{s.forecast_id}.nc"
    ds.to_netcdf(nc, encoding={k: {"zlib": True, "complevel": 4} for k in fields})
    s.files = {"netcdf": nc.name, "summary_json": f"{s.forecast_id}.json"}
    (d / f"{s.forecast_id}.json").write_text(s.model_dump_json(indent=2))
    return s
