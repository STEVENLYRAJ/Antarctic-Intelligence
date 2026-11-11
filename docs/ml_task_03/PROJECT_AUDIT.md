# AETHENTRA ML-03 — Project Audit (Phase 0)

Audit date: 2026-11-09. Everything below was checked on this machine; nothing is assumed from earlier discussion.

## Hardware

| item | verified value |
|---|---|
| CPU | AMD Ryzen 7 7435HS, 8 cores |
| RAM | 23.7 GB |
| GPU | NVIDIA GeForce RTX 4060 Laptop, 8 GB; PyTorch 2.5.1+cu124 working (installed on H: in `.pydeps/`) |
| Disk | C: 6.4 GB free (too small for data); H: 213 GB free → all ML-03 data on H: |
| SNAP / GDAL CLI | not installed; rasterio 1.4.4 (bundled GDAL) and pyproj available |

## Repository state relevant to ML-03

| component | state |
|---|---|
| ML-01 (weekly SIC forecast, 25 km) | completed; U-Net operational; NSIDC CDR v6 SIC 1979–2026 on disk (3.3 GB) |
| ML-02 (weekly T2m forecast) | completed; U-Net operational |
| FastAPI (`api/main.py`) | ML-01 at `/`, ML-02 at `/temperature`, map layers at `/layers`, viewer at `/viewer/` |
| Frontend | static viewer in `frontend/` (no Next.js/CesiumJS code exists in the repository) |
| Satellite imagery | **none** (no SAR, no optical scenes) |
| Pixel-level sea-ice labels | **none** |
| SAR preprocessing / segmentation code | **none** |
| `EXTERNAL APIs/API.py`, `PRESSUREAPI.py` | ERA5 single/pressure-level CDS request templates; rely on `~/.cdsapirc` (absent); no credentials in the files |

## Credentials (presence only, values never read)

CDSE (Copernicus Data Space), Copernicus Marine, NASA Earthdata, CDS: **none configured** (no env vars, no `.netrc`, no `.cdsapirc`,
no `.copernicusmarine`, no `.env`).

## Reachable sources (HTTP checks on 2026-11-09)

| source | access | status |
|---|---|---|
| Microsoft Planetary Computer STAC `sentinel-1-grd` (official ESA GRD as COGs + SAFE annotation XMLs) | anonymous (SAS token) | **verified**: Antarctic EW GRDM HH scenes, overviews ×2…×64, GCPs, calibration + noise XML |
| Copernicus Data Space catalogue (OData) | search anonymous, download needs account | search reachable; download **blocked (no account)** |
| ASF search API | search anonymous, download needs Earthdata | search reachable; download **blocked (no account)** |
| U.S. National Ice Center Antarctic weekly/biweekly charts (SIGRID-3 shapefiles, 2003–2026) | anonymous | **verified** (downloaded 2023-02-03 chart: 514 polygons, CT codes 00…92) |
| Univ. Bremen AMSR2 ASI 3.125 km SIC | anonymous | reachable |
| OSI SAF (met.no THREDDS) | anonymous | reachable |
| NSIDC G02135 / G02202 | anonymous | reachable (G02202 already on disk) |
| Copernicus Marine SEAICE_ANT_PHY_AUTO_L3_NRT_011_012 (DMI-ASIP) | account required | one daily file present locally (`DATAS/dmi_asip_seaice_mosaic_ant_20230202.nc`) |
| AI4Arctic ASIP v2 (DTU) | anonymous, ~large; Arctic only | not used for Antarctic training/evaluation (see plan) |

## Consequences

* Imagery: Sentinel-1 EW GRDM (HH, single-pol over Antarctica) from Planetary Computer — no credentials needed.
* Labels: USNIC expert ice charts (independent of our model, but chart-scale and time-mismatched) → primary labels;
  DMI-ASIP (automated, Sentinel-1-derived) and AMSR2 ASI (passive microwave) → comparison only, never treated as ground truth.
* Manual annotation: protocol written; no annotators available in this session (documented in MISSING_PREREQUISITES.md).
