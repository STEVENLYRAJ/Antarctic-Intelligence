# Feature Engineering — AETHENTRA ML Task 01

All features for issue date *t* are computed from data dated ≤ *t* (enforced in `src/aethentra/features/build.py` and tested by
`test_no_future_information_in_features`, which corrupts every value after *t* and checks that features are unchanged).
Climatologies (SIC and atmosphere) are fitted on the **training years only** (1979–2015) for validation, and on 1979–2020 for the
final refit — never on test years. Tree models need no feature scaling, so no other fitted transformation exists.

## Feature list (40 with atmosphere, 33 SIC-only)

| Group | Feature | Definition |
|---|---|---|
| SIC history | `sic_d0` | latest valid daily SIC ≤ 3 days old (the persistence value) |
| | `sic_age` | age of that value in days (0–3) |
| | `sic_w1`…`sic_w4`, `sic_w8` | mean SIC over week *k* before *t* (days t−7k+1 … t−7k+7), ≥ 3 valid days |
| | `d_w1_w2`, `d_d0_w1` | recent change: week-1 minus week-2; latest day minus week-1 mean |
| | `sic_std28` | standard deviation of daily SIC over the last 28 days |
| | `sic_trend7` | least-squares slope of the last 7 daily values (% / day) |
| | `unc_w1` | mean CDR source standard deviation over the last 7 days (%) |
| Climatology (train-only) | `clim_target`, `clim_target_std` | day-of-year climatology (±7 day smoothing) averaged over the target window |
| | `clim_now`, `clim_change` | climatology of the past week; expected seasonal change (target − now) |
| | `anom_w1`, `anom_persist` | past-week anomaly; anomaly-persistence estimate clip(clim_target + anom_w1) |
| Spatial context | `nbr3_w1`, `nbr7_w1` | ocean-only 3×3 / 7×7 neighbourhood means of week-1 SIC |
| | `grad_w1` | magnitude of the week-1 SIC gradient (% per 25 km) |
| | `dist_edge_km` | signed distance to the week-1 15 % edge (+ inside the ice, − in open water) |
| | `dist_coast_km` | distance to the nearest non-ocean cell |
| | `lat`, `lon_sin`, `lon_cos`, `sector` | location (sector is categorical) |
| Hemispheric state | `sie_w1`, `sie_change` | hemispheric extent of the week-1 field and its weekly change (10⁶ km²) |
| | `sie_sector_w1` | extent of the cell's sector |
| Season | `doy_sin`, `doy_cos`, `month` | day of year / month of the target-window midpoint (Southern-Hemisphere cycle is learned, not assumed) |
| Atmosphere (interim NCEP/NCAR R1) | `air_w1`, `air_anom_w1` | past-7-day mean near-surface air temperature (K) and its anomaly vs. train climatology |
| | `uwnd_w1`, `vwnd_w1`, `wspd_w1` | past-7-day mean eastward / northward wind and speed (m/s); positive v = equatorward (ice-divergent) |
| | `slp_w1`, `slp_anom_w1` | past-7-day mean sea-level pressure (Pa) and its anomaly |

Atmospheric fields (2.5°) are bilinearly interpolated to the SIC cell centres with longitude wrap-around. Only *past* atmospheric
states are used: no forecast of the target week enters the model, so the atmosphere acts as a short-memory forcing signal.

## Training rows
* One row per (issue date, **active** cell). Active = ocean cell where persistence > 0 or the target-window climatology > 0 or the
  7×7 neighbourhood mean > 0 — a rule using **inputs only**. Inactive cells (permanently open water at that time) receive the
  persistence/fallback value (≈ 0) and are still evaluated.
* Training uses a random 4 % of active cells per issue date (seeded), validation tables 15 %; full grids are used for all reported metrics.

## Feature-selection evidence
Collinearity, Spearman correlation with the target residual, gain and permutation importance, TreeSHAP and the seasonal stability of
SHAP ranks are computed in `scripts/analyze.py` and reported in MODEL_EVALUATION_REPORT.md. No feature was removed on test data.
