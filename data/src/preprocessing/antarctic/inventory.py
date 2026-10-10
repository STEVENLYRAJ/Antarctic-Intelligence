"""File inventory of DATAS/: format sniffing, compound-file grouping, hashing, duplicates."""
from __future__ import annotations

import datetime as dt
import fnmatch
import json
from pathlib import Path

import pandas as pd

from .common import LOG, cached_sha256, rel
from .config import RAW_DIR

# (glob pattern on the file name, dataset_id, dataset name, source organisation, role)
DATASET_RULES = [
    ("ANTARCTIC_OMI_SI_extent_*.nc", "cmems_omi_si_extent", "Copernicus Marine OMI Antarctic monthly sea-ice extent", "Copernicus Marine Service / EUMETSAT OSI SAF (MET Norway)", "data"),
    ("ANTARCTIC_OMI_SI_extent_obs.xml", "cmems_omi_si_extent", "Copernicus Marine OMI Antarctic monthly sea-ice extent", "Copernicus Marine Service", "iso_metadata"),
    ("ANTARCTIC_OMI_SI_extent_obs-hq.png", "cmems_omi_si_extent", "Copernicus Marine OMI Antarctic monthly sea-ice extent", "Copernicus Marine Service", "product_figure"),
    ("dmi_asip_seaice_mosaic_ant_*.nc", "cmems_dmi_asip_sic", "DMI-ASIP Antarctic SAR sea-ice concentration (CMEMS SEAICE_ANT_PHY_AUTO_L3_NRT_011_012)", "Danish Meteorological Institute / Copernicus Marine Service", "data"),
    ("SEAICE_ANT_PHY_AUTO_L3_NRT_011_012.xml", "cmems_dmi_asip_sic", "DMI-ASIP Antarctic SAR sea-ice concentration (CMEMS SEAICE_ANT_PHY_AUTO_L3_NRT_011_012)", "Copernicus Marine Service", "iso_metadata"),
    ("SEAICE_ANT_PHY_L3_MY_011_018.xml", "cmems_sea_ice_drift", "Copernicus Marine Antarctic sea-ice drift reprocessed (SEAICE_ANT_PHY_L3_MY_011_018)", "Copernicus Marine Service / Ifremer CERSAT", "iso_metadata"),
    ("Cda_ArcticOIB*.nc", "oib_arctic_form_drag", "NASA Operation IceBridge Arctic atmospheric form-drag coefficients (Petty et al., 2017)", "NASA GSFC (A. Petty)", "data"),
    ("N_seaice_extent_climatology_*.csv", "nsidc_g02135_north_climatology", "NSIDC Sea Ice Index v4 (G02135) Northern Hemisphere daily extent climatology 1981-2010", "NSIDC / NOAA", "data"),
    ("download.htm", "nsidc_g02135_north_climatology", "NSIDC Sea Ice Index v4 (G02135) Northern Hemisphere daily extent climatology 1981-2010", "NSIDC / NOAA", "saved_index_page"),
    ("glims_polygons.*", "glims_polygons", "GLIMS glacier outlines (polygons)", "GLIMS / NSIDC", "data"),
    ("glims_points.*", "glims_points", "GLIMS glacier representative points", "GLIMS / NSIDC", "data"),
    ("glims_images.*", "glims_images", "GLIMS source-image footprints (points)", "GLIMS / NSIDC", "data"),
    ("glims_lines.*", "glims_lines", "GLIMS glacier lines (snow lines / centre lines)", "GLIMS / NSIDC", "data"),
    ("glims_hypsometry_*.csv", "glims_hypsometry", "GLIMS glacier hypsometry (area-elevation histograms)", "GLIMS / NSIDC", "data"),
    ("README.txt", "glims_documentation", "GLIMS download package documentation", "GLIMS / NSIDC", "documentation"),
    ("CITATIONS.txt", "glims_documentation", "GLIMS download package documentation", "GLIMS / NSIDC", "documentation"),
    ("NCALM_DV_LiDAR_LAS_Tile_index.kmz", "pgc_ncalm_dv_lidar_tiles", "NCALM McMurdo Dry Valleys LiDAR (2014) LAS tile index", "Polar Geospatial Center (PGC) / NCALM", "data"),
    ("NCALM_DV_LiDAR_Collection_Report.pdf", "pgc_ncalm_dv_lidar_tiles", "NCALM McMurdo Dry Valleys LiDAR (2014) LAS tile index", "NCALM", "documentation"),
    ("edsc_collection_results_export.*", "nasa_edsc_catalog", "NASA Earthdata Search collection-results export (catalog records)", "NASA Earthdata (CMR)", "catalog"),
    ("antarctic.htm", "noaa_ncei_arcgis_antarctic", "NOAA NCEI ArcGIS REST 'antarctic' services folder (saved page)", "NOAA NCEI", "saved_index_page"),
    ("AGS_A_2002_04.tif", "ags_glacier_photograph", "Glacier photograph image AGS_A_2002_04 (provenance unverified)", "unverified", "image"),
    ("Earthdata-Download-x64.exe", "earthdata_download_installer", "NASA Earthdata Download application installer", "NASA Earthdata", "software"),
]

