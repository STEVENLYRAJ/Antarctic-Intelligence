"""Entry point for the Antarctic climate & cryosphere preprocessing pipeline.

Run from the repository root:

    python -m data.src.preprocessing.antarctic.run_pipeline                    # offline, uses cached remote checks
    python -m data.src.preprocessing.antarctic.run_pipeline --check-remote --download-small
    python -m data.src.preprocessing.antarctic.run_pipeline --skip-report

Raw files in DATAS/ are opened read-only and re-hashed at the end to prove they were not modified.
"""
from __future__ import annotations

import argparse
import datetime as dt
import time
import traceback

import pandas as pd

from . import era5_api, external_sources, handlers_documents as docs, handlers_geospatial as geo
from . import handlers_netcdf as ncd, handlers_tabular as tab
from .common import (LOG, load_hash_cache, read_json, rel, save_hash_cache, setup_logging, software_versions,
                     utcnow, write_json)
from .config import (DATASET_MANIFEST_CSV, DOMAIN, EXTERNAL_RAW_DIR, INVENTORY_CSV, INVENTORY_JSON,
                     INVENTORY_PRERUN_CSV, QUALITY_DIR, RAW_DIR, RUN_SUMMARY_JSON, SOURCE_REGISTRY_JSON)
from .inventory import build_inventory, verify_raw_unchanged

STATUS_RANK = {"processed": 6, "partially_processed": 5, "validated": 4, "metadata_inspected": 3,
               "not_available": 2, "unsupported": 1, "failed": 0}


def _safe(fn, *a, **k):
    """Run one handler; an exception never stops independent datasets."""
    try:
        return fn(*a, **k)
    except Exception as e:  # handlers already catch, this is a last resort
        LOG.error("Handler %s crashed: %s\n%s", fn.__name__, e, traceback.format_exc())
        return None


