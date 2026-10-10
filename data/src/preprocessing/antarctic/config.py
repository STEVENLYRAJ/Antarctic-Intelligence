"""Paths and constants for the Antarctic climate & cryosphere preprocessing pipeline.

All paths are resolved relative to the repository root so the pipeline can be
run from any working directory.
"""
from pathlib import Path

# data/src/preprocessing/antarctic/config.py -> repository root is 4 levels up
ROOT = Path(__file__).resolve().parents[4]

RAW_DIR = ROOT / "DATAS"                                    # user-collected raw data (read-only)
API_DIR = ROOT / "EXTERNAL APIs"                            # existing CDS API scripts
EXTERNAL_RAW_DIR = ROOT / "data" / "raw" / "antarctic" / "external"   # small official downloads
ERA5_RAW_DIR = ROOT / "data" / "raw" / "antarctic" / "era5"           # target for ERA5 API outputs

PROCESSED_DIR = ROOT / "data" / "processed" / "antarctic"
REPORTS_DIR = ROOT / "data" / "reports" / "antarctic"
QUALITY_DIR = REPORTS_DIR / "quality"
FIGURES_DIR = REPORTS_DIR / "figures"
LOGS_DIR = REPORTS_DIR / "logs"
MANIFEST_DIR = ROOT / "metadata"                            # existing project manifest location
WORD_REPORT = ROOT / "reports" / "Antarctic_Climate_Cryosphere_Data_Preprocessing_Report.docx"

INVENTORY_CSV = MANIFEST_DIR / "antarctic_dataset_inventory.csv"
INVENTORY_JSON = MANIFEST_DIR / "antarctic_dataset_inventory.json"
INVENTORY_PRERUN_CSV = MANIFEST_DIR / "antarctic_dataset_inventory_prerun.csv"
DATASET_MANIFEST_CSV = MANIFEST_DIR / "antarctic_dataset_manifest.csv"
SOURCE_REGISTRY_JSON = MANIFEST_DIR / "antarctic_source_registry.json"
EXTERNAL_CHECKS_JSON = MANIFEST_DIR / "antarctic_external_source_checks.json"
HASH_CACHE_JSON = MANIFEST_DIR / ".antarctic_hash_cache.json"
RUN_SUMMARY_JSON = REPORTS_DIR / "pipeline_run_summary.json"

DOMAIN = "Antarctic Climate and Cryosphere"

# Antarctic Treaty area boundary used for geographic flags.
ANTARCTIC_LAT_LIMIT = -60.0
# GLIMS/GTN-G first-order region 19 = "Antarctic and Subantarctic" (RGI v6/v7).
GLIMS_ANTARCTIC_O1REG = 19

# EPSG codes used for spatial calculations (never written back over source CRS).
EPSG_WGS84 = 4326
EPSG_ANTARCTIC_PS = 3031      # Antarctic Polar Stereographic (mapping)
EPSG_EASE2_SOUTH = 6932       # NSIDC EASE-Grid 2.0 South, Lambert azimuthal equal-area (areas)

# Small, public, directly relevant files that the pipeline may fetch when
# explicitly asked (--download-small). Nothing else is downloaded automatically.
SMALL_DOWNLOADS = {
    "nsidc_g02135_south": {
        "base_url": "https://noaadata.apps.nsidc.org/NOAA/G02135/south/daily/data/",
        "files": [
            "S_seaice_extent_climatology_1981-2010_v4.0.csv",
            "S_seaice_extent_daily_v4.0.csv",
        ],
        "max_bytes": 10_000_000,
    }
}

HTTP_TIMEOUT = 30
USER_AGENT = "scientific-intelligence-antarctic-preprocessing/1.0"
