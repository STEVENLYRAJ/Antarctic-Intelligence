# ML-04 v1 — INVALIDATED (kept for the record)

v1 (decision frozen 2026-11-10T23:03Z, single test 2026-11-10) was built on three corrupt NCEP R1 raw files
(rhum 2001, rhum 2002, tcdc 2001: every value 0; they passed the day-count check of the downloader). The defect
contaminated both baselines (1981-2010, 1991-2020) and therefore every humidity/cloud z-score, the multivariate
features, all fitted detectors, the validation decision and the test result.

Found by the Phase 1 read-only audit (docs/phase1/PHASE1_FINAL_AUDIT.md, item A1). Fixed 2026-11-12: corrupt files
moved to data/raw/ml04/quarantine_corrupt_20261112/, re-downloaded through the new content check
(aethentra.data.acquisition.content_check), ML-04 rebuilt from preprocessing as v2 with a new frozen decision and a
new single test. Re-testing is justified by a data defect, not by a model choice made after seeing test results.
v1 numbers must not be cited.
