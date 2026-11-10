# AETHENTRA ML-02 — Model Interpretability & Scientific Validation

**Truth = NCEP/NCAR Reanalysis 1 (interim substitute for ERA5).** All skill numbers below are agreement with NCEP R1, not with ERA5 and not with direct observations.

## Validation-stage feature analysis (candidate LightGBM)

Top-12 mean |SHAP| (°C): anom_d0 0.974, msl_anom_d0 0.507, anom_m8 0.283, nbr_anom_w1 0.211, msl_anom_w1 0.146, anom_d0_minus_w1 0.137, domain_anom_w1 0.107, region_anom_w1 0.094, sic_change_w4 0.074, anom_w2 0.073, sic_w1 0.070, doy_cos 0.064.

Top-10 permutation importance (validation RMSE increase, °C): anom_d0 0.593, msl_anom_d0 0.146, anom_m8 0.052, nbr_anom_w1 0.035, msl_anom_w1 0.031, anom_d0_minus_w1 0.019, domain_anom_w1 0.013, sic_change_w4 0.012, clim_target 0.011, lat 0.008.

Collinear pairs (|Spearman| ≥ 0.9): anom_w1/nbr_anom_w1 +1.00, anom_std_w1/t2m_range_w1 +0.99, land/region +0.98, t2m_w1/clim_target +0.97, t2m_d0/t2m_w1 +0.97, elevation_m/region +0.96, elevation_m/land +0.95, t2m_d0/clim_target +0.94.

Top-10 SHAP features per season: **DJF** anom_d0, msl_anom_d0, anom_m8, nbr_anom_w1, msl_anom_w1, region_anom_w1, clim_target, domain_anom_w1, sic_w1, anom_w2; **MAM** anom_d0, msl_anom_d0, anom_m8, nbr_anom_w1, msl_anom_w1, anom_d0_minus_w1, sic_change_w4, domain_anom_w1, sic_w1, region_anom_w1; **JJA** anom_d0, msl_anom_d0, anom_m8, nbr_anom_w1, anom_d0_minus_w1, msl_anom_w1, domain_anom_w1, region_anom_w1, sic_change_w4, doy_cos; **SON** anom_d0, msl_anom_d0, anom_m8, nbr_anom_w1, anom_d0_minus_w1, msl_anom_w1, domain_anom_w1, region_anom_w1, doy_sin, anom_w2.

## Final model on the test period (post-selection; nothing was tuned on it)

* Rows analysed: 150,000. Prediction range -13.9 … 15.0 °C vs observed -31.2 … 31.1 °C; std(pred)/std(obs) = 0.51 (regression to the mean expected for a conditional-mean forecast).
* Top-10 permutation importance (test RMSE increase, °C): anom_d0 0.431, msl_anom_d0 0.134, nbr_anom_w1 0.069, anom_m8 0.056, anom_d0_minus_w1 0.046, msl_anom_w1 0.019, clim_target 0.013, anom_w2 0.011, anom_w1 0.009, sic_w1 0.008.
* Top-10 mean |SHAP| (test): anom_d0 0.814, msl_anom_d0 0.485, anom_m8 0.312, nbr_anom_w1 0.290, anom_d0_minus_w1 0.270, msl_anom_w1 0.169, anom_w2 0.125, domain_anom_w1 0.118, clim_target 0.094, region_anom_w1 0.093.

### Sensitivity to missing predictors (set to NaN at inference)

| group | RMSE full | RMSE missing |
|---|---|---|
| atmosphere (6) | 3.678 | 3.731 |
| sea_ice (2) | 3.678 | 3.692 |
| lags_beyond_week1 (6) | 3.678 | 3.753 |

### Residuals by observed anomaly class (extremes)

| observed z | bias °C | RMSE °C | n |
|---|---|---|---|
| <-2s | +6.533 | 8.236 | 3,255 |
| -2..-1s | +3.888 | 5.184 | 13,809 |
| -1..1s | +0.060 | 2.398 | 106,294 |
| 1..2s | -3.714 | 4.791 | 21,595 |
| >2s | -6.939 | 8.089 | 5,047 |

### Residuals by elevation and season

