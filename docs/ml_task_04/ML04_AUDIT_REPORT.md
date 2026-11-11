# ML-04 Audit Report: Repository and Infrastructure (Phase 0)

Audit date: 2026-11-11. Everything below was checked on disk or against the live source; nothing is assumed from earlier briefs.

## 1. Repository

| Item | Found | Notes |
|---|---|---|
| Python package | `src/aethentra/` (ML-01 sea ice, `temperature/` ML-02, `sar/` ML-03) | ML-04 is added as `src/aethentra/anomaly/` (separate package, same conventions) |
| API | FastAPI `api/main.py` + routers `api/temperature.py`, `api/seaice_detection.py`, `api/viewer.py` | ML-04 is added as `api/anomaly.py`, mounted under `/api/ml04` |
| Frontend | `frontend/` static viewer (HTML/JS/CSS, served at `/viewer/`) | **No Next.js or CesiumJS app exists in the repository** (no `package.json`). ML-04 is integrated into the existing viewer; a Next.js/Cesium dashboard remains future work |
| Database | **None configured.** No Supabase client, URL or schema anywhere in the repository | ML-04 uses a local SQLite event store with the requested schema, plus a PostgreSQL/Supabase migration file that has **not** been applied to any remote project |
| `EXTERNAL APIs/API.py`, `PRESSUREAPI.py` | Present: `cdsapi` request templates for ERA5 single and pressure levels | They contain no credentials. They need a personal CDS token (`~/.cdsapirc`), which is not configured, so ERA5 cannot be downloaded |
| Tests | `tests/` (pytest; 70 tests across ML-01…03 + viewer) | ML-04 tests are added as `tests/test_ml04_anomaly.py` |
| Notebooks | `notebooks/` holds no ML-04 notebooks | Analysis is done with scripts (`scripts/ml04/`), which are more reproducible here than notebooks |

## 2. Existing datasets relevant to ML-04 (verified)

| Dataset | Location | Coverage | Status |
|---|---|---|---|
| NCEP/NCAR R1 daily `air` (sigma 0.995), `slp`, `uwnd`, `vwnd`; lat ≤ 35° S | `data/raw/aethentra/ncep_r1/` (+ provenance JSON, MD5) | 1979-01-01 … **2026-03-17** | Reused in place |
| NOAA/NSIDC SIC CDR v6 (G02202), 25 km EPSG:3412, daily | `data/raw/aethentra/nsidc_g02202_v6/`; daily cube `data/interim/aethentra/sic_daily.npy` (MD5-verified inputs, 2 missing days) | 1979-01-01 … 2026-11-01 | Reused (cube and grid with 5 sectors) |
| NSIDC Sea Ice Index v4 daily southern extent | `data/raw/antarctic/external/nsidc_g02135_south/` | 1978 … 2026-10-09 | Used as an independent extent cross-check |
| GHCN-Daily Antarctic stations (45 selected) | `data/raw/station_observations/ghcnd/` | 1973 … 2026 (varies by station) | Used for the in-situ temperature check |
| Antarctic station daily series (Zenodo record 17164992, 18 stations) | `data/raw/station_observations/zenodo_17164992/` | varies | Secondary in-situ check |
| DMI-ASIP SIC mosaic (1 day), ice charts, Sentinel-1 | `DATAS/`, `data/raw/ice_charts`, `data/raw/sentinel1` | — | Not relevant to ML-04 |

**Important coverage fact:** NOAA PSL's NCEP/NCAR R1 daily files end on **2026-03-17**. I checked the remote OPeNDAP time axis on 2026-11-11. As a result:

- The last complete month with all atmospheric variables is **February 2026**.
- From March 2026 onward, only sea-ice anomalies can be computed.
- The 2026 `uwnd` file reports 365 time steps, while `air` and `slp` report 76. The missing days are checked and masked in preprocessing (Phase 2).

## 3. Datasets not available (and why)

| Requested | Status | Requirement |
|---|---|---|
| ERA5 (CDS) | Not acquired | Personal CDS API token (`CDSAPI_KEY`) plus accepted ERA5 licence |
| MERRA-2 | Not acquired | NASA Earthdata login |
| Copernicus Marine (SST, ice thickness, drift) | Not acquired | Copernicus Marine account |
| Separate snowfall and snow depth | Not available | NCEP R1 has no daily snowfall field, and its snow fields over the ice sheet are not physically meaningful. Precipitation rate (`prate`) is used and named "precipitation", not "snowfall" |
| SCAR READER | Not downloaded | GHCN-Daily station data already on disk covers the station-check role |

These gaps are documented requirements; independent work continues on public data.

## 4. Variables acquired for ML-04 (Phase 1, public OPeNDAP, no login)

`rhum` (sigma 0.995 relative humidity), `prate` (surface precipitation rate, T62 Gaussian), `tcdc` (total cloud cover, T62 Gaussian) and `hgt` at 500 hPa, 1979–2026, lat ≤ 35° S. All are stored in `data/raw/ml04/ncep_r1/` with provenance sidecars.

## 5. Compute

| Resource | Value |
|---|---|
| CPU | 16 logical cores |
| RAM | 25.4 GB (Windows; commit limit lower because the pagefile is small) |
| GPU | NVIDIA GeForce RTX 4060 Laptop, 8 GB (PyTorch 2.5.1 + CUDA 12.4) |
| Disk | H: 188 GB free, C: 146 GB free |

Problem sizes are small at the chosen resolution (2.5° grid south of 50° S, 2,304 cells; about 1.3 M cell-months). Isolation Forest, LOF and One-Class SVM are feasible on CPU (OCSVM on a subsample), and a small autoencoder trains in minutes on the GPU.

## 6. Existing ML outputs (ML-01…03)

- **ML-01:** weekly SIC forecast (operational U-Net plus a SIC-only fallback).
- **ML-02:** weekly T2m forecast (U-Net).
- **ML-03:** SAR sea-ice segmentation with a weekly composite.

All three are served at `/viewer/`. ML-04 reuses their conventions:

- provenance sidecars;
- a frozen validation decision followed by a single test evaluation;
- no file paths in API responses;
- `data_type` labels on every layer.

ML-04 does not depend on their predictions.
