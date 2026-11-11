# ML-03 — Implementation Plan (decided after the Phase 0 audit)

## Data and labels

* **Imagery:** Sentinel-1 A/B EW GRDM HH (40 m pixels, 6×2 looks) from Planetary Computer. Each scene is read at the ×8 COG overview
  (≈ 320 m), calibrated to σ⁰ with the product's own calibration LUT, thermal-noise corrected (range × azimuth noise vectors),
  incidence angle derived from the LUTs (sin θ = A_β² / A_σ²), then geocoded with the product GCPs to EPSG:3031 at 400 m.
* **Labels:** USNIC Antarctic charts (SIGRID-3). Scenes are paired with the chart whose valid date is 0–3 days after acquisition.
  Classes: 0 open water (CT 00/01/02), 1 sea ice (CT lower bound ≥ 70 %), 2 uncertain/mixed (10–70 %, and a buffer around every
  class boundary for chart-scale/time-mismatch), 255 land/ice shelf/no SAR/no chart polygon.
* **Comparison only (never truth):** DMI-ASIP 1 km SIC (one local day), AMSR2 ASI 3.125 km SIC.

## Splits (by chart date → by scene, before tiling)

train 2018–2022 · validation 2023–2024 · test 2025-01-01 → latest chart (2026). One scene belongs to exactly one chart date and
therefore one split; tiles inherit the scene's split.

## Models (in order; each must beat the previous to justify complexity)

1. Threshold on incidence-angle-normalised HH σ⁰ (threshold and slope fitted on train).
2. Random Forest and XGBoost on per-pixel SAR texture + geography features (pixel sample from train scenes).
3. U-Net (BCE + Dice, uncertain/invalid pixels masked), early stopping on validation.
4. Further architectures only if the U-Net clearly beats the tree baselines and time allows.

Selection on validation only → final refit on train+validation (fixed epochs) → one test evaluation.

## Products

Scene-level probability / class GeoTIFFs and NetCDF + JSON metadata; weekly composites on a 2 km EPSG:3031 grid with valid-acquisition
count, ice-detection count, detection frequency and coverage. FastAPI router `/seaice-detection`; layers in the existing viewer.

## Layout (separate subpackage; ML-01/ML-02 untouched)

`src/aethentra/sar/` · `configs/ml03/` · `scripts/ml03/` · `data/raw/sentinel1/`, `data/raw/ice_charts/` · `data/interim/ml03/`,
`data/processed/ml03/` · `models/ml03/` · `experiments/ml03/` · `outputs/ml03/` · `docs/ml_task_03/`
