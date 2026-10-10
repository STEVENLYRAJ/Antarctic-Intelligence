"""External-source inspection (sources A-F of the assignment) and small, explicit downloads.

Remote checks are only performed with ``--check-remote``; results are cached in
metadata/antarctic_external_source_checks.json so offline reruns stay reproducible.
No credentials are used or stored. Large/credentialed downloads are never started here.
"""
from __future__ import annotations

import re
from pathlib import Path

import requests

from .common import LOG, read_json, rel, sha256_file, utcnow, write_json
from .config import EXTERNAL_CHECKS_JSON, EXTERNAL_RAW_DIR, HTTP_TIMEOUT, SMALL_DOWNLOADS, USER_AGENT

CMEMS_LICENCE = "https://marine.copernicus.eu/user-corner/service-commitments-and-licence"

SOURCES = [
    {"source_key": "A", "dataset_id": "cmems_omi_si_extent", "dataset_name": "Antarctic Monthly Sea Ice Extent from Observations Reprocessing",
     "provider": "Copernicus Marine Service (CMEMS); EUMETSAT OSI SAF / MET Norway", "product_id": "ANTARCTIC_OMI_SI_extent_obs",
     "source_url": "https://data.marine.copernicus.eu/product/ANTARCTIC_OMI_SI_extent_obs/services",
     "metadata_urls": ["https://stac.marine.copernicus.eu/metadata/ANTARCTIC_OMI_SI_extent_obs/product.stac.json"],
     "doi": "https://doi.org/10.48670/moi-00187", "license": CMEMS_LICENCE,
     "access_method": "Copernicus Marine Toolbox / MyOcean Data Store (free registration required); public STAC metadata",
     "purpose": "Monthly Southern Hemisphere sea-ice EXTENT (area with SIC > 15 %), 1979 onwards, for climate monitoring",
     "variables": ["siextent (km^2)", "monthlyclimsiextent_mean", "monthlyclimsiextent_std"]},
    {"source_key": "B", "dataset_id": "cmems_dmi_asip_sic", "dataset_name": "Antarctic Ocean - High Resolution Sea Ice Information",
     "provider": "Copernicus Marine Service (CMEMS); Danish Meteorological Institute (DMI-ASIP)", "product_id": "SEAICE_ANT_PHY_AUTO_L3_NRT_011_012",
     "source_url": "https://data.marine.copernicus.eu/product/SEAICE_ANT_PHY_AUTO_L3_NRT_011_012/services",
     "metadata_urls": ["https://stac.marine.copernicus.eu/metadata/SEAICE_ANT_PHY_AUTO_L3_NRT_011_012/product.stac.json",
                       "https://stac.marine.copernicus.eu/metadata/SEAICE_ANT_PHY_AUTO_L3_NRT_011_012/cmems_obs-si_ant_phy_nrt_l3-1km_P1D_202303/dataset.stac.json"],
     "doi": "https://doi.org/10.48670/mds-00320", "license": CMEMS_LICENCE,
     "access_method": "Copernicus Marine Toolbox (subset/get), ARCO Zarr, WMTS; free registration required",
     "purpose": "Daily 1 km SAR+AMSR2 sea-ice CONCENTRATION for the Southern Ocean (near real time)",
     "variables": ["ice_concentration (%)", "confidence (%)", "acq_time (s)"]},
    {"source_key": "C", "dataset_id": "cmems_sea_ice_drift", "dataset_name": "Antarctic Ocean Sea Ice Drift REPROCESSED",
     "provider": "Copernicus Marine Service (CMEMS); Ifremer CERSAT", "product_id": "SEAICE_ANT_PHY_L3_MY_011_018",
     "source_url": "https://data.marine.copernicus.eu/product/SEAICE_ANT_PHY_L3_MY_011_018/services",
     "metadata_urls": ["https://stac.marine.copernicus.eu/metadata/SEAICE_ANT_PHY_L3_MY_011_018/product.stac.json",
                       "https://stac.marine.copernicus.eu/metadata/SEAICE_ANT_PHY_L3_MY_011_018/cmems_obs-si_ant_phy_my_drift-cfosat-ssmi-merged_P3D_202411/dataset.stac.json"],
     "doi": "https://doi.org/10.48670/moi-00120", "license": CMEMS_LICENCE,
     "access_method": "Copernicus Marine Toolbox (subset/get), ARCO Zarr; free registration required",
     "purpose": "Multi-year 2/3/30-day sea-ice DRIFT vectors (eastward/northward velocity components) from AMSR, CFOSAT, SSMI",
     "variables": ["eastward_sea_ice_velocity", "northward_sea_ice_velocity", "quality/flag variables per dataset"]},
    {"source_key": "D", "dataset_id": "pgc_antarctica_map", "dataset_name": "Polar Geospatial Center - Antarctica map catalog",
     "provider": "Polar Geospatial Center (University of Minnesota)", "product_id": "PGC map catalog (interactive)",
     "source_url": "https://maps.apps.pgc.umn.edu/antarctica", "metadata_urls": [], "doi": None,
     "license": "Per-product (PGC data use and acknowledgement policy); not stated on the map application page",
     "access_method": "Interactive JavaScript web map; linked products served from data.pgc.umn.edu (HTTPS)",
     "purpose": "Geographic context layers; source of the NCALM Dry Valleys LiDAR tile index found locally",
     "variables": ["map layers (not a dataset)"]},
    {"source_key": "E", "dataset_id": "scar_amd", "dataset_name": "SCAR Antarctic Master Directory (AMD)",
     "provider": "Scientific Committee on Antarctic Research (SCAR)", "product_id": "AMD",
     "source_url": "https://scar.org/library-data/data/amd", "metadata_urls": [], "doi": None,
     "license": "Catalog; each listed dataset carries its own licence",
     "access_method": "Web catalog page linking to the AMD metadata portal (catalog records, not data)",
     "purpose": "Discovery of Antarctic scientific datasets (metadata directory)", "variables": ["catalog records"]},
    {"source_key": "F", "dataset_id": "glims", "dataset_name": "GLIMS Glacier Database (NSIDC-0272)",
     "provider": "GLIMS / NSIDC", "product_id": "NSIDC-0272 GLIMS v1",
     "source_url": "https://daacdata.apps.nsidc.org/pub/DATASETS/nsidc0272_GLIMS_v1/", "metadata_urls": [],
     "doi": "https://doi.org/10.7265/N5V98602", "license": "GLIMS data: free use with citation of the analysts (see CITATIONS.txt)",
     "access_method": "NSIDC DAAC HTTPS (NASA Earthdata Login required); GLIMS web download (glims.org) used for the local copy",
     "purpose": "Glacier outlines, points, images and hypsometry", "variables": ["glacier polygons", "points", "image locations", "hypsometry"]},
    {"source_key": "G", "dataset_id": "nsidc_g02135_south", "dataset_name": "NSIDC Sea Ice Index v4 (G02135) - Southern Hemisphere",
     "provider": "NSIDC / NOAA", "product_id": "G02135 v4",
     "source_url": "https://noaadata.apps.nsidc.org/NOAA/G02135/south/daily/data/", "metadata_urls": [],
     "doi": "https://doi.org/10.7265/a98x-0f50", "license": "NSIDC data use: free with citation",
     "access_method": "Public HTTPS directory (no login)",
     "purpose": "Daily Southern Hemisphere sea-ice extent and 1981-2010 climatology (independent cross-check of source A)",
     "variables": ["Extent (10^6 km^2)", "Missing (10^6 km^2)"]},
]


