# ML-04 Implementation Plan

**Mission.** Detect and characterise statistically unusual Antarctic and Southern Ocean conditions:

- univariate, multivariate and compound anomalies;
- with documented baselines;
- using leakage-free chronological evaluation;
- with interpretable outputs.

**Scope decision.** The plan is fitted to the data that exist and can be downloaded without credentials, as verified in the audit:

- NCEP/NCAR R1 daily, 1979-01-01 to 2026-03-17;
- NOAA/NSIDC SIC CDR v6, 1979 to 2026-11-01;
- stations.

ERA5, MERRA-2 and Copernicus Marine need credentials that are not configured. Each can be added as a new data version later; that new version needs a new decision.

## Design

| Topic | Decision | Reason |
|---|---|---|
| Analysis grid | NCEP R1 native 2.5°, 87.5° S–50° S (16 × 144 = 2,304 cells) | Six of the eight variables are native on this grid, so no resampling is needed for them. The domain covers the ice sheet and the sea-ice zone |
| Gaussian fields (prate, tcdc) | Linear interpolation to 2.5° | T62 (~1.9°) is slightly finer, so interpolation mildly smooths it |
| SIC | Area-weighted mean of 25 km ocean pixels per 2.5° cell (≥ 25 % ocean coverage); native 25 km kept for maps | Preserves the native resolution where practical |
| Time | Daily cubes → monthly means (≥ 80 % valid days) | A monthly unit for the ML detectors (about 1.3 M samples); daily products are statistical only |
| Variables | t2m, slp, wind speed, rhum, prate, tcdc, z500, sic, plus month-to-month SIC change | Chosen for physical relevance and available record. Snowfall and snow depth are not available, and precipitation is **not** renamed snowfall |
| Baselines | Fixed. Reporting baseline 1991–2020 (WMO normal) for products and maps. Model baseline 1981–2010 (inside the training period) for every feature, threshold and evaluation | Uses the WMO normal for reporting while keeping validation and test years out of every evaluated baseline |
| Seasonality | Per calendar month (monthly) and per day of year with a ±15-day window (daily); Feb 29 uses Feb 28 | Summer is never compared with winter |
| Splits | Train 1979–2010, validation 2011–2017, test 2018–2025, operational 2026 | The data genuinely cover the candidate periods |
| Statistical methods | z, percentile (Weibull), robust (median/MAD), Mahalanobis (per month, Ledoit–Wolf), seasonal (trailing 3-month), rolling (trailing 30-year) | Interpretable references that stay available permanently |
| ML methods | Isolation Forest, LOF (novelty), One-Class SVM (RBF), MLP autoencoder; two configurations each | Hyperparameters are chosen on validation only |
| Not built | VAE and ConvLSTM / spatiotemporal deep learning | See below |
| Severity | Base-rate classes from the training-period score distribution: P90 / P95 / P98 / P99.5 | Documented statistical criteria rather than arbitrary cut-offs, and comparable across methods |
| Evaluation | Synthetic injections (labelled synthetic) on validation and on test, seed stability, station agreement, flag rates, literature events (qualitative only) | No labelled real anomalies exist |
| Selection | Rank-sum of four validation PR-AUCs among seed-stable candidates; decision frozen; test evaluated once | Same protocol as ML-01…03 |
| Storage | SQLite with the suggested schema, plus PostgreSQL DDL (not applied) | No database is configured |
| Frontend | "Climate anomalies" tab in the existing viewer | No Next.js/Cesium app exists in the repository |

**Why the VAE and spatiotemporal deep learning were not built:**

- Only 384 training months exist as spatial fields. That is too few for a ConvLSTM or ConvAE to learn "normal" variability without memorising it.
- The tabular 9-feature problem gains nothing from a VAE over the autoencoder that can be shown with the labels available.
- The brief says a well-evaluated statistical or Isolation Forest system is preferable.

## Phases and artefacts

| Phase | Code | Main outputs |
|---|---|---|
| 0 Audit | — | `ML04_AUDIT_REPORT.md`, `ML04_DATA_INVENTORY.csv`, this plan |
| 1 Acquisition | `anomaly/acquisition.py`, `scripts/ml04/download_data.py` | `data/raw/ml04/ncep_r1/*.nc` + provenance |
| 2 Preprocessing | `anomaly/preprocessing.py` | `data/interim/ml04/daily_*.npy`, `data/processed/ml04/monthly_*.npy`, `quality_report.json`, extent indices |
| 3 Baselines | `anomaly/climatology.py` | `data/processed/ml04/climatology/*.npz` |
| 4 Features | `anomaly/features.py` | `features/table.parquet`, `z/robust/percentile/physical.npy` |
| 5–6 Detectors | `anomaly/detectors.py`, `anomaly/training.py` | `models/ml04/*.joblib`, `*.meta.json`, `decision.json` |
| 7–9 Severity, compound, spatial/temporal | `anomaly/products.py` | NetCDF cube, clusters, events, co-occurrence, summaries, spells |
| 10 Evaluation | `anomaly/evaluation.py`, `training.py` | `experiments/ml04/metrics/validation.json`, `test.json`, station and event checks |
| 11 Explainability | `products.explain_flagged` | Ablation contributions per flagged cell-month |
| 12 Inference | `anomaly/inference.py`, `anomaly/export.py` | GeoTIFF/JSON products per month, `POST /detect` |
| 13 API | `api/anomaly.py` | `/api/ml04/*` |
| 14 Storage | `anomaly/storage.py`, `configs/ml04/supabase_schema.sql` | `data/processed/ml04/ml04.sqlite` |
| 15 Frontend | `frontend/anomaly.js` | `/viewer/#anom` |
| 16 Automation | `scripts/ml04/run_all.py`, `update_pipeline.py` | Run log in the `processing_runs` table |
| 17 Tests and docs | `tests/test_ml04_anomaly.py` | Test report, model card, data documentation, limitations |
