"""Figures generated exclusively from processed outputs / quality records.

Every figure is registered in figures_manifest.json with caption, dataset, variables and a
data-derived interpretation, which the Word report consumes verbatim.
"""
from __future__ import annotations

import json

import matplotlib
matplotlib.use("Agg")
import geopandas as gpd
import matplotlib.pyplot as plt
import netCDF4
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from .common import LOG, rel, write_json
from .config import EPSG_ANTARCTIC_PS, FIGURES_DIR, PROCESSED_DIR, QUALITY_DIR, RAW_DIR

# Reference validated categorical palette (fixed order) and text/surface tokens.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
OTHER = "#898781"
INK, INK2, MUTED, SURFACE, GRID = "#0b0b0b", "#52514e", "#898781", "#fcfcfb", "#e4e3df"
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
DIVERGE = ("#eb6834", "#f0efec", "#2a78d6")

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.titlecolor": INK, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.labelsize": 10,
    "font.size": 9.5, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False, "lines.linewidth": 2,
})

MANIFEST: list[dict] = []


def _q(did):
    try:
        return json.loads((QUALITY_DIR / f"{did}.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _save(fig, name, title, caption, dataset, variables, interpretation):
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    p = FIGURES_DIR / f"{name}.png"
    fig.savefig(p, dpi=180, bbox_inches="tight")
    plt.close(fig)
    MANIFEST.append({"file": rel(p), "name": name, "title": title, "caption": caption, "dataset": dataset,
                     "variables": variables, "interpretation": interpretation})
    LOG.info("Figure written: %s", rel(p))


def _limit(name, reason):
    MANIFEST.append({"file": None, "name": name, "title": name, "caption": None, "dataset": None,
                     "variables": None, "interpretation": None, "not_generated_reason": reason})


# --------------------------------------------------------------------------- 1 inventory
def fig_inventory(inv: pd.DataFrame):
    status_order = ["processed", "validated", "metadata_inspected", "partially_processed", "not_available", "unsupported", "failed"]
    c = inv.processing_status.value_counts().reindex(status_order).dropna()
    size = inv.groupby("dataset_id").size_bytes.sum().sort_values() / 1e6
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.4), gridspec_kw={"width_ratios": [1, 1.4]})
    a.barh(c.index[::-1], c.values[::-1], color=SERIES[0], height=0.6)
    for i, v in enumerate(c.values[::-1]):
        a.text(v + 0.3, i, f"{int(v)}", va="center", color=INK)
    a.set_xlabel("Number of files in DATAS/"); a.set_title("Files by processing status"); a.grid(axis="y", visible=False)
    b.barh(size.index, size.values, color=SERIES[0], height=0.6)
    b.set_xscale("log"); b.set_xlabel("Volume (MB, log scale)"); b.set_title("Data volume per dataset group"); b.grid(axis="y", visible=False)
    b.tick_params(axis="y", labelsize=8)
    _save(fig, "fig01_inventory_status", "Dataset inventory and processing status",
          f"Status of the {len(inv)} files discovered in DATAS/ (left) and volume per dataset group (right, log scale).",
          "metadata/antarctic_dataset_inventory.csv", "processing_status, size_bytes",
          f"{int(c.get('processed', 0))} files were processed into validated outputs, {int(c.get('validated', 0))} validated in native form "
          f"and {int(c.get('metadata_inspected', 0))} are metadata/documentation. GLIMS polygons dominate the volume "
          f"({size.max() / size.sum() * 100:.0f}% of {size.sum() / 1e3:.1f} GB).")


