# AETHENTRA ML-02 — Missing Prerequisites

| # | Prerequisite | Needed for | Status | Action |
|---|---|---|---|---|
| 1 | Copernicus CDS account + API key in `%USERPROFILE%\.cdsapirc` (never in the repo) and acceptance of the ERA5 licence on the CDS website | ERA5 daily T2m (primary target) and predictors | **Missing — user is adding it** | File format: `url: https://cds.climate.copernicus.eu/api` / `key: <personal access token>`. Then `python scripts/ml02/download_data.py --era5`. |
| 2 | PyTorch (CUDA build) | CNN / ConvLSTM / U-Net candidates | Not installed | Only after the tree-model baseline is established (decision gate in the plan). |
| 3 | cfgrib / eccodes | GRIB input | Not installed | Not needed: all retrievals are requested as NetCDF. |
| 4 | Antarctic frontend (Next.js / CesiumJS) | Phase 14 display | Not in this repo | Layers are exported as GeoTIFF/PNG/GeoJSON/JSON for later integration. |
| 5 | Independent sea-ice / temperature expert review | Scientific sign-off | Not available | Documented as a limitation. |

Work that does **not** depend on #1 proceeds immediately: station acquisition (Zenodo, GHCN-Daily), pipeline code,
tests on synthetic data, and an interim real-data run on NCEP/NCAR R1 2 m temperature (anonymous) clearly labelled as interim.