COMPOUND_SIDECARS = {".shp": [".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".qix"]}


def sniff_format(path: Path) -> str:
    """Detect the actual file format from magic bytes, falling back to the extension."""
    with open(path, "rb") as f:
        head = f.read(512)
    ext = path.suffix.lower()
    if head.startswith(b"\x89HDF\r\n\x1a\n"):
        return "NetCDF-4/HDF5"
    if head[:3] == b"CDF":
        return "NetCDF-3 classic"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "TIFF"
    if head.startswith(b"\x89PNG"):
        return "PNG image"
    if head.startswith(b"%PDF"):
        return "PDF document"
    if head.startswith(b"PK\x03\x04"):
        return "KMZ (zipped KML)" if ext == ".kmz" else "ZIP archive"
    if head.startswith(b"MZ"):
        return "Windows executable (PE)"
    if head.startswith(b"GRIB"):
        return "GRIB"
    if ext == ".shp":
        return "ESRI Shapefile (geometry)"
    if ext == ".shx":
        return "ESRI Shapefile (index)"
    if ext == ".dbf":
        return "dBASE attribute table (shapefile)"
    if ext == ".prj":
        return "ESRI WKT projection (shapefile)"
    text = head.decode("utf-8", errors="replace").lstrip("﻿").lstrip()
    if text.startswith("<?xml"):
        return "XML (ISO 19139 / CSW)" if b"gmd:" in head or b"csw:" in head else "XML"
    if text.lower().startswith("<html") or text.lower().startswith("<!doctype html"):
        return "HTML page"
    if ext == ".json" and text[:1] in "[{":
        try:
            json.loads(path.read_text(encoding="utf-8"))
            return "JSON"
        except Exception:
            return "JSON (invalid)"
    if ext == ".csv":
        return "CSV"
    if ext == ".txt":
        return "Plain text"
    return f"unknown ({ext or 'no extension'})"


def match_rule(name: str):
    for pat, did, dname, org, role in DATASET_RULES:
        if fnmatch.fnmatch(name, pat):
            return did, dname, org, role
    return "unclassified", "Unclassified file", "unknown", "unknown"


def build_inventory(hash_cache: dict, force_hash: bool = False) -> pd.DataFrame:
    rows = []
    files = sorted(p for p in RAW_DIR.rglob("*") if p.is_file())
    LOG.info("Inventory: %d files under %s", len(files), rel(RAW_DIR))
    for p in files:
        did, dname, org, role = match_rule(p.name)
        st = p.stat()
        compound = ""
        if p.suffix.lower() in {".shp", ".shx", ".dbf", ".prj", ".cpg"}:
            stem = p.with_suffix("")
            members = [stem.with_suffix(s) for s in [".shp"] + COMPOUND_SIDECARS[".shp"]]
            present = [m.name for m in members if m.exists()]
            compound = f"shapefile:{stem.name} [{', '.join(present)}]"
        rows.append({
            "relative_path": rel(p),
            "file_name": p.name,
            "extension": p.suffix.lower(),
            "detected_format": sniff_format(p),
            "size_bytes": st.st_size,
            "size_mb": round(st.st_size / 1e6, 3),
            "modified_utc": dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc).replace(microsecond=0).isoformat(),
            "sha256": cached_sha256(p, hash_cache, force=force_hash),
            "dataset_id": did,
            "dataset_name": dname,
            "source_organization": org,
            "file_role": role,
            "compound_group": compound,
        })
    df = pd.DataFrame(rows)
    dup = df[df.duplicated("sha256", keep=False)]
    df["duplicate_of"] = ""
    for h, grp in dup.groupby("sha256"):
        paths = list(grp["relative_path"])
        for i in grp.index:
            df.at[i, "duplicate_of"] = "; ".join(x for x in paths if x != df.at[i, "relative_path"])
    return df


def verify_raw_unchanged(prerun: pd.DataFrame, hash_cache: dict) -> dict:
    """Re-hash every raw file (forced) and compare with the pre-run inventory."""
    changed, missing = [], []
    for _, r in prerun.iterrows():
        p = RAW_DIR.parent / r["relative_path"]
        if not p.exists():
            missing.append(r["relative_path"])
            continue
        if p.stat().st_size != r["size_bytes"] or cached_sha256(p, hash_cache, force=True) != r["sha256"]:
            changed.append(r["relative_path"])
    return {"files_checked": int(len(prerun)), "changed": changed, "missing": missing,
            "unchanged": not changed and not missing, "method": "full SHA-256 re-hash after processing"}
