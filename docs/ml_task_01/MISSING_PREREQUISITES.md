# Missing Prerequisites (Phase 0)

Each item states the exact requirement, its impact, and what was done instead. Nothing below is silently substituted.

| # | Missing resource | Exact requirement | Impact | Mitigation in Task 01 |
|---|---|---|---|---|
| 1 | **ERA5 atmospheric data** (project's preferred predictors) | A Copernicus CDS account + personal access token, supplied via `~/.cdsapirc` or env vars `CDSAPI_URL`/`CDSAPI_KEY` (see `.env.example`), plus `pip install cdsapi`. Licence must be accepted on the CDS dataset page. | Atmospheric predictors cannot come from ERA5. | NCEP/NCAR Reanalysis 1 daily means (public OPeNDAP) used as an **interim** substitute; feature code is source-agnostic so ERA5 can be swapped in. The value of atmospheric inputs is measured by an ablation (with vs without). |
| 2 | Outputs of `EXTERNAL APIs/API.py` / `PRESSUREAPI.py` | Same CDS credentials; the scripts as written request ≈4.7 TB and ≈12.7 TB (global, full period) and should be split/area-restricted. | None used. | `data/src/preprocessing/antarctic/era5_api.py` (Stage 1) provides a guarded, Antarctic-restricted retrieval wrapper. |
| 3 | Copernicus Marine products (OSI SAF SIC CDR 011_009, sea-ice drift 011_018, extent reanalysis) | Free Copernicus Marine account; `copernicusmarine login`. | No independent *gridded* SIC comparison; no drift/thickness predictors. | Independent *extent* comparison uses NSIDC G02135 and CMEMS OMI (local). |
| 4 | NASA Earthdata (NSIDC DAAC: NSIDC-0803, GLIMS DAAC) | Earthdata Login account (`.netrc` or `earthaccess`). | NSIDC-0803 AMSR2 SIC not used. | G02202 v6 CDR is public and covers 1978–2026. |
| 5 | PyTorch (CNN / ConvLSTM / U-Net) | `pip install torch --index-url https://download.pytorch.org/whl/cu124` (≈2.5 GB). At the measured ≈0.5 MB/s this is ≈1.5 h of bandwidth competing with the 3.3 GB label download. | Deep spatial models not trained in Task 01. | Deferred by the guide's decision gate (tree models + baselines first). Documented in NEXT_STEPS.md. |
| 6 | Sea-ice thickness, ocean temperature/salinity/heat content, drift | Products identified (CMEMS, ORAS5/GLORYS) but all need accounts. | Not used. | Listed as next research step. |
| 7 | Backend/frontend code base | No existing FastAPI/Next.js code in the repository. | Integration cannot be "into" an existing service. | A standalone FastAPI service (`api/`) and frontend data-layer exports are provided as an integration-ready interface. |
| 8 | Domain-expert review | A sea-ice scientist to review physical plausibility. | Required before public scientific use. | Recommended in MODEL_CARD.md. |