def run_handlers(inv: pd.DataFrame) -> list[dict]:
    R = RAW_DIR
    g = R / "glims_download_33432"
    recs = []

    def f(name):
        p = R / name
        return p if p.exists() else None

    # Sea-ice NetCDF
    omi = next(R.glob("ANTARCTIC_OMI_SI_extent_*.nc"), None)
    if omi:
        recs.append(_safe(ncd.process_omi_extent, omi, [p for p in [f("ANTARCTIC_OMI_SI_extent_obs.xml"), f("ANTARCTIC_OMI_SI_extent_obs-hq.png")] if p]))
    for dmi in sorted(R.glob("dmi_asip_seaice_mosaic_ant_*.nc")):
        recs.append(_safe(ncd.process_dmi_asip_sic, dmi, [p for p in [f("SEAICE_ANT_PHY_AUTO_L3_NRT_011_012.xml")] if p]))
    for oib in sorted(R.glob("Cda_ArcticOIB*.nc")):
        recs.append(_safe(ncd.process_oib_cda, oib))

    # NSIDC climatologies (local north + downloaded south) and daily south
    for p in sorted(R.glob("N_seaice_extent_climatology_*.csv")):
        recs.append(_safe(tab.process_nsidc_climatology, p, "nsidc_g02135_north_climatology", "Northern", [x for x in [f("download.htm")] if x]))
    ext = EXTERNAL_RAW_DIR / "nsidc_g02135_south"
    for p in sorted(ext.glob("S_seaice_extent_climatology_*.csv")):
        recs.append(_safe(tab.process_nsidc_climatology, p, "nsidc_g02135_south_climatology", "Southern", external=True))
    daily = ext / "S_seaice_extent_daily_v4.0.csv"
    if daily.exists():
        recs.append(_safe(tab.process_nsidc_daily, daily))

    # GLIMS (polygons first: they define the Antarctic glacier-ID set)
    ant_ids: set[str] = set()
    if (g / "glims_polygons.shp").exists():
        res = _safe(geo.process_glims_polygons, g / "glims_polygons.shp")
        if res:
            rec, ant_ids = res
            recs.append(rec)
    if (g / "glims_points.shp").exists():
        recs.append(_safe(geo.process_glims_points, g / "glims_points.shp", ant_ids))
    if (g / "glims_images.shp").exists():
        recs.append(_safe(geo.process_glims_images, g / "glims_images.shp"))
    if (g / "glims_lines.shp").exists():
        recs.append(_safe(geo.process_glims_lines, g / "glims_lines.shp"))
    hyps = sorted(g.glob("glims_hypsometry_*.csv"))
    if hyps:
        recs.append(_safe(tab.process_glims_hypsometry, hyps, ant_ids))
    if (g / "README.txt").exists() and (g / "CITATIONS.txt").exists():
        recs.append(_safe(docs.process_glims_docs, g / "README.txt", g / "CITATIONS.txt"))

    # PGC / NCALM tile index, catalog exports, images, docs
    if f("NCALM_DV_LiDAR_LAS_Tile_index.kmz"):
        recs.append(_safe(geo.process_pgc_kmz, f("NCALM_DV_LiDAR_LAS_Tile_index.kmz"), [p for p in [f("NCALM_DV_LiDAR_Collection_Report.pdf")] if p]))
    if f("NCALM_DV_LiDAR_Collection_Report.pdf"):
        recs.append(_safe(docs.process_pdf, f("NCALM_DV_LiDAR_Collection_Report.pdf"), "pgc_ncalm_dv_lidar_tiles"))
    if f("edsc_collection_results_export.json") and f("edsc_collection_results_export.csv"):
        recs.append(_safe(tab.process_edsc_catalog, f("edsc_collection_results_export.json"), f("edsc_collection_results_export.csv")))
    for xml, did, pid in [("ANTARCTIC_OMI_SI_extent_obs.xml", "cmems_omi_si_extent", "ANTARCTIC_OMI_SI_extent_obs"),
                          ("SEAICE_ANT_PHY_AUTO_L3_NRT_011_012.xml", "cmems_dmi_asip_sic", "SEAICE_ANT_PHY_AUTO_L3_NRT_011_012"),
                          ("SEAICE_ANT_PHY_L3_MY_011_018.xml", "cmems_sea_ice_drift", "SEAICE_ANT_PHY_L3_MY_011_018")]:
        if f(xml):
            recs.append(_safe(docs.process_iso_xml, f(xml), did, pid))
    if f("ANTARCTIC_OMI_SI_extent_obs-hq.png"):
        recs.append(_safe(docs.process_png, f("ANTARCTIC_OMI_SI_extent_obs-hq.png"), "cmems_omi_si_extent"))
    if f("antarctic.htm"):
        recs.append(_safe(docs.process_html_index, f("antarctic.htm"), "noaa_ncei_arcgis_antarctic",
                          "NOAA NCEI ArcGIS REST 'antarctic' services folder (saved page)", "NOAA NCEI"))
    if f("download.htm"):
        recs.append(_safe(docs.process_html_index, f("download.htm"), "nsidc_g02135_index",
                          "NSIDC G02135 directory index (saved page)", "NSIDC / NOAA"))
    for tif in sorted(R.glob("*.tif")):
        recs.append(_safe(geo.process_tiff_image, tif))
    for exe in sorted(R.glob("*.exe")):
        recs.append(_safe(docs.process_executable, exe))

    # API-generated datasets (CDS ERA5) and cross-product comparison
    recs += era5_api.process_api_sources()
    from .config import PROCESSED_DIR
    omi_csv = PROCESSED_DIR / "sea_ice_extent" / "cmems_omi_si_extent_monthly.csv"
    nsd_csv = PROCESSED_DIR / "sea_ice_extent" / "nsidc_g02135_south_daily.csv"
    if omi_csv.exists() and nsd_csv.exists():
        recs.append(_safe(tab.compare_extent_products, omi_csv, nsd_csv))
    return [r for r in recs if r]


# --------------------------------------------------------------------------- manifest/inventory enrichment
def _first(m: dict, *keys):
    for k in keys:
        v = m.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def summarize_record(rec: dict) -> dict:
    m = rec.get("metrics", {})
    variables = _first(m, "variables", "fields", "columns_processed", "json_schema")
    if isinstance(variables, dict):
        variables = list(variables.keys())
    tc = m.get("time_continuity")
    time_cov = (f"{tc['first']}..{tc['last']}" if tc else None) or _first(m, "time_coverage", "time", "acq_time_range_utc",
                                                                          "time_start_range", "acq_time_range")
    spatial = _first(m, "antarctic_bounds_lonlat", "bounds_lonlat", "lat_range", "global_bounds")
    units = m.get("units")
    if not units and isinstance(m.get("variables"), dict):
        units = {k: v.get("units") for k, v in m["variables"].items() if isinstance(v, dict) and v.get("units")}
    return {
        "variables": "; ".join(map(str, variables))[:500] if variables else "",
        "records_or_dimensions": str(_first(m, "records_before", "dimensions") or ""),
        "processed_records_or_dimensions": str(m.get("records_after", "")),
        "time_coverage": str(time_cov or ""),
        "spatial_coverage": str(spatial or ""),
        "crs": str(_first(m, "crs", "crs_proj4") or ""),
        "units": str(units or ""),
        "missing_values": (f"{m['missing_count']} ({m.get('missing_percent')}%)" if m.get("missing_count") is not None else ""),
    }


