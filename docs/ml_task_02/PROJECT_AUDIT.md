# AETHENTRA ML-02 — Project Audit (Phase 0)

Audit date: 2026-11-08. Everything below was inspected on disk or queried live; nothing is assumed from earlier discussions.

## 1. Repository state

| Component | Status | Evidence |
|---|---|---|
| Git repo `main`, 2 commits (`528e314`, `eb03a93`) | Verified existing | `git log` |
| `DATAS/` user-collected files (8.9 GB, 36 inventoried files) | Verified existing | `metadata/antarctic_dataset_inventory.csv` (Stage 1) |
| Stage-1 preprocessing (`data/src/preprocessing/antarctic/`) incl. `era5_api.py` (AST-parses the CDS scripts, dry-run size guard) | Verified existing | source inspected |
| `EXTERNAL APIs/API.py`, `PRESSUREAPI.py` | Verified existing — **request definitions only, no credentials**. API.py: 25 ERA5 single-level variables, 1996–2026, 4×daily, global. PRESSUREAPI.py: 13 variables × 6 levels, 2000–2026, global. Both would be multi-TB requests; they are not executed. | source inspected (keys redacted on read; none present) |
| ERA5 NetCDF output of those scripts | **Missing** — no ERA5 file anywhere in the repo | file search |
| CDS credentials (`%USERPROFILE%\.cdsapirc`, `CDSAPI_URL/KEY`) | **Missing** at audit time; user will add a key | checked existence only |
| ML-01 sea-ice module (`src/aethentra/`, configs, scripts, api, models, experiments) | Verified existing; **pipeline still executing** at audit time (candidates trained and validated; tune/select/final/test pending) | `models/checkpoints/*`, `experiments/metrics/validation_candidates/summary.json` |
| ML-01 data: NOAA/NSIDC SIC CDR v6 daily 1979–2026 (48 files, MD5-verified, 3.3 GB) + 25 km cube | Verified existing | provenance JSONs |
| ML-01 data: NCEP/NCAR R1 daily `air.sig995`, `uwnd`, `vwnd`, `slp` south of 35°S, 1979–2026-03-17 (192 files, 422 MB) | Verified existing | provenance JSONs |
| FastAPI service `api/main.py` (ML-01 endpoints `/health`, `/model/info`, `/forecast/*`) | Verified existing — ML-02 must not break it | source inspected |
| Notebooks | **Missing** (`notebooks/` empty) | |
| Frontend (Next.js / CesiumJS) | **Missing** in this repo (no `package.json`) — layers are prepared as files only | file search |
| ML-02 code, data, models | **Missing** (nothing pre-existing) | |

## 2. Environment

| Item | Value |
|---|---|
| OS / Python | Windows 11, Python 3.11.9 |
| CPU / RAM | 8 physical / 16 logical cores, 25.4 GB RAM (≈3 GB free while ML-01 runs) |
| GPU | NVIDIA RTX 4060 Laptop, 8 GB (PyTorch **not installed**) |
| Free disk (H:) | 289 GB |
| Key packages | xarray 2026.9, netCDF4 1.7.4, h5netcdf 1.8.1, lightgbm 4.7, xgboost 3.2, scikit-learn 1.9.1, optuna 5.0, pyproj 3.7.2, rasterio 1.4.4, fastapi 0.135, cdsapi and nbformat 5.11 (installed in this phase). Missing: cfgrib/eccodes (GRIB), zarr, torch, shap. |

## 3. External sources checked live

| Source | Result |
|---|---|
| ERA5 single levels / daily statistics (CDS) | Downloadable after free registration + licence acceptance; credentials pending |
| ERA5 pressure levels (CDS) | Downloadable after registration (same key) |
| Zenodo 17164992 "Daily Temperature and Temperature Anomaly Data at Staffed Antarctic Stations" (2025-09-20, CC-BY-4.0) | Downloadable anonymously; 16 stations × (daily T, daily anomaly) CSV, MD5 per file |
| SCAR READER (legacy.bas.ac.uk/met/READER) | Reachable (HTTP 200); monthly means — not used for weekly validation |
| NOAA GHCN-Daily | Reachable; 102 stations south of 60°S, 45 with TAVG spanning ≤1990…≥2020 |
| NCEP/NCAR R1 daily 2 m air temperature (PSL OPeNDAP) | Downloadable anonymously (interim development source only) |

## 4. Consequences for ML-02

* ERA5 is the designated primary source but must be downloaded first (credentials). The pipeline is written source-agnostic
  (`source: era5 | ncep_r1`) so development and tests proceed now; the scientific results are produced from ERA5 if it arrives.
* Station data are an **independent** check (point vs. 25 km cell); ERA5 assimilates many of these stations' SYNOP reports,
  so station agreement is "partially independent" and is reported separately from reanalysis-based skill.
* ML-01 SIC observations (not forecasts) are available as optional historical predictors on the same 25 km grid.
* Deep learning (CNN/ConvLSTM/U-Net) requires installing PyTorch (CUDA); deferred behind the tree-model baseline (decision gate in
  `ML02_IMPLEMENTATION_PLAN.md`).
