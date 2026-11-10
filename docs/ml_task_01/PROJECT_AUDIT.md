# AETHENTRA ML Task 01 — Project Audit (Phase 0)

Audit date: 2026-11-08. Repository: `scientific-intelligence` (AETHENTRA Scientific Intelligence Platform). Status labels used throughout:
**VERIFIED** (inspected on disk / executed), **DOWNLOADABLE** (official source confirmed reachable), **PROPOSED**, **MISSING**, **UNVERIFIED**.

## 1. Repository state (VERIFIED)

| Item | Finding |
|---|---|
| Git history | 2 commits: `528e314 Added Initial files`, `eb03a93 Stage ! of Preprocessing ... completed` (Antarctic preprocessing stage 1). Branch `main`. |
| Code | `data/src/preprocessing/antarctic/` — Stage-1 inventory/validation pipeline (NetCDF, CSV, GLIMS, KMZ, ERA5 handlers). Placeholder modules `data/src/preprocessing/{biodiversity,genomics,geospatial,medicine,tabular}.py` and `data/src/pipeline.py` are **empty (0 bytes)**. |
| Existing ML assets | **None.** No model files, checkpoints, experiment logs, notebooks with results, or training code existed before this task. |
| Backend / database | **None found.** No FastAPI/Flask/Django app, no DB config, no Next.js frontend in the repository. Architecture diagrams (`AETHENTRA Scientific Intelligence Architecture.png`, `...Roadmap.png`, `mermaid-diagram.png`) and `AETHENTRA_AI_ML_Models_Guide.docx` describe a *planned* platform. |
| Guide document | `AETHENTRA_AI_ML_Models_Guide.docx` (Oct 2026) recommends: climatology + persistence baselines → XGBoost/LightGBM MVP → U-Net / ConvLSTM only after baselines and consistent grids exist. This task follows that decision gate. |
| Dependencies | `requirements.txt` (Stage-1 libraries). Pre-installed: fastapi 0.135, uvicorn 0.42, pydantic 2.12, pyyaml, httpx. Installed for this task: scikit-learn, xgboost, lightgbm, optuna, scipy, joblib, psutil. **Not installed:** torch (≈2.5 GB CUDA wheel; see MISSING_PREREQUISITES.md), shap (TreeSHAP is obtained from the boosters' native `pred_contrib`). |
| `EXTERNAL APIs/API.py`, `PRESSUREAPI.py` | CDS ERA5 request scripts (single levels: 25 vars 1996–2026; pressure levels: 13 vars × 6 levels 2000–2026, global). They output **NetCDF**, not JSON. **No output from either script exists anywhere in the repository** (re-verified). `cdsapi` is not installed and no CDS credentials are configured. |
| Existing JSON "API responses" | `DATAS/edsc_collection_results_export.json` (NASA Earthdata Search catalog export, 97 collection records) and seven `DATAS/*.umm_json` files (NASA CMR UMM *service/tool* records for NSIDC access tools: `NSIDC_CPRD_S3`, `NSIDCV0_DAAC_Data_HTTPS_File_System`, `NSIDC_CPRD_EARTHACCESS`, GLIMS viewers). These are **metadata, not scientific datasets**. |
| Git hygiene risk | Commit `eb03a93` added `DATAS/` raw data to Git, incl. `glims_polygons.shp` (2.1 GB) and `glims_polygons.dbf` whose recorded size (2,598,908,176 B) is the true 6.9 GB size wrapped at 2^32 bytes. Large raw data in Git is a risk; this task adds a `.gitignore` for new raw/interim data and model binaries (existing history untouched). |

## 2. Compute resources (VERIFIED)

| Resource | Value |
|---|---|
| CPU | AMD64 Family 25 (Zen 3/4), 16 logical cores |
| RAM | 23.7 GB total (≈5 GB free at audit time — feature pipelines are streamed / memory-mapped) |
| GPU | NVIDIA GeForce RTX 4060 Laptop, 8 GB (usable by XGBoost `cuda`) |
| Disk | H: 370 GB, 278 GB free |
| Network | ≈0.5 MB/s sustained from NSIDC (measured: 73.6 MB in 152 s) — the main practical constraint |

## 3. Local datasets relevant to sea-ice forecasting (VERIFIED)

Full per-file inventory with suitability: `DATA_INVENTORY.csv`. Summary:

| Dataset | Verdict for weekly SIC forecasting |
|---|---|
| `DATAS/dmi_asip_seaice_mosaic_ant_20230202.nc` (CMEMS SEAICE_ANT_PHY_AUTO_L3_NRT_011_012) | **Not suitable as training data**: a single day; 98.7 % fill; 1 km SAR grid. Usable only as a qualitative high-resolution comparison. |
| `DATAS/ANTARCTIC_OMI_SI_extent_...nc` (CMEMS OMI) | Monthly hemispheric extent only (no grid). **Comparison only.** |
| `data/raw/antarctic/external/nsidc_g02135_south/` (Sea Ice Index v4 daily extent) | Hemispheric daily extent, independent product → **comparison of derived extent**. |
| `DATAS/N_seaice_extent_climatology...csv`, `Cda_ArcticOIB...nc` | Arctic — not applicable. |
| GLIMS, PGC LiDAR tiles, TIFF photo, catalogs | Not applicable to SIC forecasting. |

**Conclusion:** no multi-year gridded sea-ice concentration record existed locally. A primary dataset had to be acquired.

## 4. External datasets investigated (Phase 2 summary)

| Candidate | Access (VERIFIED by request) | Decision |
|---|---|---|
| NSIDC-0803 *AMSR2 Daily Polar Gridded SIC v1* | NASA DAAC; Earthdata Login required; AMSR2 era only (2012+) | Rejected as primary: too short for a 1979–2015 training period; login needed. |
| **NOAA/NSIDC SIC CDR G02202 v6** | **Public HTTPS, no login**, daily 25 km SH grid 1978-10-25 → 2026-11-01, yearly aggregates + MD5 manifests | **Selected primary label + SIC predictor dataset.** |
| NSIDC Sea Ice Index (G02135 v4) | Public HTTPS | Independent extent comparison (already local). |
| CMEMS SEAICE_GLO_SEAICE_L4_REP_OBSERVATIONS_011_009 (OSI SAF CDR) | Copernicus Marine account required | Not acquired (credentials). Documented as the preferred independent gridded comparison. |
| CMEMS ANTARCTIC_OMI_SI_extent (reanalysis) | Copernicus Marine account | Not acquired; the *observation* OMI file is local and used for comparison. |
| ERA5 single/pressure levels | CDS token required — **not configured** | Not acquired. |
| **NCEP/NCAR Reanalysis 1 daily** | **Public OPeNDAP (NOAA PSL), no login** | **Selected as interim atmospheric predictor source** (clearly labelled as ERA5 substitute). |
