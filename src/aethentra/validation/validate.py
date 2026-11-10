"""Data validation of the SIC cube and atmospheric predictors -> outputs/reports/data_validation/."""
from __future__ import annotations

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..config import OUTPUTS_DIR, ROOT, load
from ..features.atmosphere import Atmosphere
from ..preprocessing.cube import Cube
from ..visualization.style import BLUE_CMAP, INK2, MUTED, SERIES, apply_style

OUT = OUTPUTS_DIR / "reports" / "data_validation"
FIG = OUTPUTS_DIR / "figures" / "data_quality"


def _ranges(mask: pd.Series, dates: pd.Series) -> list[dict]:
    out, start = [], None
    for d, m in zip(dates, mask):
        if m and start is None:
            start = d
        if not m and start is not None:
            out.append({"start": str(start.date()), "end": str(prev.date()), "days": (prev - start).days + 1})
            start = None
        prev = d
    if start is not None:
        out.append({"start": str(start.date()), "end": str(prev.date()), "days": (prev - start).days + 1})
    return out


def run() -> dict:
    apply_style()
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    cube = Cube()
    cal = cube.calendar
    qa = pd.read_csv(cube.dir / "daily_qa.csv", parse_dates=["date"])
    pre = load("preprocessing")
    rep: dict = {"cube": {k: cube.meta[k] for k in ("start", "end", "shape", "days_present", "days_missing", "ocean_cells",
                                                     "ocean_area_mkm2", "cell_area_km2_range")}}
    rep["cube"]["inputs_md5_verified"] = int(sum(1 for i in cube.meta["inputs"] if i.get("md5_verified")))
    rep["cube"]["inputs"] = len(cube.meta["inputs"])
    rep["missing_day_ranges"] = _ranges(~cal.present, cal.date)
    empty = cal.present & (cal.valid_ocean_cells == 0)
    rep["days_in_file_but_all_ocean_missing"] = int(empty.sum())
    rep["all_missing_day_ranges"] = _ranges(empty, cal.date)
    rep["effective_gap_ranges"] = _ranges(~cal.present | empty, cal.date)
    q = qa[~qa.duplicate_day]
    rep["duplicate_days"] = int(qa.duplicate_day.sum())
    rep["ocean_invalid_gt100_total"] = int(q.ocean_invalid_gt100.sum())
    rep["ocean_missing_cells_total"] = int(q.ocean_missing.sum())
    frac_missing = q.ocean_missing / q.ocean_cells
    rep["days_with_ocean_missing_gt_1pct"] = int((frac_missing > 0.01).sum())
    rep["days_with_ocean_missing_gt_1pct_list"] = [str(d.date()) for d in q.date[frac_missing > 0.01]][:50]
    q = q.assign(year=q.date.dt.year, interp=q.ocean_temporally_interpolated / q.ocean_cells)
    rep["temporal_interpolation_fraction_by_year"] = q.groupby("year").interp.mean().round(4).to_dict()
    rep["no_input_flag_cells_total"] = int(q.ocean_no_input_flag.sum())
    rep["nonocean_cells_with_values_total"] = int(q.nonocean_with_value.sum())
    # mask consistency
    od = cube.grid["ocean_days"]
    n_days = cube.meta["days_present"]
    rep["mask"] = {"static_ocean_cells": int(cube.ocean.sum()),
                   "cells_ocean_on_some_but_lt99pct_days": int(((od > 0) & (od < 0.99 * n_days)).sum()),
                   "rule": "ocean if surface_type_mask == 50 on >= 99 % of present days"}
    # extent jumps
    c = cal[cal.present & (cal.valid_ocean_cells > 0)].copy()
    c["jump"] = c.extent_mkm2.diff().abs()
    thr = pre["qa"]["max_daily_extent_jump_mkm2"]
    jumps = c[c.jump > thr]
    rep["extent_jumps_gt_threshold"] = {"threshold_mkm2": thr, "count": int(len(jumps)),
                                        "dates": [f"{d.date()} ({j:.2f})" for d, j in zip(jumps.date, jumps.jump)][:40]}
    rep["extent_summary_mkm2"] = c.extent_mkm2.describe().round(3).to_dict()
    # independent comparison: NSIDC Sea Ice Index (G02135) daily extent
    g = ROOT / "data/raw/antarctic/external/nsidc_g02135_south/S_seaice_extent_daily_v4.0.csv"
    if g.exists():
        s = pd.read_csv(g, skipinitialspace=True, skiprows=[1])
        s["date"] = pd.to_datetime(dict(year=s.Year, month=s.Month, day=s.Day))
        j = c.merge(s[["date", "Extent"]], on="date")
        d = j.extent_mkm2 - j.Extent
        rep["comparison_g02135"] = {"matched_days": int(len(j)), "mean_diff_cdr_minus_g02135_mkm2": float(d.mean()),
                                    "std_diff_mkm2": float(d.std()), "pearson_r": float(np.corrcoef(j.extent_mkm2, j.Extent)[0, 1]),
                                    "note": "G02135 uses NASA Team (NSIDC-0051/0081) on the same 25 km grid; CDR v6 combines NASA Team and Bootstrap -> systematic differences expected."}
    # atmosphere
    atm = Atmosphere.load(cube.grid["lat"], cube.grid["lon"])
    if atm is not None:
        cov = atm.coverage()
        rng = {v: [float(np.nanmin(a)), float(np.nanmax(a)), int(np.isnan(a).sum())] for v, (t, a) in atm.data.items()}
        rep["atmosphere"] = {"coverage": cov, "min_max_nan": rng, "grid_lat_range": [float(atm.lat.min()), float(atm.lat.max())],
                             "sic_grid_lat_range": [float(cube.grid["lat"].min()), float(cube.grid["lat"].max())],
                             "sic_grid_inside_atm_grid": bool(cube.grid["lat"].max() <= atm.lat.max())}
    (OUT / "data_quality.json").write_text(json.dumps(rep, indent=2, default=str))

    # ---------------- figures
    fig, ax = plt.subplots(2, 1, figsize=(11, 5.5), sharex=True)
    ax[0].plot(cal.date, cal.valid_ocean_cells / cube.ocean.sum() * 100, color=SERIES[0], lw=0.6)
    for r in rep["effective_gap_ranges"]:
        ax[0].axvspan(pd.Timestamp(r["start"]), pd.Timestamp(r["end"]) + pd.Timedelta(days=1), color=SERIES[1], alpha=0.35, lw=0)
    ax[0].plot([], [], color=SERIES[1], lw=6, alpha=0.35, label="No valid data (missing or all-fill days)")
    ax[0].set_ylabel("Valid ocean cells (%)"); ax[0].set_title("Daily data coverage of the SIC record (NOAA/NSIDC CDR v6, SH 25 km)")
    ax[0].legend(loc="lower right")
    ax[1].plot(q.groupby("year").interp.mean().index.map(lambda y: pd.Timestamp(f"{y}-07-01")), q.groupby("year").interp.mean() * 100,
               color=SERIES[0], marker="o", ms=3)
    ax[1].set_ylabel("Temporally interpolated\nocean cells (%)"); ax[1].set_xlabel("Year")
    fig.savefig(FIG / "coverage.png", dpi=160, bbox_inches="tight"); plt.close(fig)

    wk = c.set_index("date").extent_mkm2.resample("7D").mean()
    fig, ax = plt.subplots(figsize=(11, 3.8))
    ax.plot(wk.index, wk.values, color=SERIES[0], lw=0.8, label="CDR v6 (this pipeline), 7-day mean")
    if g.exists():
        ax.plot(s.set_index("date").Extent.resample("7D").mean(), color=SERIES[1], lw=0.8, alpha=0.8, label="NSIDC Sea Ice Index G02135")
    ax.set_ylabel("Extent (10$^6$ km$^2$)"); ax.set_xlabel("Year"); ax.legend(loc="lower left", ncol=2)
    ax.set_title("Weekly Antarctic sea-ice extent from the preprocessed SIC grid vs independent index")
    fig.savefig(FIG / "weekly_extent.png", dpi=160, bbox_inches="tight"); plt.close(fig)

    fig, axs = plt.subplots(1, 2, figsize=(11, 5))
    for a, d in zip(axs, ["2023-02-20", "2023-09-10"]):
        f = cube.day(d)
        im = a.imshow(np.ma.masked_invalid(f), cmap=BLUE_CMAP, vmin=0, vmax=100)
        a.imshow(np.ma.masked_where(cube.ocean, np.ones_like(f)), cmap="Greys", vmin=0, vmax=3, alpha=0.6)
        a.set_title(f"Observed SIC {d}"); a.set_xticks([]); a.set_yticks([])
    fig.colorbar(im, ax=axs, shrink=0.8, label="Sea-ice concentration (%)")
    fig.savefig(FIG / "sic_maps_2023.png", dpi=160, bbox_inches="tight"); plt.close(fig)
    rep["figures"] = [str(p.relative_to(ROOT).as_posix()) for p in sorted(FIG.glob("*.png"))]
    (OUT / "data_quality.json").write_text(json.dumps(rep, indent=2, default=str))
    return rep