# --------------------------------------------------------------------------- 2-5 sea-ice extent
def fig_extent():
    p = PROCESSED_DIR / "sea_ice_extent" / "cmems_omi_si_extent_monthly.csv"
    if not p.exists():
        return _limit("fig02_omi_extent_timeseries", "OMI processed output missing")
    df = pd.read_csv(p, parse_dates=["time"])
    q = _q("cmems_omi_si_extent")
    ann = df.groupby("year").agg(m=("siextent_million_km2", "mean"), n=("siextent_million_km2", "count"))
    ann = ann[ann.n == 12]
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.plot(df.time, df.siextent_million_km2, color=SERIES[0], lw=1.2, label="Monthly mean extent")
    ax.plot(pd.to_datetime(ann.index.astype(str) + "-07-01"), ann.m, color=SERIES[1], lw=2, label="Annual mean (complete years)")
    miss = df[df.flag_missing]
    for t in miss.time:
        ax.axvline(t, color=MUTED, lw=0.8, ls=":")
    if len(miss):
        ax.plot([], [], color=MUTED, ls=":", label=f"Missing month ({len(miss)})")
    ax.set_ylabel("Sea-ice extent (10$^6$ km$^2$)"); ax.set_xlabel("Year")
    ax.set_title("Antarctic monthly sea-ice extent, 1979-2024 (CMEMS OMI, SIC > 15 %)")
    ax.legend(loc="upper left", ncol=3)
    tr = q["metrics"]["annual_mean_trend_million_km2_per_decade"]
    rmin = q["metrics"]["record_min"]
    _save(fig, "fig02_omi_extent_timeseries", "Antarctic monthly sea-ice extent time series",
          "Monthly-mean Southern Hemisphere sea-ice extent from the Copernicus Marine OMI product; orange line = mean of complete calendar years; "
          "dotted lines mark months stored as _FillValue.",
          "DATAS/ANTARCTIC_OMI_SI_extent_19790115_P20250505_R19792024.nc", "siextent (km^2, shown as 10^6 km^2)",
          f"Strong seasonal cycle between ~{df.siextent_million_km2.min():.1f} and ~{df.siextent_million_km2.max():.1f} million km^2. "
          f"The least-squares trend of the annual mean over 1979-2024 is {tr:+.3f} million km^2 per decade; the lowest monthly value "
          f"is {rmin['siextent_km2'] / 1e6:.2f} million km^2 ({rmin['time'][:7]}). Missing months: {', '.join(miss.time.dt.strftime('%Y-%m'))}.")

    # anomaly bars
    clim_ann = df.groupby("year").anomaly_km2.agg(["mean", "count"])
    clim_ann = clim_ann[clim_ann["count"] == 12]
    fig, ax = plt.subplots(figsize=(11, 3.8))
    v = clim_ann["mean"] / 1e6
    ax.bar(clim_ann.index, v, color=[DIVERGE[2] if x >= 0 else DIVERGE[0] for x in v], width=0.8)
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_ylabel("Annual-mean anomaly (10$^6$ km$^2$)"); ax.set_xlabel("Year")
    ax.set_title("Annual sea-ice extent anomaly vs 1979-2024 monthly climatology")
    ax.bar([], [], color=DIVERGE[2], label="Above climatology"); ax.bar([], [], color=DIVERGE[0], label="Below climatology")
    ax.legend(loc="lower left")
    low = v.nsmallest(3)
    _save(fig, "fig03_omi_extent_anomaly", "Annual sea-ice extent anomaly",
          "Mean of monthly anomalies (extent minus the file's monthly climatology) for each complete year.",
          "Processed: data/processed/antarctic/sea_ice_extent/cmems_omi_si_extent_monthly.csv", "anomaly_km2 (derived)",
          f"The three most negative years are {', '.join(f'{y} ({a:+.2f})' for y, a in low.items())} million km^2; "
          f"{int((v.loc[2016:] < 0).sum())} of the {int(v.loc[2016:].size)} complete years since 2016 are below the long-term climatology, "
          f"whereas {int((v.loc[:2015] < 0).sum())} of {int(v.loc[:2015].size)} years before 2016 were.")

    # seasonal cycle: OMI climatology vs NSIDC climatology
    c = pd.read_csv(PROCESSED_DIR / "sea_ice_extent" / "cmems_omi_si_extent_climatology.csv")
    ns = PROCESSED_DIR / "sea_ice_extent" / "nsidc_g02135_south_climatology.csv"
    nn = PROCESSED_DIR / "sea_ice_extent" / "nsidc_g02135_north_climatology.csv"
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.fill_between(c.month, (c.clim_mean_km2 - c.clim_std_km2) / 1e6, (c.clim_mean_km2 + c.clim_std_km2) / 1e6, color=SERIES[0], alpha=0.18, lw=0)
    ax.plot(c.month, c.clim_mean_km2 / 1e6, color=SERIES[0], marker="o", ms=5, label="CMEMS OMI 1979-2024 (±1 std)")
    txt = ""
    if ns.exists():
        s = pd.read_csv(ns)
        s["month"] = (pd.Timestamp("2001-01-01") + pd.to_timedelta(s.doy.clip(upper=365) - 1, unit="D")).dt.month
        sm = s.groupby("month").mean_extent_mkm2.mean()
        ax.plot(sm.index, sm.values, color=SERIES[1], marker="s", ms=5, label="NSIDC G02135 South 1981-2010")
        txt += f" NSIDC South 1981-2010 peaks at {sm.max():.2f} (month {sm.idxmax()}) and bottoms at {sm.min():.2f} (month {sm.idxmin()})."
    if nn.exists():
        n = pd.read_csv(nn)
        n["month"] = (pd.Timestamp("2001-01-01") + pd.to_timedelta(n.doy.clip(upper=365) - 1, unit="D")).dt.month
        nm = n.groupby("month").mean_extent_mkm2.mean()
        ax.plot(nm.index, nm.values, color=SERIES[2], marker="^", ms=5, ls="--", label="NSIDC G02135 NORTH 1981-2010 (Arctic, contrast)")
    ax.set_xticks(range(1, 13)); ax.set_xticklabels(list("JFMAMJJASOND"))
    ax.set_xlabel("Month"); ax.set_ylabel("Sea-ice extent (10$^6$ km$^2$)")
    ax.set_title("Seasonal cycle of sea-ice extent (climatologies)")
    ax.legend(loc="upper left", fontsize=8)
    _save(fig, "fig04_extent_seasonal_cycle", "Seasonal cycle of sea-ice extent",
          "Monthly climatology from the CMEMS OMI file (shaded ±1 standard deviation) compared with the NSIDC Sea Ice Index daily climatologies "
          "averaged to calendar months. The Northern Hemisphere file collected in DATAS/ is shown only as a contrast (out of Antarctic scope).",
          "OMI NetCDF; NSIDC G02135 S (downloaded) and N (DATAS/) climatology CSVs", "monthlyclimsiextent_mean/std; mean_extent_mkm2",
          f"Antarctic extent peaks in September ({c.clim_mean_km2.max() / 1e6:.2f} million km^2) and is lowest in February "
          f"({c.clim_mean_km2.min() / 1e6:.2f}), opposite in phase to the Arctic.{txt}")

    cmp = PROCESSED_DIR / "sea_ice_extent" / "comparison_omi_vs_nsidc_monthly.csv"
    if cmp.exists():
        d = pd.read_csv(cmp)
        d["t"] = pd.PeriodIndex(d.ym, freq="M").to_timestamp()
        qc = _q("comparison_omi_vs_nsidc_extent")["metrics"]
        fig, ax = plt.subplots(figsize=(11, 3.6))
        ax.plot(d.t, d.diff_mkm2, color=SERIES[0], lw=1.2, label="OMI minus NSIDC")
        ax.axhline(qc["mean_difference_omi_minus_nsidc_mkm2"], color=SERIES[1], lw=1.5, ls="--", label=f"Mean = {qc['mean_difference_omi_minus_nsidc_mkm2']:+.3f}")
        ax.axhline(0, color=INK2, lw=0.8)
        ax.set_ylabel("Difference (10$^6$ km$^2$)"); ax.set_xlabel("Year")
        ax.set_title("Cross-product check: CMEMS OMI vs NSIDC Sea Ice Index monthly extent")
        ax.legend(loc="upper left", ncol=2)
        _save(fig, "fig05_omi_vs_nsidc_difference", "OMI vs NSIDC monthly extent difference",
              "Difference between CMEMS OMI monthly extent and NSIDC G02135 daily extent averaged to months (months with >=10 daily values). "
              "Products are compared, not merged.",
              "Processed comparison_omi_vs_nsidc_monthly.csv", "siextent_million_km2, extent_mkm2",
              f"{qc['matched_months']} months matched; correlation r = {qc['pearson_r']:.4f}; mean difference "
              f"{qc['mean_difference_omi_minus_nsidc_mkm2']:+.3f} ± {qc['std_difference_mkm2']:.3f} million km^2 (max |diff| "
              f"{qc['max_abs_difference_mkm2']:.2f}). The products agree closely in variability; the offset reflects different SIC algorithms "
              "and land masks.")


