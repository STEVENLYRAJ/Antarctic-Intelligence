# Phase 1 Progress Tracker

Last updated: 2026-11-12 (P0 fixes approved and executed).

**Status meanings:**

- COMPLETED AND VERIFIED
- IMPLEMENTED BUT NOT VERIFIED
- IN PROGRESS
- BLOCKED
- DEFERRED

## Audit (this execution)

| Item | Status | Evidence |
|---|---|---|
| Read-only repository audit | COMPLETED AND VERIFIED | `PHASE1_FINAL_AUDIT.md` |
| Storage inventory and cleanup proposal | COMPLETED AND VERIFIED | `PHASE1_STORAGE_REPORT.md` (nothing deleted) |
| Remediation roadmap | COMPLETED AND VERIFIED | Audit, sections 4–6 |

## ML tasks

| Item | Status | Note |
|---|---|---|
| ML-01 sea-ice forecast (U-Net + SIC-only fallback) | COMPLETED AND VERIFIED | Test 2021–2025 metrics on file; live forecasts use the fallback (atmosphere cutoff) |
| ML-02 T2m forecast (U-Net) | COMPLETED AND VERIFIED | Test 2018–2025; U-Net station check missing (B7) |
| ML-03 SAR sea-ice detection | COMPLETED AND VERIFIED | Test 157 scenes; refit model below XGBoost on test (documented, B8) |
| ML-04 climate anomaly detection v1 | INVALIDATED (archived) | Three zero-filled raw files; see `experiments/ml04/v1_invalidated/README.md` |
| ML-04 v2 (A1): corrupt files re-downloaded, rebuilt from preprocessing, new frozen decision + single test | COMPLETED AND VERIFIED | `aethentra-ml04-lof-k20-20261111-v2`; test PR-AUC 0.296 (≈30× random); 2001–02 artefact gone; 92 tests pass |
| Download content QA (A2): `content_check` in the ML-01/ML-02 NCEP downloader, the ML-02 ERA5 checker and the ML-04 downloader; `scripts/check_raw_content.py` | COMPLETED AND VERIFIED | 432/432 NCEP files pass; 6 unit tests |

## Data

| Item | Status | Note |
|---|---|---|
| NSIDC SIC CDR v6 to 2026-11-01 | COMPLETED AND VERIFIED | MD5 vs manifest |
| NCEP R1 to 2026-03-17 | COMPLETED AND VERIFIED | Source ends there |
| ERA5 / MERRA-2 / Copernicus Marine | BLOCKED | No credentials (your registration needed) |

## Integration and presentation

| Item | Status | Note |
|---|---|---|
| FastAPI endpoints (existing) | COMPLETED AND VERIFIED | 36 GET endpoints return 200 (audit smoke test); POST endpoints not exercised (they write outputs) |
| Unified task registry `/api/tasks` | DEFERRED until approved | C1 |
| CORS for the Next.js frontend | DEFERRED until approved | C4 |
| Presentation bundle (lightweight JSON/PNG/GeoJSON) | DEFERRED until approved | D3 |
| Database | IMPLEMENTED BUT NOT VERIFIED (SQLite, ML-04 only) | No AETHENTRA Supabase project; DDL not applied |
| Next.js / CesiumJS / GSAP frontend | DEFERRED until approved | Specification due 14 Nov |
| Deployment / hosting | DEFERRED | Local server only |
| Scheduler | DEFERRED | Not registered |
| Git history repair (A3) | COMPLETED AND VERIFIED (local) | 3 unpushed commits rebuilt without data blobs (tree 14.4 → 0.82 GB, no file > 95 MB); messages and authors kept; data still on disk; `.gitignore` extended; backup at `H:/aethentra_git_backup_20261112` |
| Remote backup (push) | NOT DONE: awaiting your push | Current fixes are uncommitted in the working tree |
| PHASE1_PRESENTATION_READINESS / KNOWN_LIMITATIONS / API_CONTRACT / DATA_CATALOGUE / DEMO_CHECKLIST | DEFERRED until approved | Scheduled for 14 Nov |
