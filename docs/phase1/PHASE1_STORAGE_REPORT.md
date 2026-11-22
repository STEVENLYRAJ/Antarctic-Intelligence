# Phase 1 Storage Report (read-only inventory, 2026-11-11)

**Total working tree: about 105 GB** (`du -sh .`). Free space: H: 184 GB, C: 141 GB.

**Nothing has been deleted.** Every cleanup action below is a proposal that needs your approval. Original source data is never proposed for deletion.

## 1. Breakdown

| Path | Size | Category | Regenerable? | How to regenerate |
|---|---|---|---|---|
| `data/processed/aethentra/cnn/` | **31 GB** | ML-01 U-Net training arrays (`trainval_X.npy` 15.6 GB, `train_X.npy` 13.8 GB, `validation_X.npy` 1.9 GB, plus Y arrays) | Yes | `scripts/train_cnn.py` (stack stage); only needed to retrain |
| `data/processed/ml03/tiles/` | 11 GB | ML-03 U-Net tiles (memmaps) | Yes | `scripts/ml03/train.py` (tiles stage) |
| `data/processed/ml02/cnn/` | 8.0 GB | ML-02 U-Net training arrays | Yes | `scripts/ml02/train_cnn.py` |
| `.git/` | **7.45 GB** loose objects + 224 MB garbage | Git history, including large data blobs | Partly | See section 3 |
| `data/interim/ml02/ncep_r1/` | 7.2 GB | ML-02 regridded daily cubes | Yes | `scripts/ml02/preprocess.py` |
| `data/interim/ml03/scenes/` | 7.0 GB | ML-03 calibrated, warped Sentinel-1 scenes | Yes, but slowly (re-reads COGs) | `scripts/ml03/run_all.py --from preprocess` |
| `DATAS/glims_download_33432/` | 8.5 GB | **Original** GLIMS glacier download (Stage 1) | No (original) | Keep |
| `.pydeps/` | 4.4 GB | Local PyTorch install (C: was too small) | Reinstallable | **Required** by the U-Nets: keep |
| `data/raw/aethentra/` | 3.7 GB | **Original** NSIDC CDR v6 + NCEP R1 (ML-01) | Re-downloadable, but this is source data | Keep |
| `data/raw/sentinel1/` | 3.6 GB | **Original** Sentinel-1 COG subsets (ML-03) | Re-downloadable | Keep (provenance of the test set) |
| `data/interim/aethentra/` | 3.5 GB | SIC daily cube (1.8 GB, shared by ML-01 and ML-04) + `sic_stdev_daily.npy` (1.8 GB) | Yes | ML-01 preprocessing. Check whether `sic_stdev_daily.npy` is still used before removing it |
| `data/raw/ice_charts/` | 1.5 GB | **Original** USNIC charts (ML-03 labels) | Re-downloadable | Keep |
| `models/` | 1.4 GB | Checkpoints and final models | Final models: keep | — |
| `data/interim/ml04/` | 1.2 GB | ML-04 daily cubes | Yes (rebuilt in remediation A1) | `scripts/ml04/run_all.py --only preprocess` |
| `outputs/` | 1.1 GB | Forecasts, maps, figures | Mostly yes | Keep final products |
| `data/processed/ml04/` | 758 MB | ML-04 features and climatology | Yes | — |
| `data/processed/ml02/tables`, `aethentra/tables` | 1.4 GB | Tabular training sets | Yes | — |
| `data/raw/ml04/` | 416 MB | **Original** NCEP extra variables (**3 corrupt files**, see audit A1) | Re-download | Keep; replace the 3 corrupt files |
| `experiments/` | 398 MB | Metrics, logs, error maps | Keep the metrics | — |
| `data/raw/ncep_r1_2m/` | 113 MB | ML-02 NCEP air copy (different subset from ML-01's; **not** byte-identical) | — | Keep |
| `data/raw/station_observations/` | 121 MB | **Original** GHCN-D + Zenodo stations | — | Keep |
| `DATAS/Earthdata-Download-x64.exe` | 133 MB | Installer program, not data | — | Candidate to move out of the repository |

## 2. Duplicates found

These are byte-identical, checked with `cmp`:

- `models/final/sic_climatology.npz` and `models/artifacts/sic_climatology_1979_2020.npz` (41 MB)
- `models/ml02/final/t2m_climatology_ncep_r1.npz` and `models/ml02/artifacts/t2m_climatology_ncep_r1.npz` (281 MB)

The final-model copies are what the loaders read. The duplicates are small; leave them in place for the presentation.

## 3. Proposed safe cleanup (NOT executed; needs approval)

| # | Action | Frees | Risk | Recommendation |
|---|---|---|---|---|
| S1 | Unstage `data/processed/aethentra/cnn/trainval_*.npy` and add `data/processed/*/cnn/` to `.gitignore` | Prevents +16.5 GB in git | None | **Do (P0)** |
| S2 | Rewrite the 2 **unpushed** local commits without data blobs (GLIMS shapefile, CNN arrays, large climatologies, `.exe`); then `git gc` | About 7 GB of `.git` | Low (local history only; nothing is pushed) | **Do (P0)**, after a full copy of `.git` as backup |
| S3 | Delete the ML-01/ML-02/ML-03 training arrays (`*/cnn/`, `ml03/tiles`) | About 50 GB | Retraining would need to rebuild them (hours) | Optional; **after** 24 Nov |
| S4 | Delete `data/interim/ml02/ncep_r1` and `data/interim/ml03/scenes` | 14 GB | Rebuild takes hours; ML-03 on-demand inference reuses scenes | Not before 24 Nov |
| S5 | Move `DATAS/Earthdata-Download-x64.exe` out of the repository | 133 MB | None | Optional |
| S6 | Remove the git garbage (`tmp_obj_*`) with `git gc` | 224 MB | None | Together with S2 |

## 4. What the frontend must not load

The frontend never reads `data/`. It uses only:

- API responses;
- a presentation bundle of a few MB (pre-rendered PNGs in EPSG:4326 with bounds, GeoJSON contours, and JSON summaries and time series).

The bundle is planned as remediation item D3.
