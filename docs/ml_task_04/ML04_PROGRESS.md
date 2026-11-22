# ML04_PROGRESS

Status as of 2026-11-12. **v1 invalidated** (three all-zero NCEP raw files); everything below refers to **v2**.

**Status meanings:**

- COMPLETED: code written and executed successfully.
- VALIDATED: also checked by tests or independent checks.
- BLOCKED: waiting on something outside this project.

| Phase | Status | Evidence | Open items |
|---|---|---|---|
| 0 Audit | VALIDATED | `ML04_AUDIT_REPORT.md`, `ML04_DATA_INVENTORY.csv`, `ML04_IMPLEMENTATION_PLAN.md` (checked on disk and against the live source) | — |
| 1 Acquisition | VALIDATED | 192/192 NCEP R1 files (rhum, prate, tcdc, z500 for 1979–2026), provenance and MD5; 3 corrupt files re-downloaded 2026-11-12 and all 432 NCEP files pass the new content check (`scripts/check_raw_content.py`); air/slp/uwnd/vwnd and SIC CDR reused | **ERA5 BLOCKED** (needs CDS token); MERRA-2 and Copernicus Marine BLOCKED (need accounts) |
| 2 Preprocessing | VALIDATED | 8 daily cubes + monthly means + native 25 km SIC monthly + extent indices; `quality_report.json` all `range_ok`; 3 source issues found and handled | — |
| 3 Baselines | VALIDATED | Fixed 1991–2020 (reporting) and 1981–2010 (model); monthly and daily (±15 d) statistics; leakage test passes | — |
| 4 Features | VALIDATED | 1,324,800 cell-months × 9 features; alignment test passes | — |
| 5 Statistical baselines | VALIDATED | z, percentile, MAD, Mahalanobis, seasonal, rolling; evaluated on validation and test | Percentile detector unsuitable for flagging (flags 43 % in test) |
| 6 ML models | VALIDATED | IF, LOF, OCSVM, autoencoder (2 configurations each), seed stability; LOF k=20 selected (v2 decision frozen 2026-11-11 03:41 UTC) | VAE and ConvLSTM not built (justified in the plan) |
| 7 Severity | VALIDATED | Base-rate classes from training scores; base-rate unit test | — |
| 8 Compound events | COMPLETED | Co-occurrence rule for 5 physical pairs (31,488 cell-months); DBSCAN clusters → 1,926 linked events (772 lasting ≥ 2 months) | No physical-mechanism attribution (by design) |
| 9 Temporal and spatial | COMPLETED | Monthly/seasonal summaries, daily extent anomalies, daily warm/cold spells, regions, persistent clusters | — |
| 10 Evaluation | VALIDATED | Synthetic recovery on validation (frozen) and test (once), stations, literature events, flag rates | No labelled real anomalies exist |
| 11 Explainability | COMPLETED | Ablation contributions and top-3 variables for every flagged cell-month; per-variable z, percentile and tier in `/detect` | SHAP not used (`shap` not installed; the ablation method is model-agnostic) |
| 12 Inference | VALIDATED | NetCDF cube, GeoTIFF layers for 2026-02 (multivariate) and 2026-10 (SIC only), JSON/CSV, `POST /detect` (API test) | — |
| 13 FastAPI | VALIDATED | 14 endpoints under `/api/ml04`; API tests pass | Local only; not a production deployment |
| 14 Storage | COMPLETED | SQLite: models, datasets, 294,205 anomaly records, processing runs; PostgreSQL/Supabase DDL written | Supabase not configured; DDL not applied |
| 15 Frontend | COMPLETED | "Climate anomalies" tab in `/viewer/#anom` | Next.js/CesiumJS dashboard not present in the repository |
| 16 Automation | COMPLETED | `run_all.py` (resumable, run log), `update_pipeline.py` (`--check` / `--backfill`) | No scheduler registered (needs your decision); NCEP R1 source no longer updates |
| 17 Tests and docs | VALIDATED | 17/17 ML-04 tests + 6 content-check tests (full suite 92 passed, 1 pre-existing Stage-1 failure); test report, model card, data documentation, limitations | — |
