# AETHENTRA ML-02 — Next Steps

1. **Run on ERA5** (highest priority): add `%USERPROFILE%\.cdsapirc`, accept the ERA5 licences, run the commands in
   TEMPERATURE_DATA_SOURCES.md. Archive the NCEP results first; ERA5 adds d2m, tcc, z500 and t850 predictors and a 0.25° truth.
   Because the 2018–2025 test period has been used once with NCEP R1, report the ERA5 run as a new experiment on the same protocol
   and keep 2026 as a fresh hold-out.
2. **Target-week atmosphere**: add ECMWF / GFS ensemble-mean forecasts of the target week (requires a reforecast archive for
   training) — the largest missing source of predictability at a 7-day horizon.
3. **Spatial deep learning** (U-Net / ConvLSTM on the 266 × 266 domain box) once PyTorch-CUDA is installed; must beat the tree model
   on the same validation protocol.
4. **Station-based calibration**: use the station archive (Zenodo, GHCN, AWS from AMRC) for bias correction of the absolute
   temperature at point locations; keep a station hold-out.
5. **Probabilistic forecasts**: conformal recalibration of the quantile models on validation, CRPS.
6. **Operationalise**: nightly ERA5T download (5-day latency) → incremental cube update → forecast → layers; monitor input
   coverage and rolling error.
7. **Chained ML-01 × ML-02** experiment (predicted sea ice as a predictor for coastal temperature) — only with a dedicated,
   validated design.
8. **Expert review** of extreme-event cases (e.g. the March 2022 East Antarctic heatwave) before public communication.