| stratum | bias °C | RMSE °C |
|---|---|---|
| elevation (-1, 1] m (n=92,568) | -0.083 | 3.487 |
| elevation (1, 500] m (n=6,907) | -0.421 | 4.763 |
| elevation (500, 1500] m (n=14,196) | -0.368 | 3.682 |
| elevation (1500, 2500] m (n=12,669) | -0.369 | 3.637 |
| elevation (2500, 5000] m (n=23,660) | -0.566 | 4.042 |
| season DJF | -0.006 | 1.592 |
| season JJA | -0.129 | 5.093 |
| season MAM | -0.379 | 3.592 |
| season SON | -0.384 | 3.515 |

### Partial dependence (mean prediction, °C) of the top features

* `anom_d0`: x -13.32 → 15.25 gives -1.91 → +3.80 °C (monotonic increasing: True).
* `msl_anom_d0`: x -25.30 → 21.64 gives -0.34 → +1.86 °C (monotonic increasing: True).
* `anom_m8`: x -4.53 → 6.56 gives -0.15 → +1.27 °C (monotonic increasing: True).
* `nbr_anom_w1`: x -9.09 → 11.20 gives -0.46 → +1.43 °C (monotonic increasing: True).

### Spatial discontinuity check

Mean absolute neighbour difference of weekly anomaly fields: reanalysis 0.158 °C, final model 0.106 °C, persistence 0.250 °C (ratio model/reanalysis 0.67; < 1 means the forecast is smoother than the truth, > 1 would indicate artificial cell-to-cell noise).

## Independent station comparison (test period)

Station anomalies vs each station's own 1981-2010 climatology; nearest 25 km cell (land preferred). Reanalysis assimilates many of these stations -> partially independent.