def enrich_inventory(inv: pd.DataFrame, recs: list[dict]) -> pd.DataFrame:
    by_file: dict[str, dict] = {}
    for r in recs:
        for sf in r["source_files"]:
            cur = by_file.get(sf)
            # A file's status is the best outcome of any record that consumed it as primary data.
            if cur is None or STATUS_RANK.get(r["status"], -1) > STATUS_RANK.get(cur["status"], -1):
                by_file[sf] = r
    cols = {k: [] for k in ["processing_status", "quality_record", "domain_relevance", "variables", "records_or_dimensions",
                            "processed_records_or_dimensions", "time_coverage", "spatial_coverage", "crs", "units",
                            "missing_values", "issues", "errors"]}
    for _, row in inv.iterrows():
        r = by_file.get(row["relative_path"])
        if r is None:
            for k in cols:
                cols[k].append("" if k != "processing_status" else "discovered_not_handled")
            continue
        s = summarize_record(r)
        cols["processing_status"].append(r["status"])
        cols["quality_record"].append(rel(QUALITY_DIR / f"{r['dataset_id']}.json"))
        cols["domain_relevance"].append(r.get("domain_relevance", ""))
        for k in s:
            cols[k].append(s[k])
        cols["issues"].append("; ".join(f"{i['type']}" + (f"({i['count']})" if i.get("count") not in (None, 0) else "") for i in r["issues"])[:500])
        cols["errors"].append("; ".join(r["errors"])[:500])
    for k, v in cols.items():
        inv[k] = v
    return inv


def build_manifest(recs: list[dict]) -> pd.DataFrame:
    rows = []
    for r in recs:
        outs = r["outputs"] or [{"path": "", "kind": "", "description": "no transformed output (validated in place / metadata only)", "size_bytes": None}]
        for o in outs:
            rows.append({"dataset_id": r["dataset_id"], "dataset_name": r["dataset_name"], "status": r["status"],
                         "source_files": "; ".join(r["source_files"]), "output_path": o["path"], "output_kind": o["kind"],
                         "output_bytes": o["size_bytes"], "output_description": o["description"],
                         "quality_report": rel(QUALITY_DIR / f"{r['dataset_id']}.json"), "processed_utc": r["finished_utc"]})
    return pd.DataFrame(rows)