# --------------------------------------------------------------------------- 6-7 DMI SIC
def fig_dmi():
    q = _q("cmems_dmi_asip_sic")
    path = next(RAW_DIR.glob("dmi_asip_seaice_mosaic_ant_*.nc"), None)
    if not q or not path:
        return _limit("fig06_dmi_sic_distribution", "DMI-ASIP file or quality record missing")
    vc = {int(k): v for k, v in q["metrics"]["sic_value_counts"].items() if int(k) >= 0}
    cls = q["metrics"]["cell_classes"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 4), gridspec_kw={"width_ratios": [1.4, 1], "wspace": 0.55})
    a.bar(list(vc.keys()), list(vc.values()), width=7, color=SERIES[0])
    a.set_yscale("log"); a.set_xlabel("Ice concentration (%)"); a.set_ylabel("Grid cells (log scale)")
    a.set_title("Valid ice-concentration values"); a.set_xticks(sorted(vc))
    labels = ["Valid 0 % (open water)", "Valid >0 % (ice)", "Fill, inside SAR swath", "Fill, outside SAR swath"]
    vals = [cls["sic_zero"], cls["sic_ice"], cls["fill_with_acq"], cls["fill_without_acq"]]
    b.barh(labels[::-1], np.array(vals[::-1]) / 1e6, color=[OTHER, OTHER, SERIES[0], SERIES[0]], height=0.6)
    for i, v in enumerate(vals[::-1]):
        b.text(v / 1e6 * 1.15 if v / 1e6 > 0.01 else 0.012, i, f"{v / cls['total'] * 100:.2f}%", va="center", color=INK, fontsize=8)
    b.set_xscale("log"); b.set_xlabel("Grid cells (millions, log scale)"); b.set_title("Cell classes (1 km grid)"); b.grid(axis="y", visible=False)
    ice_valid = cls["sic_zero"] + cls["sic_ice"]
    _save(fig, "fig06_dmi_sic_distribution", "DMI-ASIP sea-ice concentration distribution",
          "Exact counts of ice_concentration values in the 2023-02-02 DMI-ASIP mosaic (left) and classification of all 65.5 million grid cells (right). "
          "Classes are mutually exclusive.",
          path.name, "ice_concentration (%), acq_time (s)",
          f"The CNN product is quantised in 10 % steps ({len(vc)} distinct valid values). Only {ice_valid / cls['total'] * 100:.2f}% of the grid holds a "
          f"valid retrieval (one SAR day near the February minimum); of these {cls['sic_zero'] / ice_valid * 100:.1f}% are valid open-water zeros, "
          f"and 100 % is the most frequent ice value. {cls['fill_with_acq']:,} fill cells lie inside SAR swaths (probable land/ice-shelf mask). "
          "No out-of-range values were found.")

    with netCDF4.Dataset(path) as nc:
        s = 8
        sic = nc["ice_concentration"][0, ::s, ::s].astype(float).filled(np.nan)
        x, y = nc["x"][::s] / 1e3, nc["y"][::s] / 1e3
    cmap = LinearSegmentedColormap.from_list("blue", BLUE_RAMP)
    cmap.set_bad("#e4e3df")
    fig, ax = plt.subplots(figsize=(7.5, 7.2))
    m = ax.pcolormesh(x, y, np.ma.masked_invalid(sic), cmap=cmap, vmin=0, vmax=100, shading="auto")
    ax.set_aspect("equal"); ax.set_xlabel("x (km, polar stereographic)"); ax.set_ylabel("y (km, polar stereographic)")
    ax.set_title("DMI-ASIP sea-ice concentration, 2023-02-02 (preview, every 8th cell)"); ax.grid(False)
    cb = fig.colorbar(m, ax=ax, shrink=0.75); cb.set_label("Ice concentration (%)")
    _save(fig, "fig07_dmi_sic_map", "DMI-ASIP sea-ice concentration map preview",
          "Native polar-stereographic grid (true-scale latitude 70 S) subsampled every 8th cell for display only (no averaging). Grey = _FillValue "
          "(no SAR coverage or masked).",
          path.name, "ice_concentration (%)",
          "Valid retrievals are confined to the Sentinel-1 swaths acquired on 2023-02-02 (13:35-20:08 UTC); most of the Southern Ocean has no "
          "retrieval in this single daily file, so it cannot be used for circumpolar statistics without more days.")