def _check(url: str) -> dict:
    try:
        r = requests.get(url, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}, allow_redirects=True)
        out = {"url": url, "http_status": r.status_code, "final_url": r.url, "content_type": r.headers.get("content-type"),
               "bytes": len(r.content), "login_redirect": "urs.earthdata.nasa.gov" in r.url or "login" in r.url.lower()}
        t = r.text
        title = re.search(r"<title>(.*?)</title>", t, re.S | re.I)
        out["page_title"] = title.group(1).strip()[:200] if title else None
        if "json" in (out["content_type"] or ""):
            j = r.json()
            out["stac"] = {"id": j.get("id"), "title": j.get("title"), "license": j.get("license"),
                           "extent": j.get("extent"), "keywords": j.get("keywords"),
                           "assets": {k: v.get("href") for k, v in (j.get("assets") or {}).items()},
                           "items": [l["href"] for l in j.get("links", []) if l.get("rel") == "item"],
                           "documentation": [l["href"] for l in j.get("links", []) if l.get("rel") in ("describedby", "cite-as")]}
            props = j.get("properties") or {}
            if "cube:variables" in props:
                out["stac"]["variables"] = {k: {"unit": v.get("unit"), "standard_name": v.get("standardName"),
                                                "dims": v.get("dimensions")} for k, v in props["cube:variables"].items()}
                out["stac"]["dimensions"] = props.get("cube:dimensions")
        elif "scar.org" in url:
            out["amd_links"] = sorted({u for u in re.findall(r'href="(https?://[^"]+)"', t)
                                       if any(k in u.lower() for k in ("amd", "gcmd", "data.aad", "metadata", "search"))})[:25]
        elif "nsidc" in url and "Index of" in t:
            out["directory_entries"] = re.findall(r'<a href="([^"?/][^"]*)">', t)
        return out
    except requests.RequestException as e:
        return {"url": url, "error": f"{type(e).__name__}: {str(e)[:200]}"}


def check_remote_sources() -> dict:
    results = {"checked_utc": utcnow(), "sources": {}}
    for s in SOURCES:
        urls = [s["source_url"], *s["metadata_urls"]]
        results["sources"][s["source_key"]] = [_check(u) for u in urls]
        LOG.info("Checked source %s (%s)", s["source_key"], s["product_id"])
    write_json(results, EXTERNAL_CHECKS_JSON)
    return results


def load_remote_checks() -> dict | None:
    return read_json(EXTERNAL_CHECKS_JSON)


def download_small_files() -> list[dict]:
    """Fetch the explicitly whitelisted small public files; never overwrite, verify size limits."""
    results = []
    for key, spec in SMALL_DOWNLOADS.items():
        dest_dir = EXTERNAL_RAW_DIR / key
        dest_dir.mkdir(parents=True, exist_ok=True)
        for fname in spec["files"]:
            dest = dest_dir / fname
            url = spec["base_url"] + fname
            prov_path = dest.with_suffix(dest.suffix + ".provenance.json")
            if dest.exists():
                results.append({"file": rel(dest), "status": "already_present", "url": url})
                continue
            try:
                h = requests.head(url, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
                size = int(h.headers.get("content-length", 0))
                if size > spec["max_bytes"]:
                    results.append({"file": fname, "status": "skipped_too_large", "bytes": size, "url": url})
                    continue
                r = requests.get(url, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()
                dest.write_bytes(r.content)
                prov = {"url": url, "downloaded_utc": utcnow(), "bytes": len(r.content), "sha256": sha256_file(dest),
                        "http_last_modified": r.headers.get("last-modified"), "access": "public HTTPS, no credentials"}
                write_json(prov, prov_path)
                results.append({"file": rel(dest), "status": "downloaded", **prov})
            except requests.RequestException as e:
                results.append({"file": fname, "status": "failed", "error": f"{type(e).__name__}: {e}", "url": url})
    return results
