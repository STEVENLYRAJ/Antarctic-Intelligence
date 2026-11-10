# Initial Implementation Plan (Phase 0)

Status keys: PLANNED → IMPLEMENTED → EXECUTED → VALIDATED. Final status of every step is reported in `AETHENTRA_ML_TASK_01_FINAL_REPORT.md`.

1. **Acquisition** — G02202 v6 SH daily aggregates 1979–2026 (MD5-verified, resumable); NCEP R1 daily air/uwnd/vwnd/slp south of 35°S via OPeNDAP. `scripts/download_data.py`.
2. **Preprocessing** — build a memory-mapped daily SIC cube (uint8 %, 255 = missing) on the native EPSG:3412 25 km grid, a static ocean mask from `surface_type_mask`, exact cell areas from the projection scale factor, a daily calendar with explicit gaps; QA statistics per day. `scripts/preprocess.py`, `scripts/validate_data.py`.
3. **Labels** — weekly issue dates t (7-day cadence); target = mean daily SIC over t+1…t+7 per ocean cell (valid if ≥5 of 7 days observed).
4. **Features** — SIC lags (day t, weeks 1–4, 8), change, 28-day std, 7-day trend, train-only climatology and anomaly, neighbourhood means, gradient, signed distance to ice edge, distance to coast, seasonal sin/cos, sector, hemispheric/sector extent, CDR uncertainty, NCEP past-week atmosphere (+ anomalies).
5. **Splits** — issue years train 1979–2015, validation 2016–2020, test 2021–2025, after verifying coverage; target windows may not cross split boundaries; climatology fitted on training years only (train+val for the final refit).
6. **Baselines** — persistence (latest valid day), past-week persistence, train climatology, anomaly persistence, damped 7-day trend.
7. **Models** — LightGBM, XGBoost (GPU), Random Forest (subsample) on a cell×issue-date table; target = residual over persistence; ablation without atmosphere.
8. **Evaluation** — MAE/RMSE/bias/R² (unweighted and area-weighted), extent & area errors, IIEE, IoU/F1/precision/recall of the 15 % edge, per sector/season/condition/ice-edge band; uncertainty via quantile models only if coverage verifies.
9. **Tuning & final model** — Optuna on validation only; refit on 1979–2020; single evaluation on 2021–2025.
10. **Interpretability** — TreeSHAP (native), permutation importance, residual/plausibility checks.
11. **Inference** — `src/aethentra/inference/` → NetCDF grid + JSON summary; live forecast from the latest CDR day.
12. **Integration** — FastAPI service `api/`, frontend layers (GeoJSON edges, GeoTIFF, JSON time series).
13. **Tests & docs** — pytest suite (synthetic fixtures labelled), reports listed in Phase 16.
