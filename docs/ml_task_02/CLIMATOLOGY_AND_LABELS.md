# AETHENTRA ML-02 — Climatology and Labels (Phase 4)

Code: `src/aethentra/temperature/climatology/climatology.py`, `src/aethentra/temperature/labels/labels.py` · configs
`configs/ml02/climatology.yaml`, `configs/ml02/features.yaml` · artefacts `models/ml02/artifacts/` (copied into `models/ml02/final/`).

## Reference climatology
* **Period 1981–2010** (30 years, a WMO standard normal) — entirely inside the training split (1979–2010), so it is fixed
  before any validation (2011–2017) or test (2018–2025) data are seen. The current WMO normal 1991–2020 was rejected because
  it overlaps validation and test (leakage).
* Per cell and day of year: mean of all reference-period daily values (365 slots; 29 Feb shares the 28 Feb slot), then a
  circular **±15-day moving average** (31-day window; 31 Dec is adjacent to 1 Jan) to remove sampling noise and calendar
  discontinuities. Fitted for every cube variable (T2m, and MSL / winds / … for predictor anomalies).
* The same climatology is used for training, validation, test and inference (one consistent anomaly definition).

## Labels (issue date t; inputs ≤ t, 23:59 UTC)
| Label | Definition |
|---|---|
| A — weekly T2m | T̄ = mean of the daily-mean T2m on days t+1 … t+7 (°C). All 7 days required (reanalysis has no gaps). |
| B — weekly anomaly | A = T̄ − C̄, where C̄ = mean of the 7 daily climatological values of the same target days (consistent across the window). |
| Categories | z = A / σ(cell, season of the middle target day); bins z < −2 strong cold, −2 ≤ z < −1 cold, −1 ≤ z < 1 near normal, 1 ≤ z < 2 warm, z ≥ 2 strong warm. |
| Indicators | warm (z ≥ 1), cold (z ≤ −1), extreme warm (z ≥ 2), extreme cold (z < −2). |

σ is the standard deviation of label B over all **training** issue dates in 1981–2010 (per cell, per DJF/MAM/JJA/SON; suspect
dates excluded). Models predict label B; label A is reconstructed exactly as C̄ + predicted anomaly, so the absolute and anomaly
errors are identical cell by cell (R² and correlations differ).

## Limitations
* σ varies strongly in space (small over the Southern Ocean in summer, large over the plateau in winter); identical z-thresholds
  therefore correspond to very different °C amplitudes — categories are relative, not absolute.
* With a warming trend after 2010 the "warm" classes become more frequent than the nominal ~16 % in validation/test; this is
  real signal relative to a fixed baseline, not a calibration error.
* Seasonal σ uses the season of the target week; weeks straddling season boundaries inherit the season of their middle day.
* Interim source: the climatology is NCEP R1's own climatology — anomalies are internally consistent but not comparable to
  ERA5-based anomalies.
