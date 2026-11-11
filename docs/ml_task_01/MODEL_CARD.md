# Model Card — AETHENTRA Antarctic Weekly Sea-Ice Concentration Forecast

## Operational model: U-Net (addendum)

The U-Net beat the frozen tree selection `lgbm_residual_tuned` on 4/4 selection criteria on validation (decision frozen 2026-11-09T03:36:53.145488+00:00, before its test evaluation) and now produces the forecasts. The tree model documented below remains the frozen selection and the fallback.
When fewer than 5 of 7 atmospheric days are available (all issue dates after 2026-03-17 at present), the forecast uses the SIC-only tree fallback declared before the test, because the U-Net was validated with atmospheric inputs only.
No uncertainty interval is exported for U-Net forecasts (interval coverage was assessed around the tree model only).

* U-Net (`cnn_unet_residual`): 7,773,697 parameters, 34 epochs, best epoch 26 (validation mae 2.576), 84 min on cuda; 34 dynamic + 5 static channels; loss l1.

| criterion (validation) | U-Net | lgbm_residual_tuned | U-Net better |
|---|---|---|---|
| siz_mae | 2.767 | 3.058 | yes |
| siz_rmse | 6.364 | 7.130 | yes |
| iiee | 502,112.958 | 585,508.141 | yes |
| extent_mae | 79,879.693 | 116,514.113 | yes |

* Decision (frozen 2026-11-09T03:36:53.145488+00:00, validation only): U-Net better on 4/4 selection criteria; replaces the operational model: **True** (the U-Net replaces the operational model only if it is better on ALL validation selection criteria).
* Single test evaluation of `test_cnn_addendum` (260 issue dates, 2021-01-03 … 2025-12-21, evaluated 2026-11-09T10:48:38.948388+00:00):

| test metric | U-Net | tree final model |
|---|---|---|
| SIZ MAE (pp) | 2.752 | 3.017 |
| SIZ RMSE (pp) | 6.474 | 7.141 |
| IIEE (km²) | 516,507 | 584,559 |
| extent MAE (km²) | 106,184 | 127,375 |


**Version** `aethentra-sic-weekly-20261108-v1` · **Family** lightgbm gradient-boosted trees (745 trees) · **Selected candidate** LightGBM residual (Optuna-tuned) · **Trained** 2026-11-07T23:02:24+00:00

## Intended use

* One-week-ahead outlook of Antarctic sea-ice concentration for scientific exploration and visualisation in AETHENTRA.
* **Not** for navigation, operational ice services, or decisions affecting safety. Not a substitute for official ice charts.

## What it predicts

* Output: mean SIC (%) over days t+1…t+7 for every ocean cell of the NSIDC 25 km polar-stereographic grid (EPSG:3412), issued at the end of day t.
* Derived: sea-ice extent and area (km²) with the 15 % threshold, hemispheric and per sector.
* Internally the model predicts the change relative to persistence (residual target); output is clipped to [0, 100].

## Inputs

* Daily NOAA/NSIDC CDR v6 SIC for days t−55…t (+ CDR uncertainty for t−6…t); training-period climatology (1979–2020).
* Past-week NCEP/NCAR R1 near-surface air temperature, winds and sea-level pressure (interim substitute for ERA5).
* 40 features — see FEATURE_ENGINEERING.md. Input schema: `src/aethentra/inference/prediction_schema.py`.

## Training data

* Issue dates 1979-01-01 … 2020-12-31 (weekly), 3,433,423 sampled cell-weeks.
* Hyper-parameters selected on 2016–2020 validation only; test 2021–2025 used once.

## Performance on the untouched test period (2021–2025)

| Metric | Final model | Persistence | Skill vs persistence |
|---|---|---|---|
| SIZ MAE (pp) | 3.02 | 3.70 | +18.5 % |
| SIZ RMSE (pp) | 7.14 | 8.72 | +18.1 % |
| Ice-edge-band MAE (pp) | 10.24 | 11.89 | +13.9 % |
| Area-weighted RMSE, all ocean (pp) | 4.82 | 5.88 | +18.0 % |
| Extent MAE (10³ km²) | 127.38 | 394.81 | +67.7 % |
| Area MAE (10³ km²) | 119.18 | 320.59 | +62.8 % |
| IIEE (10³ km²) | 584.56 | 696.33 | +16.1 % |
| Ice-edge IoU (≥15 %) | 0.949 | 0.939 | |

## Uncertainty

80 % quantile interval: test coverage 0.881 (nominal 0.80) → **not** exported (calibration not verified).

## Limitations and known failure modes

* Errors are largest in the marginal ice zone and during rapid advance/retreat; see seasonal and ice-edge tables in MODEL_EVALUATION_REPORT.md.
* Seasons where it does not beat persistence on SIZ MAE: none.
* Passive-microwave SIC underestimates concentration over melt ponds / wet snow in summer and over thin ice; the model inherits these biases.
* No forecast of the target-week weather is used; extreme wind events during the target week are not anticipated.
* 2.5° atmospheric inputs cannot resolve coastal polynya winds; ERA5 (0.25°) is the recommended upgrade.
* The 2021–2025 test period includes record-low Antarctic sea ice (2023); performance in other regimes may differ.
* Statistical skill ≠ physical validity: the model has no explicit dynamics or thermodynamics. **Independent review by a sea-ice scientist is required before public scientific use.**

## Ethical / communication notes

* Forecast layers are labelled `data_type = model_prediction` and must be visually distinct from observations in the UI.
* Always display issue time, target period, model version and data source with the forecast.