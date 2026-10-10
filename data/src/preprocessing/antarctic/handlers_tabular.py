"""Handlers for tabular datasets (CSV / JSON)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .common import add_output, finish, issue, new_record, num_summary, rel, step
from .config import PROCESSED_DIR

GLAC_ID_RE = re.compile(r"^G(\d{6})E(\d{5})([NS])$")


def parse_glims_id(gid: str):
    """GLIMS glacier IDs encode a location: G<lon*1000, 0-360 E><lat*1000><N|S>. Returns (lon, lat) or (nan, nan)."""
    m = GLAC_ID_RE.match(str(gid))
    if not m:
        return np.nan, np.nan
    lon = int(m.group(1)) / 1000.0
    lat = int(m.group(2)) / 1000.0 * (-1 if m.group(3) == "S" else 1)
    return (lon - 360.0 if lon > 180 else lon), lat


# --------------------------------------------------------------------------- NSIDC climatology
NSIDC_CLIM_COLUMNS = {"DOY": "doy", "Average Extent": "mean_extent_mkm2", "Std Deviation": "std_extent_mkm2",
                      "10th": "p10_extent_mkm2", "25th": "p25_extent_mkm2", "50th": "p50_extent_mkm2",
                      "75th": "p75_extent_mkm2", "90th": "p90_extent_mkm2"}


def read_nsidc_climatology(path: Path) -> tuple[pd.DataFrame, str]:
    with open(path, encoding="utf-8") as f:
        meta_line = f.readline().strip()
    df = pd.read_csv(path, skiprows=1, skipinitialspace=True, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns=NSIDC_CLIM_COLUMNS)
    for c in df.columns:
        df[c] = pd.to_numeric(df[c].str.strip(), errors="coerce")
    return df, meta_line


def process_nsidc_climatology(path: Path, dataset_id: str, hemisphere: str, related=(), external=False) -> dict:
    name = f"NSIDC Sea Ice Index v4 (G02135) {hemisphere} Hemisphere daily extent climatology 1981-2010"
    rec = new_record(dataset_id, name, [path, *related], "sea_ice_extent_climatology", "NSIDC / NOAA")
    if hemisphere == "Northern":
        rec["domain_relevance"] = "out_of_domain_arctic"
        issue(rec, "warning", "out_of_domain", "Northern Hemisphere (Arctic) climatology; the Southern Hemisphere file "
              "S_seaice_extent_climatology_1981-2010_v4.0.csv is the Antarctic equivalent", None)
    try:
        raw_lines = sum(1 for _ in open(path, encoding="utf-8"))
        df, meta = read_nsidc_climatology(path)
        step(rec, f"Parsed metadata line '{meta}' and {len(df)} data rows ({raw_lines} lines incl. 2 header lines)")
        step(rec, "Renamed columns to snake_case with explicit unit suffix (_mkm2 = 10^6 km^2 per NSIDC G02135 User Guide; "
                  "the file header itself carries no units)")
        rec["metrics"]["metadata_line"] = meta
        rec["metrics"]["columns_original"] = list(NSIDC_CLIM_COLUMNS.keys())
        rec["metrics"]["columns_processed"] = list(df.columns)
        rec["metrics"]["records_before"] = int(len(df))
        miss = df.isna().sum()
        rec["metrics"]["missing_by_column"] = {k: int(v) for k, v in miss.items()}
        rec["metrics"]["missing_count"] = int(miss.sum())
        rec["metrics"]["missing_percent"] = round(100 * miss.sum() / df.size, 3)
        dup = int(df.doy.duplicated().sum())
        expected = set(range(1, 367))
        missing_doy = sorted(expected - set(df.doy.dropna().astype(int)))
        rec["metrics"]["duplicate_doy"] = dup
        rec["metrics"]["missing_doy"] = missing_doy
        pcols = ["p10_extent_mkm2", "p25_extent_mkm2", "p50_extent_mkm2", "p75_extent_mkm2", "p90_extent_mkm2"]
        nonmono = int((np.diff(df[pcols].values, axis=1) < -1e-9).any(axis=1).sum())
        neg = int((df[[c for c in df.columns if c != "doy"]] < 0).sum().sum())
        rec["metrics"]["percentile_order_violations"] = nonmono
        rec["metrics"]["negative_values"] = neg
        rec["metrics"]["mean_extent_summary_mkm2"] = num_summary(df.mean_extent_mkm2)
        rec["metrics"]["seasonal_min"] = df.loc[df.mean_extent_mkm2.idxmin(), ["doy", "mean_extent_mkm2"]].to_dict()
        rec["metrics"]["seasonal_max"] = df.loc[df.mean_extent_mkm2.idxmax(), ["doy", "mean_extent_mkm2"]].to_dict()
        if dup:
            issue(rec, "error", "duplicate_record", "Duplicate day-of-year rows", dup)
        if missing_doy:
            issue(rec, "warning", "temporal_gap", f"Missing day-of-year values: {missing_doy}", len(missing_doy))
        if nonmono:
            issue(rec, "warning", "inconsistent_values", "Rows where percentiles are not non-decreasing (10th<=25th<=...<=90th)", nonmono)
        df.insert(0, "hemisphere", hemisphere)
        df["climatology_period"] = meta.split("=")[-1].strip() if "=" in meta else ""
        out = PROCESSED_DIR / "sea_ice_extent" / f"{dataset_id}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        chk = pd.read_csv(out)
        rec["validation"] = {"output_reopened": True, "row_count_preserved": len(chk) == rec["metrics"]["records_before"],
                             "no_duplicate_doy": dup == 0, "values_preserved": bool(np.allclose(chk.mean_extent_mkm2, df.mean_extent_mkm2))}
        rec["metrics"]["records_after"] = int(len(chk))
        rec["metrics"]["excluded_records"] = 0
        add_output(rec, out, "csv", "Tidy daily climatology with hemisphere label and unit-suffixed columns")
        if external:
            rec["notes"].append("Downloaded by this pipeline from the official NSIDC HTTPS archive (see provenance JSON); not part of DATAS/.")
        return finish(rec, "processed" if all(rec["validation"].values()) else "partially_processed")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")


def process_nsidc_daily(path: Path) -> dict:
    rec = new_record("nsidc_g02135_south_daily", "NSIDC Sea Ice Index v4 (G02135) Southern Hemisphere daily sea-ice extent",
                     [path], "sea_ice_extent_timeseries", "NSIDC / NOAA")
    try:
        df = pd.read_csv(path, skipinitialspace=True, dtype=str)
        df.columns = [c.strip() for c in df.columns]
        units_row = df.iloc[0].to_dict()
        df = df.iloc[1:].reset_index(drop=True)
        step(rec, f"Read {len(df)} data rows; second header row gives units {units_row}")
        rec["metrics"]["units_row"] = units_row
        rec["metrics"]["records_before"] = int(len(df))
        out = pd.DataFrame({
            "date": pd.to_datetime(dict(year=pd.to_numeric(df.Year), month=pd.to_numeric(df.Month), day=pd.to_numeric(df.Day)), errors="coerce"),
            "extent_mkm2": pd.to_numeric(df["Extent"], errors="coerce"),
            "missing_mkm2": pd.to_numeric(df["Missing"], errors="coerce"),
            "source_data": df["Source Data"].str.strip(),
        })
        bad_dates = int(out.date.isna().sum())
        dup = int(out.date.duplicated().sum())
        out = out.sort_values("date").reset_index(drop=True)
        gaps = out.date.diff().dt.days
        rec["metrics"]["time_coverage"] = [str(out.date.min().date()), str(out.date.max().date())]
        rec["metrics"]["invalid_dates"] = bad_dates
        rec["metrics"]["duplicate_dates"] = dup
        rec["metrics"]["sampling_interval_days_counts"] = {str(int(k)): int(v) for k, v in gaps.value_counts().items()}
        big = out.loc[gaps > 2, "date"]
        rec["metrics"]["gaps_gt_2_days"] = [{"after": str((d - pd.Timedelta(days=int(g))).date()), "resumes": str(d.date()), "days": int(g)}
                                            for d, g in zip(big, gaps[gaps > 2])]
        rec["metrics"]["missing_count"] = int(out.extent_mkm2.isna().sum())
        rec["metrics"]["missing_percent"] = round(100 * out.extent_mkm2.isna().mean(), 3)
        rec["metrics"]["rows_with_missing_area_gt0"] = int((out.missing_mkm2 > 0).sum())
        rec["metrics"]["extent_summary_mkm2"] = num_summary(out.extent_mkm2)
        neg = int((out.extent_mkm2 < 0).sum())
        if neg:
            issue(rec, "error", "invalid_value", "Negative extent", neg)
        if rec["metrics"]["gaps_gt_2_days"]:
            issue(rec, "warning", "temporal_gap", "Gaps > 2 days (the record is every-other-day before 1987-08; the "
                  "1987-12-03..1988-01-12 SSM/I outage is a known gap)", len(rec["metrics"]["gaps_gt_2_days"]))
        if rec["metrics"]["rows_with_missing_area_gt0"]:
            issue(rec, "info", "partial_coverage", "Days where the product reports non-zero missing area (retained, flagged)",
                  rec["metrics"]["rows_with_missing_area_gt0"])
        out["flag_missing_area"] = out.missing_mkm2 > 0
        out["date"] = out.date.dt.strftime("%Y-%m-%d")
        dst = PROCESSED_DIR / "sea_ice_extent" / "nsidc_g02135_south_daily.csv"
        out.to_csv(dst, index=False)
        chk = pd.read_csv(dst)
        rec["validation"] = {"output_reopened": True, "row_count_preserved": len(chk) == rec["metrics"]["records_before"],
                             "no_duplicate_dates": dup == 0, "no_invalid_dates": bad_dates == 0}
        rec["metrics"]["records_after"] = int(len(chk))
        rec["metrics"]["excluded_records"] = 0
        add_output(rec, dst, "csv", "Daily Southern Hemisphere extent with ISO dates and missing-area flag")
        rec["notes"].append("Downloaded by this pipeline from the official NSIDC HTTPS archive (see provenance JSON); not part of DATAS/.")
        return finish(rec, "processed" if all(rec["validation"].values()) else "partially_processed")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")


def compare_extent_products(omi_csv: Path, nsidc_daily_csv: Path) -> dict:
    """Cross-product comparison (NOT a merge): CMEMS OMI (OSI SAF SIC) vs NSIDC Sea Ice Index monthly means."""
    rec = new_record("comparison_omi_vs_nsidc_extent", "Cross-check: CMEMS OMI vs NSIDC G02135 Southern Hemisphere monthly extent",
                     [omi_csv, nsidc_daily_csv], "derived_comparison", "derived")
    try:
        omi = pd.read_csv(omi_csv)
        omi["ym"] = pd.PeriodIndex(pd.to_datetime(omi.time), freq="M")
        n = pd.read_csv(nsidc_daily_csv, parse_dates=["date"])
        n["ym"] = n.date.dt.to_period("M")
        nm = n.groupby("ym").agg(nsidc_mkm2=("extent_mkm2", "mean"), n_days=("extent_mkm2", "count"))
        j = omi.set_index("ym")[["siextent_million_km2"]].join(nm, how="inner").dropna()
        j = j[j.n_days >= 10]
        d = j.siextent_million_km2 - j.nsidc_mkm2
        rec["metrics"] = {
            "method": "NSIDC daily values averaged to calendar months (months with >=10 daily values kept); joined to OMI on year-month. "
                      "Products use different SIC algorithms (OSI SAF OSI-450/430 vs NASA Team), so differences are expected and the "
                      "datasets are NOT merged.",
            "matched_months": int(len(j)),
            "omi_months_unmatched": int(len(omi) - len(j)),
            "mean_difference_omi_minus_nsidc_mkm2": float(d.mean()),
            "std_difference_mkm2": float(d.std()),
            "max_abs_difference_mkm2": float(d.abs().max()),
            "pearson_r": float(np.corrcoef(j.siextent_million_km2, j.nsidc_mkm2)[0, 1]),
        }
        out = PROCESSED_DIR / "sea_ice_extent" / "comparison_omi_vs_nsidc_monthly.csv"
        j.assign(diff_mkm2=d).reset_index().assign(ym=lambda x: x.ym.astype(str)).to_csv(out, index=False)
        add_output(rec, out, "csv", "Month-matched OMI vs NSIDC extent and difference")
        step(rec, f"Matched {len(j)} months; mean OMI-NSIDC difference {d.mean():.3f} 10^6 km^2, r={rec['metrics']['pearson_r']:.4f}")
        rec["validation"] = {"output_reopened": len(pd.read_csv(out)) == len(j)}
        return finish(rec, "processed")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")


# --------------------------------------------------------------------------- GLIMS hypsometry
def process_glims_hypsometry(paths: list[Path], antarctic_ids: set[str]) -> dict:
    rec = new_record("glims_hypsometry", "GLIMS glacier hypsometry (area-elevation histograms)", paths,
                     "glacier_hypsometry_table", "GLIMS / NSIDC")
    out_dir = PROCESSED_DIR / "glims"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        per_file = {}
        ok = True
        for p in paths:
            df = pd.read_csv(p, dtype={"glac_id": str})
            bins = [c for c in df.columns if c not in ("glac_id", "analysis_id")]
            vals = df[bins].apply(pd.to_numeric, errors="coerce")
            lonlat = df.glac_id.map(parse_glims_id)
            lat = lonlat.map(lambda t: t[1])
            m = {
                "rows": int(len(df)), "bins": len(bins), "bin_width_m": int(float(bins[1]) - float(bins[0])) if len(bins) > 1 else None,
                "bin_centres_m": [float(bins[0]), float(bins[-1])],
                "empty_cells": int(vals.isna().sum().sum()), "empty_cells_percent": round(100 * vals.isna().sum().sum() / max(vals.size, 1), 3),
                "negative_area_cells": int((vals < 0).sum().sum()),
                "rows_all_empty_or_zero": int(((vals.fillna(0)) == 0).all(axis=1).sum()),
                "duplicate_glac_analysis": int(df.duplicated(["glac_id", "analysis_id"]).sum()),
                "glaciers": int(df.glac_id.nunique()),
                "unparseable_glac_id": int(lat.isna().sum()),
                "rows_south_of_60S_by_id": int((lat <= -60).sum()),
                "rows_in_rgi19_polygon_set": int(df.glac_id.isin(antarctic_ids).sum()),
                "total_area_km2_summary": num_summary(vals.sum(axis=1)),
            }
            per_file[p.name] = m
            step(rec, f"{p.name}: {m['rows']:,} rows x {m['bins']} bins ({m['bin_width_m']} m); "
                      f"{m['rows_in_rgi19_polygon_set']:,} rows belong to RGI region 19 glaciers")
            if m["negative_area_cells"]:
                issue(rec, "error", "invalid_value", f"{p.name}: negative bin areas", m["negative_area_cells"])
            if m["duplicate_glac_analysis"]:
                issue(rec, "warning", "duplicate_record", f"{p.name}: duplicate (glac_id, analysis_id)", m["duplicate_glac_analysis"])
            sub = df[df.glac_id.isin(antarctic_ids)].copy()
            if len(sub):
                keep = [c for c in bins if sub[c].notna().any()]
                sub = sub[["glac_id", "analysis_id", *keep]]
                sub.columns = ["glac_id", "analysis_id", *[f"area_km2_bin_{int(float(c))}m" for c in keep]]
                sub["total_area_km2"] = sub.filter(like="area_km2_bin_").sum(axis=1)
                sub["lon_from_id"] = sub.glac_id.map(lambda g: parse_glims_id(g)[0])
                sub["lat_from_id"] = sub.glac_id.map(lambda g: parse_glims_id(g)[1])
                dst = out_dir / f"{p.stem}_antarctic_rgi19.parquet"
                sub.to_parquet(dst, index=False)
                chk = pd.read_parquet(dst)
                ok &= len(chk) == m["rows_in_rgi19_polygon_set"]
                m["antarctic_rows_written"] = int(len(chk))
                m["antarctic_bins_written"] = len(keep)
                add_output(rec, dst, "parquet", f"Antarctic (RGI region 19) subset of {p.name}; wide format, empty upper bins dropped")
        rec["metrics"]["per_file"] = per_file
        rec["metrics"]["records_before"] = sum(m["rows"] for m in per_file.values())
        rec["metrics"]["records_after"] = sum(m.get("antarctic_rows_written", 0) for m in per_file.values())
        rec["metrics"]["excluded_records"] = rec["metrics"]["records_before"] - rec["metrics"]["records_after"]
        rec["metrics"]["exclusion_reason"] = "Outside the Antarctic scope (glac_id not in the GLIMS RGI region 19 polygon set); source file retained unchanged"
        cells = sum(m["rows"] * m["bins"] for m in per_file.values())
        rec["metrics"]["missing_count"] = sum(m["empty_cells"] for m in per_file.values())
        rec["metrics"]["missing_percent"] = round(100 * rec["metrics"]["missing_count"] / cells, 3) if cells else None
        rec["notes"].append("Hypsometry is stored as a wide histogram: empty bins mean the glacier does not span that elevation, "
                            "not a missing measurement; they were NOT filled with zero.")
        rec["validation"] = {"outputs_reopened_and_row_counts_match": bool(ok)}
        return finish(rec, "processed" if ok else "partially_processed")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")


# --------------------------------------------------------------------------- NASA Earthdata Search export
def normalize_edsc_record(r: dict) -> dict:
    plats = r.get("platforms") or []
    instr = [i for p in plats for i in (p.get("instruments") or [])]
    modes = sorted({m for i in instr for m in (i.get("operationalModes") or [])})
    pl = r.get("processingLevel") or {}
    return {
        "provider": r.get("provider"), "short_name": r.get("shortName"), "version": r.get("version"),
        "title": r.get("title"), "processing_level": pl.get("id"),
        "processing_level_description": pl.get("processingLevelDescription"),
        "platforms": "; ".join(p.get("shortName") or "" for p in plats),
        "platform_types": "; ".join(sorted({p.get("type") or "" for p in plats})),
        "instruments": "; ".join(i.get("shortName") or "" for i in instr),
        "operational_modes": "; ".join(modes),
        "time_start_original": r.get("timeStart"), "time_end_original": r.get("timeEnd"),
        "platforms_json": json.dumps(plats, ensure_ascii=False),   # nested structure preserved verbatim
        "record_type": r.get("__typename"),
    }


def process_edsc_catalog(json_path: Path, csv_path: Path) -> dict:
    rec = new_record("nasa_edsc_catalog", "NASA Earthdata Search collection-results export (catalog records)",
                     [json_path, csv_path], "catalog_metadata_table", "NASA Earthdata (CMR)")
    out_dir = PROCESSED_DIR / "catalogs"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        step(rec, f"JSON is syntactically valid; top-level type={type(data).__name__}, {len(data)} records")
        keys = {}
        for r in data:
            for k, v in r.items():
                keys.setdefault(k, set()).add(type(v).__name__)
        rec["metrics"]["json_schema"] = {k: sorted(v) for k, v in keys.items()}
        df = pd.DataFrame([normalize_edsc_record(r) for r in data])
        df["time_start_utc"] = pd.to_datetime(df.time_start_original, utc=True, errors="coerce")
        df["time_end_utc"] = pd.to_datetime(df.time_end_original, utc=True, errors="coerce")
        df["is_ongoing"] = df.time_end_original.isna()
        bad_start = int(df.time_start_utc.isna().sum() - df.time_start_original.isna().sum())
        end_before_start = int((df.time_end_utc < df.time_start_utc).sum())
        df["mentions_antarctic"] = df.operational_modes.str.contains("Antarctic", na=False) | df.title.str.contains("Antarctic", case=False, na=False)
        step(rec, "Flattened nested platforms/instruments into delimited columns; full nested JSON kept in platforms_json; "
                  "timestamps parsed to UTC while keeping original strings")
        csv = pd.read_csv(csv_path, dtype=str)
        rec["metrics"]["csv_rows"] = int(len(csv))
        rec["metrics"]["csv_columns"] = list(csv.columns)
        jkeys = set(zip(df.provider, df.short_name, df.version.astype(str)))
        ckeys = set(zip(csv["Data Provider"], csv["Short Name"], csv["Version"].astype(str)))
        rec["metrics"]["json_csv_key_overlap"] = len(jkeys & ckeys)
        rec["metrics"]["json_only_keys"] = sorted(map(list, jkeys - ckeys))[:20]
        rec["metrics"]["csv_only_keys"] = sorted(map(list, ckeys - jkeys))[:20]
        step(rec, f"CSV export has {len(csv)} rows; {len(jkeys & ckeys)} (provider, short_name, version) keys shared with JSON")
        dup_key = int(df.duplicated(["provider", "short_name", "version"]).sum())
        dup_full = int(df.drop(columns=["time_start_utc", "time_end_utc"]).duplicated().sum())
        miss = df.drop(columns=["platforms_json"]).isna().sum()
        rec["metrics"].update({
            "records_before": int(len(data)), "records_after": int(len(df)), "excluded_records": 0,
            "duplicate_keys": dup_key, "duplicate_full_rows": dup_full,
            "invalid_start_timestamps": bad_start, "end_before_start": end_before_start,
            "ongoing_collections": int(df.is_ongoing.sum()),
            "missing_by_column": {k: int(v) for k, v in miss.items() if v},
            "missing_count": int(miss.sum()),
            "missing_percent": round(100 * miss.sum() / miss.size / len(df), 3),
            "providers": df.provider.value_counts().to_dict(),
            "processing_levels": df.processing_level.value_counts(dropna=False).astype(int).to_dict(),
            "records_mentioning_antarctic": int(df.mentions_antarctic.sum()),
            "time_start_range": [str(df.time_start_utc.min()), str(df.time_start_utc.max())],
        })
        if dup_key:
            issue(rec, "warning", "duplicate_record", "Duplicate (provider, short_name, version)", dup_key)
        if end_before_start:
            issue(rec, "error", "invalid_value", "time_end before time_start", end_before_start)
        issue(rec, "info", "catalog_only", "These are catalog (metadata) records describing remote collections; no science data were downloaded", None)
        dst = out_dir / "nasa_edsc_collections.parquet"
        df.to_parquet(dst, index=False)
        df.drop(columns=["platforms_json"]).to_csv(out_dir / "nasa_edsc_collections.csv", index=False)
        chk = pd.read_parquet(dst)
        rec["validation"] = {"json_valid": True, "output_reopened": True, "row_count_preserved": len(chk) == len(data),
                             "nested_structure_preserved": bool(chk.platforms_json.map(lambda s: isinstance(json.loads(s), list)).all())}
        add_output(rec, dst, "parquet", "Normalised collection records incl. preserved nested platform JSON")
        add_output(rec, out_dir / "nasa_edsc_collections.csv", "csv", "Flat CSV view (without nested JSON column)")
        return finish(rec, "processed" if all(rec["validation"].values()) else "partially_processed")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")
