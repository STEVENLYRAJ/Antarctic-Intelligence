# AETHENTRA ML Task 02 — Final Report
## Antarctic Weekly 2 m Temperature & Temperature-Anomaly Forecasting

**Truth = NCEP/NCAR Reanalysis 1 (interim substitute for ERA5).** All skill numbers below are agreement with NCEP R1, not with ERA5 and not with direct observations.

Status legend: **COMPLETED** = implemented, executed on real data and checked; **IMPLEMENTED** = code + tests, not executed on real data; **PENDING** = blocked by a prerequisite; **NOT DONE** = documented gap.

## 1. Scientific objective

Forecast the 7-day-mean 2 m air temperature and its anomaly (vs a fixed 1981–2010 daily climatology) for days t+1…t+7 over Antarctica and the Southern Ocean south of 60°S on a 25 km grid, with warm/cold/extreme anomaly categories. This is a statistical forecast learnt from reanalysis, not a numerical weather prediction.

## 2. Phase status

| phase | status | evidence |
|---|---|---|
| 0 Audit | COMPLETED | PROJECT_AUDIT.md, DATA_INVENTORY.csv, MISSING_PREREQUISITES.md, ML02_IMPLEMENTATION_PLAN.md |
| 1 Acquisition | COMPLETED (interim + stations); ERA5 **PENDING** (CDS key) | TEMPERATURE_DATA_SOURCES.md, provenance JSONs |
| 2 Exploration & validation | COMPLETED | DATA_QUALITY_REPORT.md, outputs/ml02/figures/data_quality/, notebooks/01_temperature_exploration.ipynb |
| 3 Preprocessing | COMPLETED | PREPROCESSING_DOCUMENTATION.md, data/interim/ml02/ncep_r1/cube_meta.json |
| 4 Climatology & labels | COMPLETED | CLIMATOLOGY_AND_LABELS.md |
| 5 Features | COMPLETED | FEATURE_ENGINEERING.md, experiments/ml02/metrics/analysis/ |
| 6 Baselines | COMPLETED | 5 baselines on identical origins and masks |
| 7 Models | COMPLETED (tree models); U-Net IMPLEMENTED, not trained (PyTorch is not installed) | MODEL_TRAINING_REPORT.md |
| 8 Splits | COMPLETED | train ['1979-01-01', '2010-12-31'], validation ['2011-01-01', '2017-12-31'], test ['2018-01-01', '2025-12-31'] |
| 9 Evaluation | COMPLETED | MODEL_EVALUATION_REPORT.md |
| 10 Optuna / final / single test | COMPLETED | selection_record.json frozen 2026-11-07T23:32:43.329940+00:00; test 2026-11-07T23:45:07.364854+00:00 |
| 11 Interpretability & stations | COMPLETED | MODEL_INTERPRETABILITY_REPORT.md |
| 12 Inference | COMPLETED | MODEL_OUTPUT_SCHEMA.md, outputs/ml02/forecasts/t2m7d_20251231_aethentra-t2m-weekly-20261108-v1/t2m7d_20251231_aethentra-t2m-weekly-20261108-v1.json |
| 13 FastAPI | COMPLETED locally (TestClient tests + live uvicorn on 127.0.0.1) — not a production deployment | api/temperature.py under /temperature, api/viewer.py |
| 14 Frontend layers | COMPLETED (layers) + web viewer COMPLETED | layers/manifest.json, frontend/, /viewer/ |
| 15 Tests | COMPLETED for ML-02 (all ML-02 tests pass); repository suite has failures | whole repository: 56 passed, 1 failed, 2 skipped (2026-11-08T09:52:35+00:00); failed: tests.test_antarctic_preprocessing::test_inventory_covers_all_raw_files — The failure is the pre-existing Stage-1 inventory test: 8 user files added to DATAS/ after the Stage-1 inventory (services*.umm_json, tools*.umm_json) are not in metadata/antarctic_dataset_inventory.csv. Not related to ML-01/ML-02; the Stage-1 inventory was not regenerated without a request. |

## 3. Final test metrics (single evaluation)

* Test 2018-01-07 … 2025-12-21 (416 weekly issue dates, all 55,512 cells each): area-weighted anomaly MAE **2.471 °C**, RMSE **3.719 °C**, bias -0.253 °C, ACC 0.542, R² (absolute T2m) 0.957, R² (anomaly) 0.278.
* MSE skill: vs climatology 0.299, vs persistence 0.547, vs damped persistence 0.150.
  * baseline climatology: MAE 2.999, RMSE 4.441, ACC n/a.
  * baseline persistence: MAE 3.644, RMSE 5.527, ACC 0.476.
  * baseline persistence_week: MAE 3.162, RMSE 4.775, ACC 0.416.
  * baseline recent_trend: MAE 3.955, RMSE 5.949, ACC 0.367.
  * baseline damped_persistence: MAE 2.702, RMSE 4.033, ACC 0.418.

Independent stations (40 stations, 10,394 station-weeks, test period): weekly-anomaly RMSE final model 3.20 °C (r = 0.39), persistence 5.10 °C, climatology 3.48 °C; the verifying reanalysis itself 2.39 °C (r = 0.78).

## 4. Model selection

Selected **lgbm_tuned** on validation only (validation 2011-2017 full-grid, rank-sum of all:area_weighted_rmse_degC, antarctica_land:area_weighted_rmse_degC, all:acc_pattern_mean, all:area_weighted_mae_degC); best baseline damped_persistence.

## 5. Documents

TEMPERATURE_DATA_SOURCES.md · DATA_QUALITY_REPORT.md · PREPROCESSING_DOCUMENTATION.md · CLIMATOLOGY_AND_LABELS.md · FEATURE_ENGINEERING.md · MODEL_TRAINING_REPORT.md · MODEL_EVALUATION_REPORT.md · MODEL_INTERPRETABILITY_REPORT.md · MODEL_CARD.md · MODEL_OUTPUT_SCHEMA.md · REPRODUCIBILITY_GUIDE.md · NEXT_STEPS.md

## 6. Blockers and limitations

* **ERA5 not acquired** (no CDS key during this run) → all results use NCEP/NCAR R1 as interim truth; ERA5 pipeline is implemented and switchable by configuration (TEMPERATURE_DATA_SOURCES.md).
* Deep learning: U-Net IMPLEMENTED, not trained (PyTorch is not installed).
* Station data are only partially independent of reanalysis; Zenodo station series end in 2022.
* The API runs locally; it is not a production deployment.
* Web viewer (`frontend/`, served by FastAPI at `/viewer/`; `/` redirects there): COMPLETED and run locally — sea-ice and 2 m temperature tabs, polar-stereographic previews rendered server-side from the native EPSG:3412 GeoTIFFs (`/layers/{sic|t2m}/…`), GeoTIFF downloads, every layer badged by data_type (forecasts framed and stamped MODEL PREDICTION), forecast summary, test skill and limitations. Start with `bash scripts/serve.sh` (loopback 127.0.0.1:8000). Not a production deployment: no authentication, TLS, process supervision or public hosting — those need an owner decision on where to host.