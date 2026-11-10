# AETHENTRA ML-02 — Implementation Plan

Status labels: PLANNED → IMPLEMENTED (code + unit tests) → EXECUTED (run on real data) → VALIDATED (results checked) → COMPLETED.

## Scientific definition (fixed before any data is seen)

* **Issue time t** = 23:59 UTC of the issue day; inputs are daily means of days ≤ t.
* **Target window** = days t+1 … t+7 (UTC days). Labels:
  * A: weekly-mean 2 m temperature T̄(t+1..t+7) in °C.
  * B: weekly anomaly A = T̄ − C̄, with C̄ the mean of the 7 daily climatological values of the target days.
  * Categories from training-period per-cell, per-season anomaly σ (±1σ, ±2σ); warm/cold/extreme indicators.
* **Grid**: the ML-01 NSIDC 25 km polar-stereographic grid (EPSG:3412), cells with latitude ≤ 60°S. ERA5 0.25° fields are
  bilinearly interpolated onto it (0.25° ≈ 28 km meridionally, so the target is not materially degraded; the lat-lon
  oversampling near the pole is removed; cells become near-equal-area and align with ML-01 sea ice).
  Land/ice-sheet vs ocean: ERA5 land-sea-mask fraction interpolated as a continuous fraction, then ≥ 0.5 → land (no
  nearest/bilinear interpolation of a categorical class). Elevation from ERA5 surface geopotential / g.
* **Climatology**: 1981–2010 (WMO normal entirely inside the training period → no leakage), daily day-of-year means
  smoothed with a ±15-day circular window, per cell. 1991–2020 rejected: it overlaps validation and test.
* **Splits** (chronological; targets never cross boundaries): train 1979–2010, validation 2011–2017, test 2018–2025.
  Rolling-origin check on the training years. Test evaluated once after a frozen selection record.
* **Cadence**: one issue date every 7 days.

## Phases

| Phase | Deliverable | Plan |
|---|---|---|
| 0 | Audit | `PROJECT_AUDIT.md`, `DATA_INVENTORY.csv`, `MISSING_PREREQUISITES.md`, this plan |
| 1 | Acquisition | ERA5 daily statistics via `cdsapi` (t2m first, then msl, u10, v10, d2m, tcc, z500, t850; invariants lsm, z); stations (Zenodo 17164992, GHCN-Daily); interim NCEP R1 air.2m; provenance + MD5 per file |
| 2 | Validation | units, coordinates, duplicates, gaps, ranges; figures; `notebooks/01_temperature_exploration.ipynb` |
| 3 | Preprocessing | daily cube on the 25 km grid (int16, 0.01 °C), masks, areas, elevation, regions |
| 4 | Climatology & labels | train-only climatology, labels A/B, σ thresholds |
| 5 | Features | lags (1–8 weeks), anomalies, rolling stats, trends, atmosphere, season, space, optional SIC; train-only fits |
| 6 | Baselines | climatology (A=0), persistence (last-day anomaly and last-week anomaly), damped recent trend |
| 7 | Models | LightGBM, XGBoost, Random Forest on sampled cell×issue rows (anomaly target); DL gate below |
| 8 | Splits | as above, plus regional / seasonal breakdowns and station check |
| 9 | Evaluation | MAE/RMSE/bias/R², area-weighted; anomaly ACC & skill vs climatology/persistence; categories; regions |
| 10 | Tuning | Optuna on validation only; refit train+validation; single test |
| 11 | Interpretability | TreeSHAP, permutation, response curves, residual analysis, station comparison |
| 12–14 | Inference, API, layers | `src/aethentra/temperature/inference`, `api` router under `/temperature`, GeoTIFF/PNG/GeoJSON layers |
| 15 | Tests | synthetic-data unit tests + integration tests |

**Deep-learning decision gate**: train a U-Net/ConvLSTM only if (a) PyTorch with CUDA can be installed, (b) the tree model
is complete, and (c) time remains; it must beat the selected tree model on validation to be considered.

## Code layout (adapted to the existing repository)

ML-01 already owns `src/aethentra/{features,baselines,models,training,evaluation,inference}`. ML-02 is therefore a
self-contained subpackage `src/aethentra/temperature/` with sub-modules `data, preprocessing, climatology, labels,
features, baselines, models, training, evaluation, inference`, configs in `configs/ml02/`, scripts in `scripts/ml02/`,
data in `data/raw/era5`, `data/raw/station_observations`, `data/interim/ml02`, `data/processed/ml02`, models in `models/ml02/`,
experiments in `experiments/ml02/`, outputs in `outputs/ml02/`, docs in `docs/ml_task_02/`.
