# ML-04 Test Report

**Run:** 2026-11-12 (after the v2 rebuild), `python -m pytest tests/`.

**Full suite: 92 passed, 1 failed.**

- The failure is the pre-existing ML-01 Stage-1 test `test_antarctic_preprocessing.py::test_inventory_covers_all_raw_files`. It flags user files in `DATAS/` that are not in the Stage-1 inventory, and it is unrelated to ML-04.
- **ML-04 (`tests/test_ml04_anomaly.py`): 17 of 17 passed.**

`tests/test_content_check.py`: **6 of 6 passed**. It rejects all-zero, all-NaN, constant, flat-day and out-of-range fields, and accepts NaN-padded current-year files.

Unit tests use SYNTHETIC arrays, labelled as such in the code. They test the software only.

| Area | Test | What it verifies |
|---|---|---|
| Anomaly calculation | `test_percentile_rank_weibull` | Weibull percentile rank, below-record value, NaN handling |
| Baselines and leap days | `test_noleap_doy_feb29_shares_feb28_and_no_shift_in_common_years` | Feb 29 shares the Feb 28 climatology; day-of-year alignment |
| Temporal splits and leakage | `test_baselines_and_splits_are_leakage_free` | Splits are chronological and non-overlapping; the model baseline lies inside the training years |
| Severity | `test_severity_classes_follow_training_base_rates` | Class base rates are 90/5/3/1.5/0.5 % |
| Statistical detectors | `test_statistical_scores_pick_the_extreme_variable`, `test_model_matrix_imputes_sic_and_clips` | max \|z\|, MAD and percentile scores; imputation and clipping |
| Multivariate statistics | `test_mahalanobis_detects_covariance_break_that_zscore_misses` | A covariance break is detected by Mahalanobis and missed by univariate z |
| Synthetic recovery | `test_ml_detectors_recover_synthetic_injections` (IF, LOF, OCSVM) | Average precision > 0.5 on injected shifts |
| Reproducibility | `test_isolation_forest_is_reproducible_with_fixed_seed` | Identical scores (tolerance 1e-12) with the same seed and data |
| Autoencoder | `test_autoencoder_trains_and_scores_injection_higher` | Trains, scores the injection higher, and pickles losslessly (tolerance 1e-5) |
| Missing data and coordinates | `test_feature_table_alignment_and_coordinates` | Full grid every month; latitude/longitude ranges; z centred in the baseline; no atmospheric samples after March 2026 |
| Data quality | `test_quality_report_ranges` | Every variable passes its plausibility range; NCEP last date is 2026-03-17 |
| Single-test rule | `test_decision_frozen_and_single_test` | The test ran after the frozen decision; the selected method is multivariate |
| Spatial output | `test_display_resampling_and_regions` | EPSG:3412 display grid shape; every cell has a region |
| API | `test_api_endpoints` | Health; 422 on a malformed month; spatial grid of 16 × 144; `/detect` happy path; 422 on an out-of-range temperature |

**Finding recorded during testing.** A spike in a single variable among 9 dimensions is poorly isolated by Isolation Forest (AP 0.08 against 1.0 for LOF and OCSVM). This is consistent with its low synthetic-recovery score in validation. The unit test now uses a 3-variable shift, and the weakness is documented in the model card.

**Reproducibility.** All stages are deterministic given the raw files:

- fixed seeds: 42 for fitting, 2011 for validation injections, 2018 for test injections;
- frozen decision file;
- MD5-verified raw inputs.

Re-running `scripts/ml04/run_all.py --from score` reproduces the products from the saved detectors.