# --------------------------------------------------------------------------- 8-10 GLIMS
def fig_glims():
    from .handlers_geospatial import GLIMS_GPKG
    if not GLIMS_GPKG.exists():
        return _limit("fig08_glims_map", "GLIMS GeoPackage missing")
    g = gpd.read_file(GLIMS_GPKG, layer="polygons", engine="pyogrio", columns=["glac_id", "line_type", "geog_area", "db_area", "geom_valid",
                                                                              "flag_area_mismatch_gt5pct"])
    gb = g[g.line_type == "glac_bound"].to_crs(EPSG_ANTARCTIC_PS)
    top = gb.geog_area.value_counts()
    keep = list(top.index[:5])
    gb["grp"] = gb.geog_area.where(gb.geog_area.isin(keep), "Other")
    fig, ax = plt.subplots(figsize=(8.5, 8))
    for i, k in enumerate(keep + ["Other"]):
        sub = gb[gb.grp == k]
        if len(sub):
            sub.plot(ax=ax, color=SERIES[i] if k != "Other" else OTHER, edgecolor=SURFACE, linewidth=0.1)
            ax.plot([], [], "s", color=SERIES[i] if k != "Other" else OTHER, ms=9, label=f"{k if len(k) <= 45 else k[:42] + '...'} ({len(sub):,})")
    ax.set_title("GLIMS glacier outlines, RGI region 19 (Antarctic Polar Stereographic)")
    ax.set_xlabel("x (m, EPSG:3031)"); ax.set_ylabel("y (m, EPSG:3031)")
    ax.legend(loc="lower left", fontsize=7.5, title="GLIMS geog_area", title_fontsize=8)
    _save(fig, "fig08_glims_map", "GLIMS Antarctic glacier outlines",
          "Glacier outlines (line_type = glac_bound) from the GLIMS download filtered to RGI first-order region 19, reprojected to EPSG:3031 for display "
          "only (stored data keep EPSG:4326). Coloured by the GLIMS geog_area attribute (top five + Other).",
          "DATAS/glims_download_33432/glims_polygons.shp", "geometry, geog_area, line_type",
          f"{len(gb):,} outlines; coverage is concentrated on the Antarctic Peninsula ({top.get('Antarctic Peninsula', 0):,}) and peripheral islands, "
          "with very sparse coverage of the main ice sheet - GLIMS is a glacier (not ice-sheet) inventory.")

    a = gb.db_area[gb.db_area > 0]
    fig, ax = plt.subplots(figsize=(9, 4))
    bins = np.logspace(np.log10(a.min()), np.log10(a.max()), 50)
    ax.hist(a, bins=bins, color=SERIES[0], edgecolor=SURFACE, linewidth=0.5)
    ax.set_xscale("log"); ax.set_xlabel("Glacier area db_area (km$^2$, log scale)"); ax.set_ylabel("Number of outlines")
    ax.set_title("Size distribution of Antarctic GLIMS glacier outlines")
    q = _q("glims_polygons")["metrics"]
    _save(fig, "fig09_glims_area_hist", "GLIMS glacier area distribution",
          "Histogram of the database-computed area (db_area, km^2) of RGI-19 glacier outlines with logarithmic bins.",
          "glims_polygons (RGI 19)", "db_area (km^2)",
          f"Median area {a.median():.2f} km^2, maximum {a.max():,.0f} km^2. Recomputed equal-area (EASE-Grid 2.0 South) areas match db_area with a "
          f"median relative difference of {q['computed_area_vs_db_area_median_rel_diff']:.1e}; {q['area_mismatch_gt5pct']} outlines differ by >5 % "
          f"(of which {int((g.flag_area_mismatch_gt5pct & ~g.geom_valid).sum())} have invalid geometry) and are flagged for review, not removed.")

    hp = PROCESSED_DIR / "glims" / "glims_hypsometry_50_antarctic_rgi19.parquet"
    if hp.exists():
        h = pd.read_parquet(hp)
        cols = [c for c in h.columns if c.startswith("area_km2_bin_")]
        tot = h[cols].sum()
        z = [int(c.split("_")[-1][:-1]) for c in cols]
        fig, ax = plt.subplots(figsize=(6.5, 6))
        ax.barh(z, tot.values, height=45, color=SERIES[0])
        ax.set_xlabel("Glacier area in bin (km$^2$)"); ax.set_ylabel("Elevation bin centre (m)")
        ax.set_title("Aggregate hypsometry of Antarctic GLIMS glaciers (50 m bins)")
        zmed = np.interp(tot.sum() / 2, tot.cumsum().values, z)
        _save(fig, "fig10_glims_hypsometry", "Aggregate glacier hypsometry",
              "Sum over all RGI-19 glaciers with hypsometry of the glacier area in each 50 m elevation bin.",
              "DATAS/glims_download_33432/glims_hypsometry_50.csv (Antarctic subset)", "area per elevation bin (km^2)",
              f"{len(h):,} glacier analyses, {tot.sum():,.0f} km^2 in total; half of the area lies below about {zmed:,.0f} m, "
              f"and the highest populated bin is {max(zi for zi, t in zip(z, tot) if t > 0):,} m.")


