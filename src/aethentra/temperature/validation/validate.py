"""ML-02 data validation (Phase 2): raw files, cube, stations; figures in outputs/ml02/figures/data_quality/."""
from __future__ import annotations

import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ...config import ROOT, rel  # noqa: E402
from ...visualization.style import DIVERGING, SERIES, apply_style  # noqa: E402
from ..climatology.climatology import doy_index  # noqa: E402
from ..paths import FIGURES, OUTPUTS, load  # noqa: E402
from ..preprocessing.cube import Cube  # noqa: E402

TEMP_DIV = DIVERGING.reversed()          # blue = cold / negative, orange = warm / positive
FIG = FIGURES / "data_quality"


def check_raw(source: str) -> list[dict]:
    import xarray as xr
    sc = load("preprocessing")["sources"][source]
    out = []
    for var, c in sc.items():
        if var not in load("preprocessing")["variables"]:
            continue
        for p in sorted(ROOT.glob(c["glob"].replace("{year}", "*"))):
            with xr.open_dataset(p) as ds:
                v = c.get("var") if c.get("var") in ds.data_vars else list(ds.data_vars)[0]
                tn = "valid_time" if "valid_time" in ds.dims else "time"
                t = pd.to_datetime(ds[tn].values)
                a = ds[v].values
                latn = "latitude" if "latitude" in ds.dims else "lat"
                lat = ds[latn].values
                d = np.diff(t.values).astype("timedelta64[D]").astype(int) if len(t) > 1 else np.array([1])
                out.append({"file": rel(p), "variable": var, "var_in_file": v, "units": ds[v].attrs.get("units"), "n_time": len(t),
                            "first": str(t.min().date()), "last": str(t.max().date()), "duplicates": int(t.duplicated().sum()),
                            "gaps_gt_1day": int((d > 1).sum()), "non_monotonic": int((d < 1).sum()), "nan_fraction": float(np.isnan(a).mean()),
                            "min": float(np.nanmin(a)), "max": float(np.nanmax(a)), "lat_min": float(lat.min()), "lat_max": float(lat.max()),
                            "dims": {k: int(s) for k, s in ds[v].sizes.items()}})
    return out


