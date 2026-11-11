# AETHENTRA ML Task 03 — Final Report
## Antarctic Sea-Ice Detection from Sentinel-1 SAR

Status legend: COMPLETED = executed on real data and checked; IMPLEMENTED = code + tests only; PENDING = blocked; NOT DONE = gap.

## 1. Objective

Pixel-level sea-ice vs open-water segmentation of Antarctic Sentinel-1 EW HH scenes, with uncertain and invalid pixels handled separately, plus weekly detection-frequency composites. This is detection from observations, not forecasting.

## 2. Phase status

| phase | status | evidence |
|---|---|---|
| 0 Audit | COMPLETED | PROJECT_AUDIT.md, DATA_INVENTORY.csv, MISSING_PREREQUISITES.md, ML03_IMPLEMENTATION_PLAN.md |
| 1 Acquisition | COMPLETED (anonymous sources; CDSE/CMEMS pending credentials) | 774 scenes, 387 charts; SATELLITE_DATA_SOURCES.md |
| 2 Labels | COMPLETED (chart-derived); expert review NOT DONE | LABEL_GENERATION_REPORT.md, ANNOTATION_GUIDELINES.md |
| 3 Preprocessing | COMPLETED | SAR_PREPROCESSING_REPORT.md |
| 4 Features | COMPLETED | FEATURE_ENGINEERING.md |
| 5 Baselines | COMPLETED | threshold, RF, XGBoost |
| 6 Deep learning | COMPLETED (U-Net ×2 losses); DeepLabV3+/Attention U-Net/SegFormer NOT DONE (not justified yet) | MODEL_TRAINING_REPORT.md |
| 7 Splits | COMPLETED | train 2018–2022, validation 2023–2024, test 2025–2026, by scene/chart date |
| 8 Evaluation | COMPLETED | MODEL_EVALUATION_REPORT.md |
| 9 Selection / final / single test | COMPLETED | selection frozen 2026-11-09T17:21:01.946458+00:00; test 2026-11-09T18:18:30.738110+00:00 |
| 10 Error analysis | COMPLETED | MODEL_INTERPRETABILITY_AND_ERROR_REPORT.md |
| 11 Weekly compositing | COMPLETED | WEEKLY_COMPOSITING_METHODOLOGY.md, week_2026-11-02 |
| 12 Inference | COMPLETED | MODEL_OUTPUT_SCHEMA.md |
| 13 FastAPI | COMPLETED locally (TestClient) — not a production deployment | api/seaice_detection.py (`/seaice-detection`) |
| 14 Frontend layers | COMPLETED as GeoTIFF files; no CesiumJS frontend in the repository | outputs/ml03 |
| 15 Tests | 69 passed, 1 failed, 0 skipped (whole repository, 2026-11-10T17:58:40+00:00) | tests/test_ml03_sar.py |

## 3. Baselines and candidates (validation)

| model | mIoU | IoU ice | IoU water | F1 ice | prec. ice | recall ice | OA | bal. acc. | boundary F1 | edge disp. km | ice-area bias % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| threshold | 0.480 | 0.625 | 0.335 | 0.769 | 0.707 | 0.843 | 0.685 | 0.633 | 0.039 | 98.740 | 17.7 |
| rf | 0.877 | 0.908 | 0.845 | 0.952 | 0.932 | 0.973 | 0.939 | 0.928 | 0.056 | 93.580 | 4.2 |
| xgb | 0.867 | 0.902 | 0.832 | 0.948 | 0.925 | 0.973 | 0.934 | 0.921 | 0.066 | 82.052 | 5.0 |
| unet_bce | 0.834 | 0.861 | 0.807 | 0.925 | 0.984 | 0.873 | 0.912 | 0.925 | 0.041 | 95.462 | -11.0 |
| unet_bce_dice | 0.886 | 0.910 | 0.861 | 0.953 | 0.967 | 0.939 | 0.942 | 0.943 | 0.042 | 89.029 | -2.8 |

Selected `unet_bce_dice` on validation only (rank-sum on validation full scenes: mIoU, ice F1, boundary F1, |ice-area bias| (ties -> simpler)).

## 4. Final test metrics (single evaluation; agreement with USNIC charts)

| model | mIoU | IoU ice | IoU water | F1 ice | prec. ice | recall ice | OA | bal. acc. | boundary F1 | edge disp. km | ice-area bias % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| threshold | 0.487 | 0.556 | 0.417 | 0.715 | 0.624 | 0.836 | 0.663 | 0.661 | 0.044 | 90.678 | 32.2 |
| rf | 0.890 | 0.894 | 0.887 | 0.944 | 0.926 | 0.963 | 0.942 | 0.942 | 0.057 | 66.097 | 3.9 |
| xgb | 0.896 | 0.898 | 0.893 | 0.946 | 0.932 | 0.961 | 0.945 | 0.945 | 0.058 | 60.760 | 3.1 |
| unet_bce | 0.839 | 0.831 | 0.848 | 0.908 | 0.980 | 0.845 | 0.913 | 0.914 | 0.033 | 78.252 | -13.7 |
| unet_bce_dice | 0.885 | 0.884 | 0.886 | 0.938 | 0.957 | 0.920 | 0.939 | 0.939 | 0.058 | 58.833 | -3.9 |
| final_model | 0.867 | 0.863 | 0.871 | 0.926 | 0.970 | 0.886 | 0.929 | 0.929 | 0.022 | 96.682 | -8.6 |

**On test, the selected model is not the best:** `xgb` reaches mIoU 0.896 vs 0.867 for `final_model` (refit of `unet_bce_dice`). The selection was frozen on validation and is not changed after seeing the test; the tree models are equally viable operational candidates and the refit lost skill relative to its train-only version (see MODEL_EVALUATION_REPORT.md, seasonal table).

## 5. Documents

SATELLITE_DATA_SOURCES · DATA_INVENTORY · SAR_PREPROCESSING_REPORT · LABEL_GENERATION_REPORT · ANNOTATION_GUIDELINES · FEATURE_ENGINEERING · MODEL_TRAINING_REPORT · MODEL_EVALUATION_REPORT · MODEL_INTERPRETABILITY_AND_ERROR_REPORT · WEEKLY_COMPOSITING_METHODOLOGY · MODEL_CARD · MODEL_OUTPUT_SCHEMA · REPRODUCIBILITY_GUIDE · NEXT_STEPS

## 6. Limitations

* Labels are expert charts at chart scale, 0–3 days from the image: metrics are chart agreement, not pixel truth.
* 400 m resolution (×8 overview) and HH only; no expert-confirmed pixels; DMI-ASIP comparison covers one day.
* Weekly composites cover only the acquisitions of that week; unobserved cells stay empty.
* Local API only; no production deployment.