# --------------------------------------------------------------------------- 11 PGC tiles
def fig_pgc():
    p = PROCESSED_DIR / "pgc" / "ncalm_dv_lidar_tile_index.gpkg"
    if not p.exists():
        return _limit("fig11_pgc_tiles", "PGC tile index output missing")
    t = gpd.read_file(p, layer="tiles", engine="pyogrio").to_crs(EPSG_ANTARCTIC_PS)
    sites = t.site_name.value_counts()
    keep = list(sites.index[:7])
    t["grp"] = t.site_name.where(t.site_name.isin(keep), "Other")
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 6), gridspec_kw={"width_ratios": [1.3, 1], "wspace": 0.45})
    for i, k in enumerate(keep + ["Other"]):
        sub = t[t.grp == k]
        if len(sub):
            col = SERIES[i] if k != "Other" else OTHER
            sub.plot(ax=a, color=col, edgecolor=SURFACE, linewidth=0.2)
            a.plot([], [], "s", color=col, ms=8, label=f"{k} ({len(sub)})")
    a.set_title("NCALM Dry Valleys LiDAR tiles (EPSG:3031)"); a.set_xlabel("x (m)"); a.set_ylabel("y (m)")
    a.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, title="Site (tiles)", title_fontsize=7.5); a.tick_params(labelsize=7)
    s = t.groupby("site_name").agg(zmin=("z_min_m", "min"), zmax=("z_max_m", "max")).sort_values("zmin")
    b.hlines(range(len(s)), s.zmin, s.zmax, color=SERIES[0], lw=4)
    b.set_yticks(range(len(s))); b.set_yticklabels(s.index, fontsize=7)
    b.set_xlabel("Elevation (m, as reported in tile index)"); b.set_title("Elevation range per site"); b.grid(axis="y", visible=False)
    q = _q("pgc_ncalm_dv_lidar_tiles")["metrics"]
    _save(fig, "fig11_pgc_tiles", "PGC/NCALM Dry Valleys LiDAR tile index",
          "Tile footprints from the PGC-hosted KMZ index coloured by site (seven largest + Other) and the min-max elevation of each site.",
          "DATAS/NCALM_DV_LiDAR_LAS_Tile_index.kmz", "geometry, site_name, Z_Min, Z_Max, Pt_Count",
          f"{len(t):,} tiles in {len(sites)} sites with {q['total_points']:,} LiDAR points in total; elevations span "
          f"{q['elevation_range_m'][0]:,.0f} to {q['elevation_range_m'][1]:,.0f} m. Only the index is local - the LAS point clouds were not downloaded.")


