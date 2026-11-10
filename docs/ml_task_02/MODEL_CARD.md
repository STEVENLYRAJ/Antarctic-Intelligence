# Model Card — AETHENTRA ML-02 weekly Antarctic 2 m temperature anomaly

**Truth = NCEP/NCAR Reanalysis 1 (interim substitute for ERA5).** All skill numbers below are agreement with NCEP R1, not with ERA5 and not with direct observations.

| item | value |
|---|---|
| Model version | `aethentra-t2m-weekly-20261108-v1` |
| Type | lightgbm regression (selected `lgbm_tuned`) |
| Output | weekly-mean (t+1…t+7) T2m anomaly on 25 km EPSG:3412 cells south of 60°S; absolute T2m = climatology + anomaly; σ categories |
| Inputs | 37 features: past 8 weeks of reanalysis T2m anomalies, MSL and wind (past week), sea-ice observations, calendar, static geography |
| Training data | ncep_r1 ['1979-01-01', '2017-12-31'] (issue dates every 7 days), climatology ['1981', '2010'] |
| Intended use | research / visualisation of weekly temperature-anomaly outlooks in AETHENTRA; comparison with baselines |
| Not intended for | operational weather forecasting, aviation / field-safety decisions, climate-trend attribution |

## Test performance

* Test 2018-01-07 … 2025-12-21 (416 weekly issue dates, all 55,512 cells each): area-weighted anomaly MAE **2.471 °C**, RMSE **3.719 °C**, bias -0.253 °C, ACC 0.542, R² (absolute T2m) 0.957, R² (anomaly) 0.278.
* MSE skill: vs climatology 0.299, vs persistence 0.547, vs damped persistence 0.150.
  * baseline climatology: MAE 2.999, RMSE 4.441, ACC n/a.
  * baseline persistence: MAE 3.644, RMSE 5.527, ACC 0.476.
  * baseline persistence_week: MAE 3.162, RMSE 4.775, ACC 0.416.
  * baseline recent_trend: MAE 3.955, RMSE 5.949, ACC 0.367.
  * baseline damped_persistence: MAE 2.702, RMSE 4.033, ACC 0.418.

## Ethical / scientific considerations

* Trained and verified on reanalysis; station agreement is reported separately and is only partially independent.
* The model is a conditional-mean forecast: it underestimates the amplitude of extreme anomalies (see the interpretability report).
* Interim truth (NCEP R1) has known plateau biases; ERA5 retraining is the next step.

## Limitations

* Statistical forecast of the 7-day MEAN 2 m temperature anomaly learnt from reanalysis; it is NOT a numerical weather forecast and uses no forecast of the target-week atmosphere.
* Truth for training and evaluation is a reanalysis (gridded model-data blend), not direct observation; reanalysis 2 m temperature over the Antarctic plateau has known biases (strong surface inversions).
* 25 km cells: station-scale and steep-topography effects (Peninsula, Transantarctic Mountains) are smoothed.
* Anomaly categories use training-period (1981-2010) sigma per cell and season; under a warming trend the 'warm' class becomes more frequent.
* Not reviewed by an independent Antarctic meteorology expert; not for operational or safety-critical use.