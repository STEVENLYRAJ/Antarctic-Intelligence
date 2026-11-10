"""Generate a weekly (7-day mean) SIC forecast from the latest valid observations.

    python -m aethentra.inference.predict [--issue-date YYYY-MM-DD]      (with src/ on PYTHONPATH)
    python scripts/predict.py [--issue-date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

import numpy as np
import pandas as pd

from ..baselines.baselines import predict_baseline
from ..config import load
from .export_forecast import export
from .model_loader import Bundle, load_bundle
from .prediction_schema import ForecastSummary, InputQuality, SectorSummary, Uncertainty

LIMITATIONS = [
    "Statistical forecast of the 7-day MEAN concentration; it does not resolve day-to-day variability.",
    "Trained on the NOAA/NSIDC passive-microwave CDR v6 (25 km); inherits its biases (melt-pond / thin-ice underestimation, coastal land spill-over).",
    "Atmospheric predictors are PAST-week NCEP/NCAR R1 means (interim substitute for ERA5); no weather forecast of the target week is used.",
    "Extent uses the 15 % threshold on the forecast 7-day-mean field; it is not identical to the mean of daily extents.",
    "Not reviewed by an independent sea-ice expert; not for operational navigation.",
]


def validate_inputs(b: Bundle, t: pd.Timestamp) -> tuple[InputQuality, dict]:
    cube, ocean = b.ctx.cube, b.ctx.ocean
    if cube.sic.shape[1:] != (332, 316):
        raise ValueError(f"Unexpected grid shape {cube.sic.shape[1:]}")
    if t > cube.dates[-1] or t < cube.dates[0] + pd.Timedelta(days=56):
        raise ValueError(f"Issue date {t.date()} outside available record {cube.dates[0].date()}..{cube.dates[-1].date()} (needs 56 days of history)")
    F = b.ctx.features(t)
    hist = cube.window(t, 56)
    days_hist = int(np.isfinite(hist[:, ocean]).any(axis=1).sum())
    cov = float(np.isfinite(F["sic_d0"][ocean]).mean())
    warn = []
    if cov < 0.95:
        warn.append(f"Only {cov:.1%} of ocean cells have an observation <= 3 days old.")
    atm_days, atm_used = None, False
    if b.ctx.atmos is not None:
        _, atm_days = b.ctx.atmos.window_mean_coarse("air", t, 7)
        atm_used = atm_days >= 5
        if not atm_used:
            warn.append(f"Atmospheric inputs available for {atm_days}/7 days; atmospheric features set to missing.")
            for k in [f for f in F if f.split("_")[0] in ("air", "uwnd", "vwnd", "slp", "wspd")]:
                F[k] = np.full_like(F[k], np.nan)
    last_obs = cube.calendar[cube.calendar.present & (cube.calendar.date <= t)].date.max().date()
    if (t.date() - last_obs).days > 0:
        warn.append(f"Latest observation is {last_obs}, {(t.date() - last_obs).days} day(s) before the issue date.")
    return InputQuality(latest_observation_date=last_obs, persistence_coverage_fraction=cov, history_days_available_of_56=days_hist,
                        atmosphere_days_available_of_7=atm_days, atmosphere_used=atm_used, warnings=warn), F


def run_forecast(issue_date=None, bundle: Bundle | None = None, write: bool = True) -> tuple[ForecastSummary, dict]:
    b = bundle or load_bundle()
    cube = b.ctx.cube
    t = pd.Timestamp(issue_date) if issue_date else cube.calendar[cube.calendar.present].date.max()
    iq, F = validate_inputs(b, t)
    active = b.ctx.active_mask(F)
    model = b.model
    if not iq.atmosphere_used:
        if b.fallback is None:
            raise ValueError("Atmospheric inputs unavailable and no SIC-only fallback model exists")
        model = b.fallback
        iq.warnings.append("Using the SIC-only fallback model (declared before test; its test metrics are reported separately).")
    pred, phys = model.predict_grid(F, active)
    pred[~b.ctx.ocean] = np.nan
    persist = predict_baseline("persistence", F); persist[~b.ctx.ocean] = np.nan
    clim = predict_baseline("climatology", F); clim[~b.ctx.ocean] = np.nan
    lo = hi = None
    unc = Uncertainty(validated=False, method="none", note="No interval provided.")
    tm = b.test_metrics or {}
    cov = tm.get("interval_coverage")
    if b.q_lo is not None and cov:
        ok = abs(cov["empirical_coverage"] - cov["nominal_coverage"]) <= 0.05
        unc = Uncertainty(validated=ok, method="LightGBM quantile regression (q10, q90) on the residual",
                          nominal_coverage=cov["nominal_coverage"], empirical_test_coverage=cov["empirical_coverage"],
                          note=("Empirical 2021-2025 coverage within 5 pp of nominal; interval exported." if ok else
                                "Empirical coverage differs from nominal by > 5 pp; interval NOT exported."))
        if ok and not iq.atmosphere_used:
            unc = Uncertainty(validated=False, method=unc.method, nominal_coverage=unc.nominal_coverage, empirical_test_coverage=unc.empirical_test_coverage,
                              note="Interval models use atmospheric inputs, which are unavailable for this issue date; interval NOT exported.")
        elif ok:
            lo, _ = b.q_lo.predict_grid(F, active)
            hi, _ = b.q_hi.predict_grid(F, active)
            lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)
            lo[~b.ctx.ocean] = hi[~b.ctx.ocean] = np.nan
    ctx = b.ctx
    sectors = []
    for s, nm in enumerate(ctx.sector_names):
        m = ctx.sector == s
        e = ctx.extent(pred, m) * 1e6
        a = float((ctx.area * np.where(ctx.ocean & m & (pred >= 15), pred, 0) / 100).sum())
        sectors.append(SectorSummary(sector=nm, extent_km2=e, area_km2=a, persistence_extent_km2=ctx.extent(persist, m) * 1e6))
    h = load("features")["labels"]["horizon_days"]
    fid = f"sic7d_{t:%Y%m%d}_{b.meta.get('model_version', 'v1')}"
    summary = ForecastSummary(
        forecast_id=fid, issue_date=t.date(), issue_time_utc=dt.datetime.combine(t.date(), dt.time(23, 59, 59), dt.timezone.utc),
        target_start=(t + pd.Timedelta(days=1)).date(), target_end=(t + pd.Timedelta(days=h)).date(),
        extent_km2=ctx.extent(pred) * 1e6, area_km2=float((ctx.area * np.where(ctx.ocean & (pred >= 15), pred, 0) / 100).sum()),
        persistence_extent_km2=ctx.extent(persist) * 1e6, climatology_extent_km2=ctx.extent(clim) * 1e6,
        sectors=sectors, model_version=b.meta.get("model_version", "unknown"), model_name=(b.meta.get("selected_from", b.model.name) if model is b.model else "final_model_sic_only (fallback)"),
        input_quality=iq, uncertainty=unc,
        provenance={"sic_source": "NOAA/NSIDC CDR of Passive Microwave SIC v6 (G02202), doi:10.7265/b18j-z797",
                    "sic_inputs_through": str(iq.latest_observation_date),
                    "atmosphere_source": "NCEP/NCAR Reanalysis 1 daily means (NOAA PSL)" if iq.atmosphere_used else
                    "not available for this issue date (NCEP R1 dailies at NOAA PSL end 2026-03-17 at retrieval time)",
                    "model_training_period": b.meta.get("train_period"), "physical_checks": phys,
                    "climatology_period": list(ctx.clim.period)},
        limitations=LIMITATIONS, generated_utc=dt.datetime.now(dt.timezone.utc).replace(microsecond=0))
    fields = {"sic_forecast": pred, "sic_persistence": persist, "sic_climatology": clim}
    if lo is not None:
        fields.update(sic_forecast_q10=lo, sic_forecast_q90=hi)
    if write:
        summary = export(summary, fields, ctx)
    return summary, fields


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue-date")
    ap.add_argument("--no-layers", action="store_true", help="skip frontend layer export")
    a = ap.parse_args()
    b = load_bundle()
    s, fields = run_forecast(a.issue_date, bundle=b)
    if not a.no_layers:
        from ..visualization.layers import export_layers
        export_layers(s, fields, b.ctx)
    print(json.dumps(json.loads(s.model_dump_json()), indent=2)[:4000])


if __name__ == "__main__":
    main()