# --------------------------------------------------------------------------- 12-13 cross-dataset quality
def fig_quality(recs):
    rows = []
    for r in recs:
        m = r.get("metrics", {})
        if m.get("missing_percent") is not None and r["status"] in ("processed", "validated", "partially_processed"):
            rows.append((r["dataset_id"], float(m["missing_percent"])))
    if rows:
        d = pd.DataFrame(rows, columns=["d", "p"]).sort_values("p")
        fig, ax = plt.subplots(figsize=(9, 0.38 * len(d) + 1.2))
        ax.barh(d.d, d.p, color=SERIES[0], height=0.6)
        for i, v in enumerate(d.p):
            ax.text(v + 0.8, i, f"{v:.2f}%", va="center", fontsize=8, color=INK)
        ax.set_xlim(0, 110); ax.set_xlabel("Missing / fill share of values (%)"); ax.set_title("Missing-value share by dataset")
        ax.grid(axis="y", visible=False)
        _save(fig, "fig12_missing_values", "Missing-value summary",
              "Share of missing, null or _FillValue entries per dataset as computed by each handler (definitions differ by format: "
              "grid cells for rasters, attribute cells for vectors/tables, time steps for series).",
              "data/reports/antarctic/quality/*.json", "missing_count, missing_percent",
              f"Highest share: {d.iloc[-1].d} ({d.iloc[-1].p:.1f}%). For the DMI-ASIP grid this is fill outside SAR coverage and for hypsometry "
              "empty elevation bins - structural, not lost measurements. Time series: "
              + ", ".join(f"{x.d} {x.p:.2f}%" for x in d.itertuples() if x.d in ("cmems_omi_si_extent", "nsidc_g02135_south_daily")) + ".")
    rows = []
    for r in recs:
        m = r.get("metrics", {})
        b, a = m.get("records_before"), m.get("records_after")
        if isinstance(b, (int, float)) and isinstance(a, (int, float)) and b > 0:
            rows.append((r["dataset_id"], b, a))
    if rows:
        d = pd.DataFrame(rows, columns=["d", "before", "after"]).sort_values("before")
        y = np.arange(len(d))
        fig, ax = plt.subplots(figsize=(9.5, 0.45 * len(d) + 1.4))
        ax.barh(y + 0.2, d.before, height=0.38, color=SERIES[0], label="Before (source records)")
        ax.barh(y - 0.2, d.after, height=0.38, color=SERIES[1], label="After (processed output)")
        ax.set_yticks(y); ax.set_yticklabels(d.d, fontsize=8); ax.set_xscale("log")
        ax.set_xlabel("Records / features (log scale)"); ax.set_title("Record counts before and after preprocessing"); ax.legend(loc="lower right")
        ax.grid(axis="y", visible=False)
        red = d[d.after < d.before]
        _save(fig, "fig13_before_after_counts", "Before-and-after record counts",
              "Records/features in the source versus the processed output. Reductions are scope subsets (Antarctic filter), never deletions of "
              "Antarctic observations; source files are unchanged.",
              "data/reports/antarctic/quality/*.json", "records_before, records_after",
              ("Counts are preserved for all tabular and time-series datasets. Reductions occur only where a global source was subset to the "
               f"Antarctic scope: {', '.join(f'{r.d} ({int(r.before):,} -> {int(r.after):,})' for r in red.itertuples())}."))


