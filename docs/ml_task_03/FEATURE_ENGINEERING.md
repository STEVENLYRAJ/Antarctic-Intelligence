# ML-03 — Feature Engineering

Implementation: `src/aethentra/sar/features.py`. Only the scene itself (and static geography) is used.

## Pixel features (threshold / Random Forest / XGBoost)

`s0`, `inc`, `s0_norm`, `mean3`, `mean7`, `mean15`, `std7`, `std15`, `grad`, `glcm_contrast`, `glcm_homogeneity`, `glcm_entropy`, `lat`, `lon_sin`, `lon_cos`, `dist_coast_km`, `doy_sin`, `doy_cos`

* `s0` HH σ⁰ (dB); `inc` incidence angle; `s0_norm` = s0 + b·(inc − 35°) with b fitted on TRAINING samples (b = 0.020 dB/°).
* Local mean (3/7/15 px), local std (7/15 px), gradient magnitude of the 3 px mean.
* GLCM contrast / homogeneity / entropy on 16 px blocks, 32 grey levels over −30…0 dB (offsets 1 px, 0° and 90°).
* Geography: latitude, sin/cos longitude, distance to coast (from the land mask); season: sin/cos day of year.

## U-Net channels

`s0_norm`, `inc`, `std7`, `valid` — normalised with training-tile statistics; NaN → 0 with the `valid` channel.
* Tiles: 6387 train / 1427 validation / 2102 test (256 × 256, 400 m).

## Not used

* HV/VV/VH and ratios: not acquired over Antarctic sea ice in EW mode (HH only).
* Temporal features (previous acquisition, historical masks), AMSR2, ERA5, ML-01 outputs: not used in this release (would require per-pixel time matching and risk leaking label information; NEXT_STEPS.md).