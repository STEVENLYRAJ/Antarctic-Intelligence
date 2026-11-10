# AETHENTRA ML-02 — Feature Engineering (Phase 5)

Code: `src/aethentra/temperature/features/build.py`. One row per (issue date t, grid cell). **Every input window ends at day t**
(unit test `test_features_never_use_future_data` wipes all data after t and checks every feature is unchanged).
Fitted transformations (climatology, σ, damped-persistence coefficients) use training years only. Tree models need no
scaling or imputation: missing predictors stay NaN (LightGBM/XGBoost native handling; Random Forest uses a −999 sentinel).

| Group | Features |
|---|---|
| Temperature history | `t2m_d0` (day t), `t2m_w1` (mean t−6…t), `anom_d0`, `anom_w1`, `anom_w2`, `anom_w3`, `anom_w4` (weekly anomaly means 1–4 weeks back), `anom_m8` (56-day mean), `anom_std_w1`, `anom_std_w4` (rolling std of daily anomalies), `anom_tend` (w1 − w2), `anom_d0_minus_w1`, `t2m_range_w1` (max − min of last 7 days) |
| Spatial context | `nbr_anom_w1` (5 × 5-cell = 125 km masked mean of `anom_w1`), `domain_anom_w1`, `region_anom_w1` (area-weighted means) |
| Seasonal expectation | `clim_target` (climatological T̄ of the target week), `clim_change` (target-week minus last-week climatology = expected seasonal tendency) |
| Calendar | `doy_sin`, `doy_cos` (middle target day), `month` |
| Static | `lat`, `lon_sin`, `lon_cos`, `elevation_m`, `dist_coast_km`, `land`, `coastal`, `region` |
| Atmosphere (interim NCEP: msl, u, v) | `msl_anom_d0`, `msl_anom_w1`, `msl_tend` (w1 − previous week), `u10_w1`, `v10_w1`, `wspd_w1` (mean of daily speed); with ERA5 additionally `d2m_anom_w1`, `tcc_w1`, `z500_anom_w1`, `t850_anom_w1` |
| Sea ice (observations, ML-01 CDR) | `sic_w1` (last-week mean SIC, ocean cells), `sic_change_w4` (w1 minus the week 3 weeks earlier); NaN over land |

Interim configuration: **37 features** (29 temperature/calendar/static, 6 atmosphere, 2 sea ice; exact list in
`data/processed/ml02/tables/train_ncep_r1.json`). Ablation `lgbm_temperature_only` uses the 29 temperature, calendar and static features.

Sampling for the tabular models: 4 % of valid cells per training issue date (1,652 dates → ≈ 3.7 M rows), 15 % per validation issue
date (for early stopping / Optuna only). All full-grid evaluations use **every cell of every issue date**.

Analyses (Phase 5/11 outputs in `experiments/ml02/metrics/analysis/`): Spearman collinearity (|ρ| ≥ 0.9 pairs), correlation with the
target, LightGBM gain, permutation importance (RMSE increase), exact TreeSHAP (mean |SHAP| overall and per season, rank stability
across seasons).