| station | source | dist km | cell elev m | weeks | reanalysis RMSE | model RMSE | persistence RMSE | model corr | model abs-T bias °C |
|---|---|---|---|---|---|---|---|---|---|
| DINAMET-URUGUAY | NOAA | 24.4 | 74 | 94 | 1.06 | 1.63 | 2.42 | 0.62 | -0.7 |
| BELLINGSHAUSEN AWS | NOAA | 25.5 | 74 | 380 | 0.98 | 1.69 | 2.61 | 0.45 | -0.5 |
| CENTRO MET. ANTARTICO PDTE. E | NOAA | 29.2 | 74 | 408 | 1.11 | 1.75 | 2.76 | 0.40 | -0.1 |
| GREAT WALL | NOAA | 31.2 | 74 | 243 | 1.10 | 1.79 | 2.87 | 0.41 | -0.6 |
| BASE ARTURO PRAT | NOAA | 9.1 | 0 | 395 | 1.12 | 1.81 | 3.11 | 0.37 | -1.5 |
| PALMER STATION | NOAA | 25.3 | 182 | 386 | 1.52 | 1.81 | 3.77 | 0.49 | -3.7 |
| VERNADSKY | Zenodo | 15.3 | 200 | 208 | 1.90 | 1.90 | 4.24 | 0.45 | -3.6 |
| BASE JUBANY | NOAA | 25.0 | 74 | 408 | 1.16 | 2.03 | 2.86 | 0.42 | -0.9 |
| BASE BERNARDO O'HIGGINS | NOAA | 21.4 | 108 | 371 | 2.11 | 2.35 | 5.18 | 0.34 | -2.2 |
| MAWSON | Zenodo | 7.9 | 764 | 255 | 1.56 | 2.54 | 4.32 | 0.49 | -8.4 |
| MOLODEZNAJA | NOAA | 19.0 | 546 | 285 | 1.61 | 2.64 | 4.74 | 0.36 | -3.3 |
| ROTHERA | Zenodo | 6.2 | 346 | 223 | 2.61 | 2.65 | 6.14 | 0.40 | -5.5 |
| BASE ORCADAS | NOAA | 13.9 | 0 | 398 | 1.51 | 2.66 | 4.78 | 0.57 | -1.0 |
| DAVIS | Zenodo | 28.0 | 756 | 215 | 1.19 | 2.67 | 4.06 | 0.52 | -6.4 |
| DUMONT D'URVILLE | Zenodo | 8.5 | 675 | 233 | 1.69 | 2.69 | 4.15 | 0.46 | -6.7 |
| SYOWA | Zenodo | 24.1 | 629 | 254 | 1.43 | 2.69 | 4.37 | 0.36 | -4.1 |
| MANUELA | NOAA | 11.2 | 926 | 74 | 2.00 | 2.85 | 4.36 | 0.42 | -6.6 |
| NOVOLAZAREVSKAJA | Zenodo | 7.9 | 971 | 253 | 1.67 | 2.85 | 3.70 | 0.36 | -6.6 |
| ZHONGSHAN | NOAA | 21.1 | 814 | 322 | 1.42 | 2.92 | 4.27 | 0.52 | -6.8 |
| MIRNYJ | NOAA | 9.0 | 670 | 362 | 1.26 | 2.95 | 4.64 | 0.42 | -3.0 |
| CASEY | Zenodo | 24.2 | 431 | 220 | 1.38 | 3.00 | 3.75 | 0.42 | -3.3 |
| BASE SAN MARTIN | NOAA | 5.8 | 466 | 407 | 2.68 | 3.01 | 6.76 | 0.46 | -8.0 |
| MCMURDO SOUND NAF | Zenodo | 16.0 | 195 | 248 | 1.62 | 3.27 | 4.15 | 0.46 | -3.0 |
| MARBLE POINT | NOAA | 3.2 | 673 | 394 | 1.90 | 3.43 | 4.06 | 0.45 | -7.1 |
| BASE BELGRANO II | NOAA | 12.2 | 106 | 409 | 4.02 | 3.46 | 7.76 | 0.44 | -5.5 |
| UNIV. WI ID 8902 (BUTLER ISLA | NOAA | 4.6 | 599 | 330 | 3.42 | 3.55 | 5.75 | 0.31 | -1.5 |
| BASE ESPERANZA | Zenodo | 10.7 | 136 | 253 | 2.53 | 3.67 | 5.69 | 0.29 | -1.6 |
| VOSTOK | Zenodo | 11.5 | 3356 | 222 | 2.57 | 3.67 | 6.23 | 0.44 | +4.2 |
| UNIV. WI ID 8926 (LARSEN ICE | NOAA | 8.3 | 205 | 209 | 3.62 | 4.20 | 5.94 | 0.40 | +2.8 |
| AMUNDSEN-SCOTT | Zenodo | 18.1 | 2590 | 220 | 2.82 | 4.22 | 5.31 | 0.36 | +6.8 |
| NEUMAYER | Zenodo | 10.1 | 184 | 254 | 2.94 | 4.23 | 5.62 | 0.36 | +2.1 |
| BASE MARAMBIO | Zenodo | 43.9 | 152 | 253 | 3.34 | 4.48 | 6.76 | 0.24 | +1.1 |
| DOME C II | NOAA | 9.7 | 3085 | 399 | 4.56 | 4.61 | 7.82 | 0.22 | +0.3 |
| FERRELL | NOAA | 11.6 | 0 | 73 | 2.49 | 4.66 | 5.07 | 0.43 | +5.0 |
| BYRD STATION | NOAA | 9.8 | 1447 | 81 | 2.75 | 4.72 | 5.82 | 0.49 | +1.8 |
| CONCORDIA | Zenodo | 9.7 | 3085 | 215 | 4.46 | 4.75 | 7.96 | 0.20 | +0.6 |
| MARILYN | NOAA | 10.7 | 492 | 50 | 2.37 | 4.87 | 4.54 | 0.58 | +2.0 |
| HALLEY | Zenodo | 15.4 | 415 | 223 | 3.08 | 4.97 | 5.94 | 0.43 | +2.2 |
| SCHWERDTFEGER | NOAA | 8.2 | 37 | 90 | 3.18 | 5.20 | 5.71 | 0.44 | +7.0 |
| LETTAU | NOAA | 10.3 | 3 | 77 | 3.68 | 5.89 | 6.60 | 0.51 | +5.8 |

Reanalysis agreement (model vs gridded truth) and station agreement measure different things: the first is skill against the training distribution, the second includes representativeness error (point vs 25 km cell, elevation mismatch) and reanalysis error.