def build_registry(recs: list[dict], remote: dict | None, downloads: list[dict]) -> list[dict]:
    by_id = {}
    for r in recs:
        by_id.setdefault(r["dataset_id"], r)
    reg = []
    links = {"A": ["cmems_omi_si_extent"], "B": ["cmems_dmi_asip_sic"], "C": [], "D": ["pgc_ncalm_dv_lidar_tiles"], "E": [],
             "F": ["glims_polygons", "glims_points", "glims_images", "glims_lines", "glims_hypsometry"],
             "G": ["nsidc_g02135_south_climatology", "nsidc_g02135_south_daily"]}
    for s in external_sources.SOURCES:
        local = [by_id[i] for i in links[s["source_key"]] if i in by_id]
        chk = (remote or {}).get("sources", {}).get(s["source_key"], [])
        reachable = [c for c in chk if c.get("http_status") == 200 and not c.get("login_redirect")]
        login = any(c.get("login_redirect") for c in chk)
        if s["source_key"] == "G":
            dl = "downloaded" if any(d["status"] in ("downloaded", "already_present") for d in downloads) or local else "not_downloaded"
        elif local and any(r["status"] in ("processed", "validated", "partially_processed") for r in local):
            dl = "downloaded"          # copy present in DATAS/ (obtained by the user before this pipeline)
        else:
            dl = "not_downloaded"
        statuses = [r["status"] for r in local]
        prep = ("processed" if statuses and all(x == "processed" for x in statuses) else
                "partially_processed" if any(x in ("processed", "partially_processed") for x in statuses) else
                "validated" if "validated" in statuses else "metadata_inspected" if chk else "discovered")
        notes = []
        if login:
            notes.append("Remote directory redirects to NASA Earthdata Login (credentials required; not used).")
        if s["source_key"] in "ABC":
            notes.append("Data download needs a (free) Copernicus Marine account; only public STAC/ISO metadata were retrieved.")
        if s["source_key"] == "B":
            notes.append("Only ONE daily file (2023-02-02, first day of the product) is present locally.")
        if s["source_key"] == "C":
            notes.append("No drift data present locally; ISO metadata XML only. Drift preprocessing could not be executed.")
        if s["source_key"] == "D":
            notes.append("Interactive map (JavaScript app) - not a dataset. Local KMZ tile index links to data.pgc.umn.edu.")
        if s["source_key"] == "E":
            notes.append("Catalog only; no AMD-listed dataset was downloaded. The AMD page links to the NASA Earthdata Search "
                         "AMD portal (https://search.earthdata.nasa.gov/portal/amd/search); DATAS/edsc_collection_results_export.* "
                         "is an Earthdata Search export that may originate from it (not verifiable from the file contents).")
        if s["source_key"] == "F":
            notes.append("Local copy is a GLOBAL GLIMS web download (790,854 polygons); Antarctic subset = RGI region 19.")
        out_paths = sorted({o["path"] for r in local for o in r["outputs"]})
        reg.append({
            "dataset_id": s["dataset_id"], "source_key": s["source_key"], "dataset_name": s["dataset_name"], "domain": DOMAIN,
            "provider": s["provider"], "source_url": s["source_url"], "product_id": s["product_id"], "doi": s["doi"],
            "local_paths": sorted({f for r in local for f in r["source_files"]}),
            "file_formats": sorted({p.rsplit(".", 1)[-1] for r in local for p in r["source_files"]}),
            "variables": s["variables"], "scientific_purpose": s["purpose"],
            "spatial_coverage": next((str(summarize_record(r)["spatial_coverage"]) for r in local if summarize_record(r)["spatial_coverage"]), None),
            "temporal_coverage": next((summarize_record(r)["time_coverage"] for r in local if summarize_record(r)["time_coverage"]), None),
            "license": s["license"], "access_method": s["access_method"],
            "remote_check": {"checked": bool(chk), "reachable_urls": len(reachable), "login_required": login},
            "download_status": dl, "validation_status": "validated" if local else ("metadata_inspected" if chk else "discovered"),
            "preprocessing_status": prep, "processing_timestamp": max((r["finished_utc"] for r in local), default=None),
            "output_paths": out_paths, "notes": notes,
        })
    # Local-only datasets and API sources
    extra = {"oib_arctic_form_drag", "nsidc_g02135_north_climatology", "nasa_edsc_catalog", "noaa_ncei_arcgis_antarctic__html",
             "ags_glacier_photograph", "earthdata_download_installer", "era5_single_levels", "era5_pressure_levels",
             "comparison_omi_vs_nsidc_extent"}
    for did in extra:
        r = by_id.get(did)
        if not r:
            continue
        s = summarize_record(r)
        api = did.startswith("era5_")
        reg.append({
            "dataset_id": did, "source_key": "API" if api else "local", "dataset_name": r["dataset_name"], "domain": DOMAIN,
            "provider": r["provider"],
            "source_url": ("https://cds.climate.copernicus.eu/datasets/" + r["metrics"]["script"]["dataset"]) if api else None,
            "product_id": r["metrics"]["script"]["dataset"] if api else None, "doi": None,
            "local_paths": r["source_files"], "file_formats": sorted({p.rsplit(".", 1)[-1] for p in r["source_files"]}),
            "variables": (r["metrics"]["request"]["variable"] if api else s["variables"]),
            "spatial_coverage": s["spatial_coverage"], "temporal_coverage": s["time_coverage"],
            "license": "Copernicus licence (CC-BY 4.0 for ERA5)" if api else None,
            "access_method": "cdsapi (Copernicus CDS API, personal access token required)" if api else "local file",
            "download_status": ("not_downloaded" if api and r["status"] == "not_available" else "downloaded"),
            "validation_status": r["status"], "preprocessing_status": r["status"], "processing_timestamp": r["finished_utc"],
            "output_paths": [o["path"] for o in r["outputs"]], "domain_relevance": r.get("domain_relevance"),
            "notes": [i["detail"] for i in r["issues"] if i["severity"] in ("warning", "error")][:6],
        })
    return reg


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check-remote", action="store_true", help="query the official source URLs (cached to metadata/)")
    ap.add_argument("--download-small", action="store_true", help="fetch whitelisted small public files (NSIDC G02135 south, ~1.9 MB)")
    ap.add_argument("--skip-figures", action="store_true")
    ap.add_argument("--skip-report", action="store_true")
    ap.add_argument("--rehash", action="store_true", help="ignore the hash cache for the pre-run inventory")
    a = ap.parse_args(argv)

    run_id = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    log_path = setup_logging(run_id)
    t0 = time.time()
    LOG.info("Antarctic preprocessing run %s", run_id)
    cache = load_hash_cache()

    inv = build_inventory(cache, force_hash=a.rehash)
    save_hash_cache(cache)
    INVENTORY_PRERUN_CSV.parent.mkdir(parents=True, exist_ok=True)
    inv.to_csv(INVENTORY_PRERUN_CSV, index=False)
    LOG.info("Pre-run inventory saved: %s (%d files, %.2f GB)", rel(INVENTORY_PRERUN_CSV), len(inv), inv.size_bytes.sum() / 1e9)

    remote = external_sources.check_remote_sources() if a.check_remote else external_sources.load_remote_checks()
    downloads = external_sources.download_small_files() if a.download_small else [
        {"file": rel(p), "status": "already_present"} for p in EXTERNAL_RAW_DIR.rglob("*.csv")]

    recs = run_handlers(inv)

    inv2 = enrich_inventory(inv.copy(), recs)
    inv2.to_csv(INVENTORY_CSV, index=False)
    write_json(inv2.to_dict(orient="records"), INVENTORY_JSON)
    man = build_manifest(recs)
    man.to_csv(DATASET_MANIFEST_CSV, index=False)
    registry = build_registry(recs, remote, downloads)
    write_json({"generated_utc": utcnow(), "domain": DOMAIN,
                "status_vocabulary": ["discovered", "metadata_inspected", "downloaded", "not_downloaded", "validated",
                                      "processed", "partially_processed", "not_available", "failed", "unsupported"],
                "sources": registry}, SOURCE_REGISTRY_JSON)

    figs = []
    if not a.skip_figures:
        from . import figures
        figs = _safe(figures.make_all, recs, inv2) or []

    integrity = verify_raw_unchanged(inv, cache)
    save_hash_cache(cache)
    LOG.info("Raw-data integrity: %s", "UNCHANGED" if integrity["unchanged"] else integrity)

    counts = inv2.processing_status.value_counts().to_dict()
    summary = {
        "run_id": run_id, "started": dt.datetime.fromtimestamp(t0).isoformat(), "duration_s": round(time.time() - t0, 1),
        "log": rel(log_path), "software": software_versions(),
        "options": vars(a), "raw_files": int(len(inv)), "raw_bytes": int(inv.size_bytes.sum()),
        "file_status_counts": counts,
        "dataset_status_counts": pd.Series([r["status"] for r in recs]).value_counts().to_dict(),
        "records": [{"dataset_id": r["dataset_id"], "status": r["status"], "outputs": len(r["outputs"]), "errors": r["errors"]} for r in recs],
        "outputs_total": int(sum(len(r["outputs"]) for r in recs)),
        "unique_output_files": int(man.output_path.replace("", pd.NA).dropna().nunique()),
        "downloads": downloads, "remote_checks_available": bool(remote),
        "raw_integrity": integrity, "figures": figs,
        "duplicates_by_hash": inv[inv.duplicate_of != ""][["relative_path", "duplicate_of"]].to_dict(orient="records"),
    }
    write_json(summary, RUN_SUMMARY_JSON)
    LOG.info("File status counts: %s", counts)

    if not a.skip_report:
        from . import report_docx
        path = _safe(report_docx.build_report)
        LOG.info("Word report: %s", rel(path) if path else "FAILED")
    LOG.info("Finished in %.1f s", time.time() - t0)
    return summary


if __name__ == "__main__":
    main()