def fig_edsc():
    p = PROCESSED_DIR / "catalogs" / "nasa_edsc_collections.parquet"
    if not p.exists():
        return
    d = pd.read_parquet(p)
    c = d.provider.value_counts().sort_values()
    fig, ax = plt.subplots(figsize=(8, 0.35 * len(c) + 1.2))
    ax.barh(c.index, c.values, color=SERIES[0], height=0.6)
    ax.set_xlabel("Collections"); ax.set_title("NASA Earthdata Search export: collections per provider"); ax.grid(axis="y", visible=False)
    _save(fig, "fig14_edsc_providers", "Earthdata Search catalog providers",
          "Number of catalog records per data provider in the Earthdata Search collection export (metadata only).",
          "DATAS/edsc_collection_results_export.json", "provider",
          f"{len(d)} collection records from {d.provider.nunique()} providers; {int(d.mentions_antarctic.sum())} mention Antarctic operational modes or "
          f"titles; {int(d.is_ongoing.sum())} are ongoing (no end date). No science granules were downloaded.")


def make_all(recs, inv):
    MANIFEST.clear()
    for fn, args in [(fig_inventory, (inv,)), (fig_extent, ()), (fig_dmi, ()), (fig_glims, ()), (fig_pgc, ()),
                     (fig_quality, (recs,)), (fig_edsc, ())]:
        try:
            fn(*args)
        except Exception as e:
            LOG.error("Figure %s failed: %s", fn.__name__, e)
            _limit(fn.__name__, f"{type(e).__name__}: {e}")
    if not any(r["dataset_id"] == "cmems_sea_ice_drift" and r["status"] == "processed" for r in recs):
        _limit("sea_ice_drift_components", "No sea-ice drift data available locally (SEAICE_ANT_PHY_L3_MY_011_018 metadata only)")
    if not any(r["dataset_id"].startswith("era5_") and r["status"] == "processed" for r in recs):
        _limit("era5_temperature_pressure_wind", "No ERA5 output from API.py / PRESSUREAPI.py available locally")
    write_json(MANIFEST, FIGURES_DIR / "figures_manifest.json")
    return [m for m in MANIFEST]
