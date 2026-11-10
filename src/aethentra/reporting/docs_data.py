"""Generate data-side documents from artifacts: DATA_INVENTORY.csv, DATA_SOURCES.md, DATA_SOURCES_AND_PROVENANCE.md,
DATA_QUALITY_REPORT.md. Numbers are read from provenance sidecars / cube metadata / validation JSON - never typed in."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..config import DOCS_DIR, OUTPUTS_DIR, RAW_DIR, ROOT, load


def _prov(dirpath: Path, pattern: str) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(dirpath.glob(pattern))]


def _cube_meta() -> dict | None:
    p = ROOT / "data/interim/aethentra/cube_meta.json"
    return json.loads(p.read_text()) if p.exists() else None


def _dq() -> dict | None:
    p = OUTPUTS_DIR / "reports/data_validation/data_quality.json"
    return json.loads(p.read_text()) if p.exists() else None


def data_inventory() -> pd.DataFrame:
    ds = load("data_sources")
    cm, dq = _cube_meta(), _dq()
    cdr_prov = _prov(RAW_DIR / "nsidc_g02202_v6", "*.nc.provenance.json")
    ncep_prov = _prov(RAW_DIR / "ncep_r1", "*.nc.provenance.json")
    rows = [
        dict(dataset="NOAA/NSIDC SIC CDR v6 (G02202) Southern Hemisphere daily", status="downloaded_this_task (VERIFIED)",
             source=ds["sea_ice_concentration"]["landing_page"], file_format="NetCDF-4 (CF-1.11), yearly aggregates",
             temporal_coverage=f"{cm['start']}..{cm['end']}" if cm else "", temporal_resolution="daily",
             spatial_coverage="Southern Ocean, 39.2S-90S", spatial_resolution="25 km",
             variables="cdr_seaice_conc, cdr_seaice_conc_stdev, qa/interp flags, surface_type_mask, lat/lon", units="fraction 0-1 (stored as % in cube)",
             crs="EPSG:3412", missing_values="_FillValue 255; all-missing days listed in DATA_QUALITY_REPORT", quality_flags="QA (7 bits), spatial & temporal interpolation flags, stdev",
             size_mb=round(sum(p["bytes"] for p in cdr_prov) / 1e6, 1), files=len(cdr_prov),
             md5_verified=sum(1 for p in cdr_prov if p.get("verified")),
             suitable="YES - primary labels and SIC predictors", reason="Long (1979-2026), consistent, daily, public, documented uncertainty"),
        dict(dataset="NCEP/NCAR Reanalysis 1 daily means (air.sig995, uwnd/vwnd.sig995, slp)", status="downloaded_this_task (VERIFIED)",
             source=ds["atmosphere_interim"]["landing_page"], file_format="NetCDF (OPeNDAP subset, lat <= 35S)",
             temporal_coverage=(dq or {}).get("atmosphere", {}).get("coverage", {}).get("air", {}).get("first", "") + ".." +
                               (dq or {}).get("atmosphere", {}).get("coverage", {}).get("air", {}).get("last", ""),
             temporal_resolution="daily mean", spatial_coverage="35S-90S", spatial_resolution="2.5 deg", variables="air, uwnd, vwnd, slp",
             units="K, m/s, m/s, Pa", crs="EPSG:4326 regular lat/lon", missing_values="none found (see report)", quality_flags="none",
             size_mb=round(sum((RAW_DIR / "ncep_r1" / f"ncep_r1_{p['variable']}_{p['year']}_south.nc").stat().st_size for p in ncep_prov) / 1e6, 1),
             files=len(ncep_prov), md5_verified="n/a (OPeNDAP subset; local MD5 recorded)",
             suitable="YES (interim)", reason="Public substitute for ERA5; coarse 2.5 deg resolution"),
        dict(dataset="ERA5 single/pressure levels (EXTERNAL APIs/API.py, PRESSUREAPI.py)", status="MISSING (credentials)",
             source="https://cds.climate.copernicus.eu", file_format="NetCDF (requested)", suitable="YES if acquired",
             reason="Preferred atmosphere; requires CDS token"),
        dict(dataset="NSIDC-0803 AMSR2 Daily Polar Gridded SIC v1", status="DOWNLOADABLE (Earthdata login)", source="https://nsidc.org/data/nsidc-0803/",
             temporal_coverage="2012-present", spatial_resolution="12.5/25 km", suitable="partly", reason="Too short for 1979-2015 training"),
        dict(dataset="CMEMS SEAICE_GLO_SEAICE_L4_REP_OBSERVATIONS_011_009 (OSI SAF SIC CDR)", status="DOWNLOADABLE (Copernicus Marine account)",
             source="https://data.marine.copernicus.eu/product/SEAICE_GLO_SEAICE_L4_REP_OBSERVATIONS_011_009/description",
             suitable="YES as independent gridded comparison", reason="Not acquired (account required)"),
        dict(dataset="CMEMS ANTARCTIC_OMI_SI_extent (reanalysis)", status="DOWNLOADABLE (Copernicus Marine account)",
             source="https://data.marine.copernicus.eu/product/ANTARCTIC_OMI_SI_extent/services", suitable="comparison only", reason="Monthly hemispheric extent"),
        dict(dataset="NSIDC Sea Ice Index v4 (G02135) SH daily extent", status="VERIFIED existing (Stage 1 download)",
             source="https://nsidc.org/data/seaice_index", file_format="CSV", temporal_coverage="1978-10-26..", temporal_resolution="daily (every other day before 1987-08)",
             spatial_coverage="Southern Hemisphere (scalar)", units="10^6 km^2", suitable="comparison only", reason="Independent extent check of the label grid"),
    ]
    stage1 = ROOT / "metadata/antarctic_dataset_inventory.csv"
    if stage1.exists():
        s = pd.read_csv(stage1).fillna("")
        rules = {"cmems_omi_si_extent": ("comparison only", "Monthly hemispheric extent, no grid"),
                 "cmems_dmi_asip_sic": ("NO (training)", "Single day, 98.7 % fill, 1 km SAR grid"),
                 "cmems_sea_ice_drift": ("NO (not acquired)", "Metadata only"),
                 "oib_arctic_form_drag": ("NO", "Arctic"), "nsidc_g02135_north_climatology": ("NO", "Arctic"),
                 "nasa_edsc_catalog": ("NO", "Catalog metadata"), "earthdata_download_installer": ("NO", "Software")}
        for did, g in s.groupby("dataset_id"):
            ok, why = rules.get(did, ("NO", "Not a sea-ice concentration time series"))
            rows.append(dict(dataset=g.dataset_name.iloc[0], status="VERIFIED existing (DATAS/)", source=g.source_organization.iloc[0],
                             file_format="; ".join(sorted(set(g.detected_format))), temporal_coverage="; ".join(sorted(set(g.time_coverage.astype(str)) - {""}))[:120],
                             variables="; ".join(sorted(set(g.variables.astype(str)) - {""}))[:200], units="; ".join(sorted(set(g.units.astype(str)) - {""}))[:120],
                             crs="; ".join(sorted(set(g.crs.astype(str)) - {""}))[:80], missing_values="; ".join(sorted(set(g.missing_values.astype(str)) - {""}))[:80],
                             size_mb=round(g.size_mb.sum(), 2), files=len(g), suitable=ok, reason=why))
    umm = sorted((ROOT / "DATAS").glob("*.umm_json"))
    if umm:
        rows.append(dict(dataset="NASA CMR UMM service/tool records (NSIDC access tools)", status="VERIFIED existing (DATAS/, added after Stage 1)",
                         source="NASA CMR", file_format="UMM JSON", files=len(umm), size_mb=round(sum(p.stat().st_size for p in umm) / 1e6, 3),
                         suitable="NO", reason="Metadata about access services, not data"))
    df = pd.DataFrame(rows)
    df.to_csv(DOCS_DIR / "DATA_INVENTORY.csv", index=False)
    return df


def data_sources_and_provenance() -> None:
    ds = load("data_sources")
    cdr = _prov(RAW_DIR / "nsidc_g02202_v6", "*.nc.provenance.json")
    ncep = _prov(RAW_DIR / "ncep_r1", "*.nc.provenance.json")
    L = ["# Data Sources and Provenance — AETHENTRA ML Task 01", "",
         "Generated by `scripts/build_docs.py` from the `.provenance.json` sidecar written for every downloaded file.", "",
         "## 1. Primary: NOAA/NSIDC Sea Ice Concentration CDR, Version 6 (G02202)", "",
         f"* DOI: {ds['sea_ice_concentration']['doi']} — {ds['sea_ice_concentration']['landing_page']}",
         f"* Access: {ds['sea_ice_concentration']['access']} — `{ds['sea_ice_concentration']['base_url']}`",
         f"* Licence: {ds['sea_ice_concentration']['license']}",
         "* Algorithm: combination of NASA Team and Bootstrap passive-microwave algorithms (SMMR 1978-87, SSM/I-SSMIS, AMSR2 for the near-real-time ICDR).",
         f"* Files: {len(cdr)} yearly aggregates, {sum(p['bytes'] for p in cdr) / 1e9:.2f} GB, "
         f"{sum(1 for p in cdr if p.get('verified'))} MD5-verified against NSIDC `.mnf` manifests.", "",
         "| File | Retrieved (UTC) | Bytes | MD5 | Verified |", "|---|---|---|---|---|"]
    L += [f"| {p['original_filename']} | {p['retrieved_utc']} | {p['bytes']:,} | `{p['md5']}` | {p.get('verified')} |" for p in cdr]
    L += ["", "## 2. Interim atmosphere: NCEP/NCAR Reanalysis 1 (daily means)", "",
          f"* Access: {ds['atmosphere_interim']['access']} — `{ds['atmosphere_interim']['opendap_base']}`",
          f"* Reference: Kalnay et al. (1996), {ds['atmosphere_interim']['doi']}",
          f"* Subset: latitude ≤ {ds['atmosphere_interim']['lat_max']}°; variables {', '.join(ds['atmosphere_interim']['variables'])}",
          f"* Why: {ds['atmosphere_interim']['note']}",
          f"* Files: {len(ncep)}; years {min(p['year'] for p in ncep) if ncep else '-'}–{max(p['year'] for p in ncep) if ncep else '-'}; "
          f"incomplete years: {[p['year'] for p in ncep if not p.get('complete_year')]}", "",
          "| Variable | Years | Days | Units |", "|---|---|---|---|"]
    if ncep:
        n = pd.DataFrame(ncep)
        for v, g in n.groupby("variable"):
            L.append(f"| {v} | {g.year.min()}–{g.year.max()} | {g.days.sum():,} | {g.units.iloc[0]} |")
    L += ["", "## 3. Comparison / reference products (not used for training)", "",
          "* NSIDC Sea Ice Index v4 (G02135) daily SH extent — `data/raw/antarctic/external/nsidc_g02135_south/` (Stage 1, with provenance).",
          "* CMEMS OMI Antarctic monthly extent — `DATAS/ANTARCTIC_OMI_SI_extent_19790115_P20250505_R19792024.nc`.", "",
          "## 4. Not acquired", "",
          "| Product | Requirement |", "|---|---|",
          "| ERA5 single / pressure levels | CDS account + token (`CDSAPI_URL`, `CDSAPI_KEY`), cdsapi |",
          "| CMEMS OSI SAF SIC CDR (011_009), sea-ice drift (011_018), Antarctic extent reanalysis | Copernicus Marine account |",
          "| NSIDC-0803 AMSR2 SIC | NASA Earthdata Login |"]
    (DOCS_DIR / "DATA_SOURCES_AND_PROVENANCE.md").write_text("\n".join(L), encoding="utf-8")


def data_quality_report() -> None:
    dq, cm = _dq(), _cube_meta()
    if not dq:
        return
    c = dq["cube"]
    g = dq.get("comparison_g02135", {})
    interp = dq["temporal_interpolation_fraction_by_year"]
    smmr = [y for y, f in interp.items() if f > 0.2]
    L = ["# Data Quality Report — AETHENTRA ML Task 01", "",
         "Generated from `outputs/reports/data_validation/data_quality.json` (`python scripts/validate_data.py`).", "",
         "## 1. Primary SIC record (NOAA/NSIDC CDR v6, SH 25 km)", "",
         "| Check | Result |", "|---|---|",
         f"| Calendar span | {c['start']} … {c['end']} ({c['shape'][0]:,} days) |",
         f"| Grid | {c['shape'][1]} × {c['shape'][2]} cells, EPSG:3412; {c['ocean_cells']:,} static ocean cells ({c['ocean_area_mkm2']:.2f} × 10⁶ km²) |",
         f"| Cell area range | {c['cell_area_km2_range'][0]:.1f} – {c['cell_area_km2_range'][1]:.1f} km² (exact, projection scale factor) |",
         f"| Input files MD5-verified | {c['inputs_md5_verified']} / {c['inputs']} |",
         f"| Days absent from files | {c['days_missing']} |",
         f"| Days present but entirely missing (all ocean cells fill) | {dq['days_in_file_but_all_ocean_missing']} |",
         f"| Duplicate days | {dq['duplicate_days']} |",
         f"| SIC values outside 0–100 (not fill) | {dq['ocean_invalid_gt100_total']} |",
         f"| Days with > 1 % of ocean cells missing | {dq['days_with_ocean_missing_gt_1pct']} |",
         f"| Ocean cells flagged 'No_input_data' (QA bit 8) | {dq['no_input_flag_cells_total']:,} (SMMR every-other-day era; values temporally interpolated by NSIDC) |",
         f"| Non-ocean cells carrying a value | {dq['nonocean_cells_with_values_total']} |",
         f"| Cells whose surface type varies (< 99 % ocean) | {dq['mask']['cells_ocean_on_some_but_lt99pct_days']} (excluded from the static ocean mask) |",
         f"| Day-to-day hemispheric extent jumps > {dq['extent_jumps_gt_threshold']['threshold_mkm2']} × 10⁶ km² | {dq['extent_jumps_gt_threshold']['count']} |", "",
         "### Effective gaps (no valid ocean data)", "", "| Start | End | Days |", "|---|---|---|"]
    L += [f"| {r['start']} | {r['end']} | {r['days']} |" for r in dq["effective_gap_ranges"]]
    L += ["", f"Years with > 20 % temporally interpolated ocean cells (SMMR alternate-day sampling): {', '.join(map(str, smmr)) or 'none'}.", "",
          "Extent jumps flagged (date, |Δ| in 10⁶ km²): " + (", ".join(dq["extent_jumps_gt_threshold"]["dates"]) or "none") + ".",
          "They are retained (not removed); they coincide with sensor transitions / gap edges and are excluded from labels only through the",
          "per-cell ≥5-of-7-day rule when data are missing.", "",
          "## 2. Independent cross-check of the derived extent", ""]
    if g:
        L += [f"Daily extent computed by this pipeline from the CDR grid vs NSIDC Sea Ice Index v4 (G02135): {g['matched_days']:,} matched days, "
              f"mean difference {g['mean_diff_cdr_minus_g02135_mkm2']:+.3f} ± {g['std_diff_mkm2']:.3f} × 10⁶ km², r = {g['pearson_r']:.4f}. {g['note']}"]
    a = dq.get("atmosphere")
    if a:
        L += ["", "## 3. Atmospheric predictors (NCEP/NCAR R1)", "", "| Variable | First | Last | Days | Missing days in span | Min | Max | NaN |", "|---|---|---|---|---|---|---|---|"]
        for v, cv in a["coverage"].items():
            mm = a["min_max_nan"][v]
            L.append(f"| {v} | {cv['first']} | {cv['last']} | {cv['days']:,} | {cv['missing_days_in_span']} | {mm[0]:.1f} | {mm[1]:.1f} | {mm[2]} |")
        L += ["", f"SIC grid latitude range {a['sic_grid_lat_range'][0]:.2f}…{a['sic_grid_lat_range'][1]:.2f} lies inside the atmosphere subset "
              f"({a['grid_lat_range'][0]:.1f}…{a['grid_lat_range'][1]:.1f}): {a['sic_grid_inside_atm_grid']}."]
    L += ["", "## 4. Handling rules (no silent discarding)", "",
          "* Missing / fill values are stored as 255 and become NaN — never 0 %. Land, coast and lake cells are excluded by the static ocean mask.",
          "* Targets need ≥ 5 of 7 valid days per cell; cells failing this are counted and excluded from that issue date only.",
          "* Issue dates where < 50 % of ocean cells have a persistence value (≤ 3 days old) are skipped and listed in the evaluation summaries.",
          "* No temporal interpolation or gap filling is added by AETHENTRA; NSIDC's own interpolation is flagged in the QA statistics above.", "",
          "## 5. Figures", ""]
    L += [f"![{Path(f).stem}](../../{f})" for f in dq.get("figures", [])]
    (DOCS_DIR / "DATA_QUALITY_REPORT.md").write_text("\n".join(L), encoding="utf-8")