def _map(ax, cube, v, cmap, vmin, vmax, title):
    g = cube.to_grid(v)
    r0, r1 = cube.grid["rows"].min(), cube.grid["rows"].max() + 1
    c0, c1 = cube.grid["cols"].min(), cube.grid["cols"].max() + 1
    im = ax.imshow(g[r0:r1, c0:c1], cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
    land = cube.to_grid(cube.grid["land"].astype(float), fill=np.nan)[r0:r1, c0:c1]
    ax.contour(np.nan_to_num(land), levels=[0.5], colors="#0b0b0b", linewidths=0.5)
    ax.set_title(title); ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    return im


def run(source: str | None = None) -> dict:
    apply_style()
    FIG.mkdir(parents=True, exist_ok=True)
    cube = Cube(source)
    raw = check_raw(cube.source)
    res = {"source": cube.source, "raw_files": len(raw), "raw_issues": [r for r in raw if r["duplicates"] or r["gaps_gt_1day"] or r["non_monotonic"]],
           "raw_units": sorted({f"{r['variable']}: {r['units']}" for r in raw}), "cube": cube.meta["variables"],
           "orography_source": cube.meta.get("orography_source"), "t2m_domain_mean_jump_days": cube.meta.get("t2m_domain_mean_jump_days", []),
           "n_cells": cube.n, "n_land": int(cube.grid["land"].sum()), "calendar_days": len(cube.dates)}
    (OUTPUTS / "reports").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(raw).to_csv(OUTPUTS / "reports" / f"raw_file_checks_{cube.source}.csv", index=False)
    # --- coverage heatmap (variable x year, fraction of days present)
    cal = cube.calendar.set_index("date")
    cov = cal.groupby(cal.index.year).mean().T
    res["coverage_by_year"] = cov.round(4).to_dict()
    fig, ax = plt.subplots(figsize=(11, 2.6))
    im = ax.imshow(cov.to_numpy(float), aspect="auto", cmap="Blues", vmin=0, vmax=1)
    ax.set_yticks(range(len(cov.index)), cov.index); ax.set_xticks(range(0, len(cov.columns), 5), cov.columns[::5]); ax.grid(False)
    ax.set_title(f"Fraction of days present per variable and year ({cube.source})"); fig.colorbar(im, ax=ax, fraction=0.02)
    fig.savefig(FIG / "coverage_heatmap.png", dpi=140, bbox_inches="tight"); plt.close(fig)
    # --- domain-mean daily series & seasonal cycle by region
    qa = pd.read_csv(cube.dir / "daily_qa.csv", parse_dates=["date"])
    fig, ax = plt.subplots(figsize=(11, 3.2))
    ax.plot(qa.date, qa.t2m_mean, color=SERIES[0], lw=0.4)
    ax.plot(qa.date, qa.t2m_mean.rolling(365, center=True).mean(), color=SERIES[1], lw=1.6, label="365-day running mean")
    ax.set_ylabel("°C"); ax.set_title("Domain-mean (south of 60°S, unweighted cells) daily 2 m temperature"); ax.legend()
    fig.savefig(FIG / "domain_mean_t2m.png", dpi=140, bbox_inches="tight"); plt.close(fig)
    yrs = cube.dates[(cube.dates.year >= 1981) & (cube.dates.year <= 2010)]
    i0 = cube.idx(yrs[0])
    sc = cube.meta["variables"]["t2m"]["scale"]
    land, area = cube.grid["land"], cube.grid["area_km2"]
    regions = {"Southern Ocean": cube.grid["region"] == 0, "Antarctic Peninsula": cube.grid["region"] == 1,
               "West Antarctica": cube.grid["region"] == 2, "East Antarctica": cube.grid["region"] == 3}
    raw_t = cube.raw("t2m")
    d_idx = doy_index(yrs)
    reg_ts = {nm: np.zeros(len(yrs)) for nm in regions}
    sums = {k: np.zeros(cube.n) for k in ("ann", "djf", "jja")}
    cnts = {k: 0 for k in sums}
    samples = []
    dm = {v: np.zeros(len(yrs)) for v in cube.variables}
    for c0 in range(0, len(yrs), 365):                       # stream one year at a time (memory)
        c1 = min(c0 + 365, len(yrs))
        q = np.asarray(raw_t[i0 + c0:i0 + c1], np.float32) * sc
        for nm, m in regions.items():
            reg_ts[nm][c0:c1] = (q[:, m] * area[m]).sum(1) / area[m].sum()
        mon = yrs[c0:c1].month
        for k, sel in (("ann", np.ones(c1 - c0, bool)), ("djf", np.isin(mon, [12, 1, 2])), ("jja", np.isin(mon, [6, 7, 8]))):
            sums[k] += q[sel].sum(0); cnts[k] += int(sel.sum())
        samples.append(q[::15])
        for v in cube.variables:
            r = np.asarray(cube.raw(v)[i0 + c0:i0 + c1], np.float32)
            r = np.where(r == -32768, np.nan, r * cube.meta["variables"][v]["scale"])
            dm[v][c0:c1] = np.nanmean(r[:, land], 1)
    fig, ax = plt.subplots(figsize=(8, 4))
    seas = {}
    for i, nm in enumerate(regions):
        s = pd.Series(reg_ts[nm]).groupby(d_idx).mean()
        seas[nm] = {"min": float(s.min()), "max": float(s.max()), "mean": float(s.mean())}
        ax.plot(s.index, s.values, color=SERIES[i], label=nm)
    ax.set_xlabel("day of year"); ax.set_ylabel("°C"); ax.set_title("Seasonal cycle of area-mean 2 m temperature, 1981–2010"); ax.legend(ncol=2)
    fig.savefig(FIG / "seasonal_cycle_regions.png", dpi=140, bbox_inches="tight"); plt.close(fig)
    res["seasonal_cycle_1981_2010"] = seas
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.4))
    for ax, (k, ttl) in zip(axs, (("ann", "Annual"), ("djf", "DJF"), ("jja", "JJA"))):
        im = _map(ax, cube, sums[k] / cnts[k], "cividis", -65, 0, f"{ttl} mean T2m 1981–2010")
    fig.colorbar(im, ax=axs, fraction=0.015, label="°C")
    fig.savefig(FIG / "t2m_maps_1981_2010.png", dpi=140, bbox_inches="tight"); plt.close(fig)
    smp = np.concatenate(samples)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for i, (nm, m) in enumerate((("land / ice sheet", land), ("ocean", ~land))):
        ax.hist(smp[:, m].ravel(), bins=120, color=SERIES[i], alpha=0.6, density=True, label=nm)
    ax.set_xlabel("daily-mean T2m (°C)"); ax.set_title("Distribution of daily T2m, 1981–2010 (every 15th day)"); ax.legend()
    fig.savefig(FIG / "t2m_distribution.png", dpi=140, bbox_inches="tight"); plt.close(fig)
    res["t2m_1981_2010_percentiles"] = {f"p{p}": float(np.percentile(smp, p)) for p in (0.1, 1, 50, 99, 99.9)}
    del smp, samples
    valid_days = np.zeros(cube.n, np.int64)
    for c0 in range(0, len(cube.dates), 365):
        valid_days += (np.asarray(raw_t[c0:c0 + 365]) != -32768).sum(0)
    fig, ax = plt.subplots(figsize=(5, 4.4))
    im = _map(ax, cube, valid_days / len(cube.dates), "Blues", 0.9, 1.0, "Fraction of valid days per cell")
    fig.colorbar(im, ax=ax, fraction=0.04)
    fig.savefig(FIG / "spatial_coverage.png", dpi=140, bbox_inches="tight"); plt.close(fig)
    res["cells_with_any_missing_day"] = int((valid_days < len(cube.dates)).sum())
    if len(cube.variables) > 1:
        cm = pd.DataFrame({v: pd.Series(x) - pd.Series(x).groupby(d_idx).transform("mean") for v, x in dm.items()}).corr()
        res["domain_mean_anomaly_correlation"] = cm.round(3).to_dict()
        fig, ax = plt.subplots(figsize=(4.8, 4))
        im = ax.imshow(cm, cmap=TEMP_DIV, vmin=-1, vmax=1); ax.grid(False)
        ax.set_xticks(range(len(cm)), cm.index, rotation=45); ax.set_yticks(range(len(cm)), cm.index)
        for i in range(len(cm)):
            for j in range(len(cm)):
                ax.text(j, i, f"{cm.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8)
        ax.set_title("Correlation of daily anomalies\n(land-mean, 1981–2010)")
        fig.savefig(FIG / "variable_correlation.png", dpi=140, bbox_inches="tight"); plt.close(fig)
    out = OUTPUTS / "reports" / f"data_quality_{cube.source}.json"
    out.write_text(json.dumps(res, indent=1, default=str))
    return res


def station_inventory() -> pd.DataFrame:
    from ..evaluation.stations import _ghcnd, _zenodo
    zen = _zenodo()
    allst = {**zen, **_ghcnd({v["ghcnd_id"] for v in zen.values()})}
    rows = []
    for k, v in allst.items():
        s = v["series"].dropna()
        rows.append({"station": k, "name": v["name"], "lat": v["lat"], "lon": v["lon"], "elev_m": v["elev_m"], "first": str(s.index.min().date()),
                     "last": str(s.index.max().date()), "n_days": len(s), "frac_days_2018_2025": float(s["2018":"2025"].size / 2922),
                     "min": float(s.min()), "max": float(s.max())})
    df = pd.DataFrame(rows)
    (OUTPUTS / "reports").mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUTS / "reports" / "station_inventory.csv", index=False)
    return df
