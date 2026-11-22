# AETHENTRA Phase 1 (Antarctic): Final Audit and Remediation Roadmap

**Audit date:** 2026-11-11. **Presentation deadline:** 24 November 2026 (13 days).

**Audit mode: read-only.**

- Nothing was modified, retrained, downloaded, deleted, moved or installed.
- The only files written are this report, `PHASE1_STORAGE_REPORT.md` and `PHASE1_PROGRESS.md` in `docs/phase1/`.
- Remote checks were read-only metadata queries:
  - the OPeNDAP time axis, which NOAA PSL refused with HTTP 429 on the second attempt;
  - a Supabase project listing.
- Every statement below cites the file or command that supports it.

---

## 1. Executive summary

Phase 1 has four working ML tasks, a FastAPI backend (36 GET endpoints respond with 200) and a static viewer. Four issues must be handled before frontend work starts, because they affect the scientific credibility of what will be shown or the safety of the work itself.

| # | Finding | Class | Why it matters for 24 Nov |
|---|---|---|---|
| **P0-1** | **Three ML-04 raw files are entirely zeros**: relative humidity 2001 and 2002, cloud cover 2001. They passed the download check and sit inside both baselines (1981–2010, 1991–2020). | 1 Critical scientific | The humidity and cloud climatologies are contaminated: humidity z-scores are compressed to σ ≈ 0.45 instead of ≈ 1, and 2001–02 are falsely anomalous. The current ML-04 fit, selection and single test (v1) are therefore **invalid** for humidity and cloud, and affected for the multivariate detectors. |
| **P0-2** | **The git repository is unsafe to push and close to a destructive commit.** HEAD tracks 14.2 GB across two unpushed commits, including files from 100 MB to 2.6 GB (GitHub rejects files over 100 MB). A further 15.6 GB array (`data/processed/aethentra/cnn/trainval_X.npy`) is staged. | 6 Deployment | None of the ML-02 deep learning, ML-03 or ML-04 code has an off-machine backup. One `git commit` would add 16.5 GB more. |
| P1 | The atmospheric record (NCEP/NCAR R1 at NOAA PSL) ends on **2026-03-17**, and no ERA5 credentials exist. | 2 Data availability | The latest ML-02 forecast covers 1–7 Jan 2026. ML-01 runs on its sea-ice-only fallback, and ML-04 multivariate output stops at Feb 2026. This must be presented honestly as a data cutoff. |
| P1 | No Next.js/CesiumJS/GSAP frontend exists. There is no CORS middleware, the task interfaces are inconsistent, and there are cold starts of 40 s. | 4/5 | These are the main engineering work before 24 Nov. |

**Recommended overall plan:**

1. Fix the two P0 items on 12 Nov.
2. Unify the backend and build a lightweight presentation data bundle on 13–14 Nov.
3. Build the frontend against a frozen API contract on 15–21 Nov.
4. Rehearse on 22–23 Nov.
5. **Defer ERA5** until after the presentation. It needs your CDS key, an uncertain CDS queue time, and retraining of three tasks.

---

## 2. Repository inventory (verified)

| Component | Location | State |
|---|---|---|
| ML-01 sea-ice forecast | `src/aethentra/{data,features,training,inference,…}`, `configs/*.yaml` | Final LightGBM + U-Net (operational when atmosphere data exist), SIC-only fallback. Test 2021–2025 |
| ML-02 2 m temperature | `src/aethentra/temperature/`, `configs/ml02/` | Final LightGBM + U-Net (operational). Test 2018–2025. Truth = NCEP R1 (interim ERA5 substitute) |
| ML-03 SAR sea-ice detection | `src/aethentra/sar/`, `configs/ml03/` | U-Net (BCE+Dice) refit. Test 157 scenes, 2025-01 to 2026-10. Weekly composite for week 2026-11-02 |
| ML-04 climate anomaly | `src/aethentra/anomaly/`, `configs/ml04/` | LOF k=20 selected. **v1 affected by P0-1** |
| Backend | `api/main.py` + `temperature.py`, `seaice_detection.py`, `anomaly.py`, `viewer.py` | 50 routes; uvicorn on 127.0.0.1:8000 |
| Viewer | `frontend/` (static HTML/JS/CSS, 4 tabs) | Works; not the requested Next.js/Cesium site |
| Database | `data/processed/ml04/ml04.sqlite` (ML-04 only) | No AETHENTRA Supabase project exists. The only project on the connected account is an unrelated, inactive "Cinema Vault". `configs/ml04/supabase_schema.sql` has **not** been applied |
| Deployment | — | No Dockerfile, compose file, CI or hosting config. Local only |
| Scheduler | `scripts/ml04/update_pipeline.py` | Not registered with any scheduler |
| Tests | `tests/` | Last full run (2026-11-11): 86 passed, 1 failed (the pre-existing Stage-1 inventory test). Not re-run in this audit because `conftest.py` writes `experiments/logs/pytest_summary.json` |
| Git | `main`, two commits ahead of `origin/main` | See P0-2 |

### 2.1 Headline test metrics (from `summary.json` files)

**ML-01: weekly SIC, test 2021–2025, truth = NSIDC CDR v6 (real observations).**

| Model | Area-weighted MAE (pp) | Extent MAE (km²) |
|---|---|---|
| U-Net (operational when atmosphere data exist) | 1.25 | 106,000 |
| LightGBM | 1.37 | 127,000 |
| SIC-only fallback | 1.39 | 125,000 |
| Persistence | 1.68 | 395,000 |
| Climatology | 4.88 | — |

**ML-02: weekly T2m, test 2018–2025, truth = NCEP R1 reanalysis.**

| Model | Area-weighted MAE (°C) | ACC |
|---|---|---|
| U-Net | 2.37 | 0.59 |
| LightGBM | 2.47 | 0.54 |
| Damped persistence | 2.70 | — |
| Climatology | 3.00 | — |

ML-02 also has a real-observation check: weekly station anomalies at 40 stations (10,394 station-weeks), for the LightGBM model.

| Source | Anomaly correlation | Anomaly MAE (°C) |
|---|---|---|
| Reanalysis itself vs stations | 0.78 | — |
| LightGBM | 0.39 | 2.28 |
| Persistence | 0.38 | — |
| Climatology | — | 2.48 |

The U-Net has **not** been station-evaluated.

**ML-03: test, 157 scenes, labels = USNIC expert charts (real, chart-scale).**

| Model | mIoU |
|---|---|
| XGBoost | 0.896 |
| Random Forest | 0.890 |
| U-Net BCE+Dice (before refit) | 0.885 |
| **Selected refit** | **0.867** |
| Threshold | 0.487 |

The selected refit model is also weak in specific conditions:

- summer (DJF) mIoU is 0.727;
- boundary F1 at 2 km is 0.022.

**ML-04 v1: synthetic-injection PR-AUC on test** (random baseline ≈ 0.01):

| Detector | PR-AUC |
|---|---|
| LOF | 0.364 |
| Autoencoder | 0.182 |
| Mahalanobis | 0.168 |
| z-score | 0.061 |

**Superseded by P0-1.**

---

## 3. Investigations requested

### 3.1 ERA5 CDS access and credentials

- No credentials are present anywhere:
  - no `~/.cdsapirc`, `.env` or `~/.netrc`;
  - `CDSAPI_KEY`, `CDSAPI_URL` and `EARTHDATA_*` are unset.
- `cdsapi` is installed.
- `EXTERNAL APIs/API.py` and `PRESSUREAPI.py` are request templates without keys.

**Result:** ERA5, MERRA-2 and Copernicus Marine are **BLOCKED** on user registration.

**Effort if unblocked:**

- 1–3 days of CDS queue time and download (CDS queues are not under our control);
- 1–2 days to retrain ML-01 (atmosphere branch), ML-02 and ML-04;
- each retrain needs a new frozen decision and test.

**Recommendation:** do not attempt this before 24 Nov.

### 3.2 Atmospheric coverage and cutoff

- **Last NCEP day:** NCEP R1 daily data end on **2026-03-17** in every local file (`data/processed/ml04/quality_report.json`). The remote time axis was verified earlier today; a re-check during this audit was refused with HTTP 429.
- **NCEP/DOE R2:** whether R2 is more current is **unverified**, also because of the 429.
- **SIC CDR:** runs to **2026-11-01**.
- **Source defects already handled in ML-04 preprocessing:**
  - the 2026 `uwnd` file repeats 2025 dates as NaN after 17 March;
  - the 2026 `uwnd` and `vwnd` files differ in length.

**Consequences of the cutoff for each task:**

| Task | Consequence |
|---|---|
| ML-01 | Live forecasts use the SIC-only fallback (test MAE 1.39 pp vs 1.25 for the U-Net) |
| ML-02 | No forecast can be issued after 2026-03-17. The latest saved forecast covers 1–7 Jan 2026 |
| ML-04 | Multivariate anomalies stop at Feb 2026; SIC anomalies continue to Oct 2026 |
| ML-03 | Unaffected (Sentinel-1 is current) |

### 3.3 Corrupt source files (new finding, P0-1)

A content scan of all 432 NCEP files on disk (ML-01, ML-02 and ML-04 copies) found exactly three files whose every value is 0:

- `ncep_r1_rhum_2001_south.nc`
- `ncep_r1_rhum_2002_south.nc`
- `ncep_r1_tcdc_2001_south.nc`

All three are ML-04 downloads, and their provenance says `complete_year: true`. The likely cause is degraded OPeNDAP responses during the server's access-failure and 429 episodes: the downloader checks the number of days, not the content. **The ML-01 and ML-02 inputs (air, slp, uwnd, vwnd) are clean.**

**Effect on ML-04:**

- Mean humidity over the domain is 0 % in 2001–02 against about 71 % in other years.
- The year-to-year standard deviation of z_rhum is about 0.45 in normal years instead of ≈ 1.
- Humidity flags fall from 5.6 % (training) to 0.1 % (validation and test). This is an artefact, not a climate signal.
- The 2001–02 flag bumps (LOF flag area 0.069 and 0.076, against about 0.04 in neighbouring years) are artefacts too.

**Fix:**

1. Re-download the three files (about 3 MB).
2. Add a content check (constant or all-zero fields, value ranges) to the downloader.
3. Rebuild ML-04 from preprocessing onward.
4. Issue a new decision (v2) and a new single test, with v1 kept and marked "invalidated by data defect".

Re-testing is justified here because the defect is in the data, not in a model choice made by looking at test results.

### 3.4 Compound anomaly detection performance

Every detector scores PR-AUC ≤ 0.045 on the `compound_moderate` injections. **This is mainly an evaluation-design problem, not a model that could be tuned.** Those injections shift two variables by 1.5–2.5σ. A ±2σ shift in two roughly independent dimensions has a Mahalanobis length of about 2.8, which is close to the *median* length of normal 9-dimensional samples (about 3). In density terms they are not anomalous, so no density-based detector can separate them.

**Recommendation:**

- Evaluate compound events with the explicit co-occurrence rule that already exists (`compound_cooccurrence.parquet`).
- Compare observed co-occurrence rates with the independence expectation, which is already computed. For example, warm + low sea ice occurs in 2,071 cell-months against an expectation of about 0.03 % of samples.
- Report the detector PR-AUC on compound injections as a known limitation, not as a target to improve.

Effort: 2 h after P0-1.

### 3.5 PR-AUC and class imbalance

- Injected prevalence is 1 % (2,211 of 221,184 test samples), so a random detector scores PR-AUC ≈ 0.01. LOF's 0.36 is roughly 36× random.
- The "negatives" are real cell-months, about 10 % of which are genuinely unusual relative to 1981–2010. This lowers precision for every method.
- **Recommendation:** report PR-AUC together with:
  - the prevalence and the lift over random;
  - precision at fixed recall;
  - recall at the moderate threshold;
  - the false-alarm (flag) rate.

  Do not re-weight or resample to inflate the metric. Effort: 1 h (re-scoring only, no refit).

### 3.6 Post-2011 increase in anomaly flags

This was measured from existing outputs, in memory only.

| Variable | Exceedance of \|z\| ≥ 1.96 in test (2018–2025), 1981–2010 baseline | Same, 1991–2020 baseline | Expected |
|---|---|---|---|
| t2m | 8.2 % | 5.7 % | 5 % |
| slp | 6.8 % | 4.9 % | 5 % |
| z500 | 7.0 % | 5.6 % | 5 % |
| sic | 3.6 % | 2.7 % | — |

Mean test-period shifts relative to 1981–2010 are:

- t2m +0.36σ;
- slp −0.28σ;
- z500 +0.16σ;
- sic −0.13σ.

**Interpretation:** most of the increase is a **baseline effect**. Recent climate differs from 1981–2010, through warming, lower Antarctic sea-level pressure consistent with the positive Southern Annular Mode trend, and post-2016 sea-ice loss. Against 1991–2020, the rates are close to nominal.

Part of the pressure trend may be spurious, because NCEP R1 has documented spurious high-latitude pressure trends. That cannot be separated without a second reanalysis (ERA5).

Humidity (P0-1) also distorts the per-variable picture.

**Recommendation:**

- Present flags with the baseline stated.
- Add a baseline-sensitivity table: 1981–2010 vs 1991–2020 vs the trailing 30-year rolling baseline, which already exists in code.
- Do **not** switch the model baseline to 1991–2020. That would put validation and test years inside the baseline used for evaluation.

Class: 1 (interpretation) and 7 (document). Effort: 2 h after P0-1.

### 3.7 Baseline-period sensitivity

The results in 3.6 show this directly. Statistical flag rates depend more on the choice of baseline than on the choice of detector. A sensitivity panel is a strong, honest presentation element.

### 3.8 Availability of real-world labelled validation

| Task | Real validation | Status |
|---|---|---|
| ML-01 | SIC CDR observations | Real (satellite observations) |
| ML-02 | NCEP R1 (reanalysis) + 40 stations | Station check exists for LightGBM only; **U-Net station evaluation missing** (inference only, ~1 h) |
| ML-03 | USNIC expert charts | Real, chart-scale (not pixel truth). DMI-ASIP comparison: no spatial overlap |
| ML-04 | No labelled anomaly catalogue exists | Real checks used: 16 GHCN stations (r = 0.72 in test), 5 literature events (qualitative). **Additional real check available:** the independent NSIDC Sea Ice Index (G02135, on disk) for record-low sea-ice periods, about 2 h |

Synthetic injections are labelled as synthetic everywhere. They must never be shown as real events in the frontend.

### 3.9 Temporal and spatial leakage

| Task | Check | Result |
|---|---|---|
| ML-01 | Splits by issue date (train ≤ 2015, validation 2016–2020, test 2021–2025). Final climatology period 1979–2020; final train 1979–2020 | **No leakage** |
| ML-02 | Climatology 1981–2010; final train 1979–2017; test 2018–2025 | **No leakage** |
| ML-03 | Scene-level split by chart date (train 2018–2022, validation 2023–24, test 2025–26). No tiles of one scene cross splits | **No leakage**. Spatial overlap of the same geography across years is inherent and acceptable |
| ML-04 | Baseline 1981–2010 inside the 1979–2010 training years; hyperparameters on validation only; seasonal and rolling methods trailing-only; injection pairs taken from training correlations | **No leakage**. One caveat: autoencoder early stopping uses unlabelled validation features (standard practice; documented) |

---

## 4. Issue register

**Classes:**

1. Critical scientific issue
2. Data availability issue
3. Model performance issue
4. Backend integration issue
5. Frontend readiness issue
6. Deployment issue
7. Acceptable limitation, document only

**Effort** is engineer time; compute time is noted where it matters.

| ID | Issue | Class | Priority | Depends on | Effort | Needs your approval for |
|---|---|---|---|---|---|---|
| **A1** | ML-04 rhum 2001/2002 and tcdc 2001 raw files are all zeros, so the v1 baselines, detectors, decision and test are affected | 1 | **P0** | — | 0.5 h + ~40 min compute | Re-download 3 files; retrain ML-04; new decision and test (v2) |
| **A2** | Downloaders (ML-01, ML-02, ML-04) do not check content (constant or zero fields, ranges) | 1 | **P0** | — | 1 h | Code change |
| **A3** | Git: 14.2 GB tracked in 2 unpushed commits (files up to 2.6 GB, which GitHub rejects); a 15.6 GB array staged; no remote backup since the first commit | 6 | **P0** | — | 1–2 h | Unstage; rewrite the 2 **unpushed** local commits; extend `.gitignore` (the CNN arrays were missed there) |
| B1 | Post-2011 flag increase is mostly a baseline effect; needs a sensitivity product and framing | 1/7 | P1 | A1 | 2 h | — |
| B2 | Compound-injection evaluation cannot be passed by density detectors (design issue); co-occurrence rule needs its own evaluation | 3/7 | P1 | A1 | 2 h | — |
| B3 | PR-AUC reporting lacks prevalence, lift and precision at fixed recall | 7 | P1 | A1 | 1 h | — |
| B4 | Percentile detector flags 40 % (calibration is in-sample, n = 30). Keep it as an interpretation aid only | 3/7 | P2 | A1 | 0.5 h (documentation) | — |
| B5 | NCEP R1 ends 2026-03-17; ERA5 credentials absent | 2 | P1 (document) / P3 (fix) | Your CDS key | Document 1 h; ERA5 3–5 days | CDS registration; retrains |
| B6 | Latest ML-02 forecast is 1–7 Jan 2026. A forecast issued on 2026-03-17 (the last data day) is possible without retraining | 2 | P2 | — | 0.5 h | Writes a new forecast output |
| B7 | ML-02 U-Net not evaluated against stations | 3 | P2 | — | 1 h (inference only) | — |
| B8 | ML-03 selected refit is worse on test than XGBoost, RF and the pre-refit U-Net; weak in summer and at boundaries | 3/7 | P2 | — | Document 0.5 h | Do **not** switch models after the test (that would select on test data) |
| B9 | ML-04: add the independent NSIDC Sea Ice Index real check for record-low periods | 2/3 | P2 | A1 | 2 h | — |
| B10 | Pre-existing Stage-1 test fails (`DATAS/*.umm_json` not in the inventory) | 4 | P3 | — | 0.5 h | Regenerate the Stage-1 inventory |
| C1 | Inconsistent task interfaces (`/forecast`, `/temperature`, `/seaice-detection`, `/api/ml04`); no unified task registry (name, model, provenance, inputs, output schema, metrics, limitations, inference status) | 4 | P1 | A1 (ML-04 metrics) | 0.5–1 day | Additive endpoints only; existing ones kept |
| C2 | Cold starts: `/model/info` 39.9 s, `/temperature/model/info` 7.9 s | 4 | P1 | C1 | 1–2 h | — |
| C3 | Heavy payloads: `/api/ml04/sea-ice-extent` 4.2 MB, `seasonal-summary` 1.8 MB unfiltered | 4 | P1 | — | 2 h | — |
| C4 | No CORS middleware, so a Next.js dev or production origin cannot call the API | 4 | P1 | — | 15 min | — |
| C5 | Write-heavy POST endpoints (`/forecast/weekly`, `/temperature/forecast/weekly`, `/seaice-detection/detect/sea-ice`) can be triggered from a public demo; SAR fetches from Planetary Computer on demand | 4/6 | P2 | — | 1 h (read-only demo mode flag) | — |
| C6 | No AETHENTRA database; SQLite only (ML-04). Supabase: no AETHENTRA project | 4/6 | P3 | Your decision | SQLite as-is 0 h; Supabase 0.5–1 day | Creating a cloud project is an outward action |
| D1 | No Next.js / CesiumJS / GSAP frontend | 5 | P1 | C1–C4, D2, D3, spec | 5–7 days | Start of the build |
| D2 | Map layers are server-rendered polar PNGs (EPSG:3412/3031); Cesium needs EPSG:4326 imagery with bounds, or GeoJSON. ML-01 already exports some | 5 | P1 | A1 | 0.5–1 day | — |
| D3 | No lightweight presentation bundle (static JSON/PNG snapshot), so the frontend depends on a live backend | 5/6 | P1 | A1, C1 | 0.5 day | — |
| E1 | No deployment config (Docker, hosting); local-only server | 6 | P2 | — | Local demo 0 h; Docker 0.5 day | Hosting choice |
| E2 | The live demo depends on remote services (NOAA PSL was rate-limited at audit time; Planetary Computer for SAR) | 6 | P1 | D3 | Covered by D3 | — |
| E3 | No scheduler registered (the NCEP source no longer updates anyway) | 7 | P3 | — | Document | — |
| F1 | 2.5° resolution; NCEP R1 quality (precipitation and cloud are tier C; SLP on the plateau is extrapolated); SIC gaps 1984/1986/1987–88; no VAE/ConvLSTM; chart labels are not pixel truth; no DMI-ASIP overlap | 7 | — | — | Already documented | — |

**Dependency graph:**

```
A3 (git safety) ─────────────────────────────────────────┐
A2 (download QA) ─► A1 (ML-04 v2 rebuild) ─► B1, B2, B3, B4, B9 ─► C1 (task registry) ─► D3 (bundle) ─► D1 (frontend)
                                                           C2, C3, C4 ────────────────────────────────────┘
D2 (Cesium layers) ─────────────────────────────────────────────────────────────────────────────► D1
B5 (ERA5) ─► [after 24 Nov] retrain ML-01 atmosphere branch / ML-02 / ML-04
```

---

## 5. Prioritised remediation roadmap (to 24 Nov 2026)

| Day | Work | Output | Gate |
|---|---|---|---|
| **Wed 12 Nov** | **P0:** A3 git safety (unstage, repair the 2 unpushed commits, `.gitignore`, push code and metadata only). A2 download QA. A1 re-download 3 files, rebuild ML-04 v2, frozen decision v2, single test v2. Re-run the full test suite | Safe remote backup; valid ML-04 | Your approval of A1/A2/A3 |
| Thu 13 Nov | B1–B4 and B9 (ML-04 scientific framing: baseline sensitivity, co-occurrence evaluation, lift metrics, Sea Ice Index check). B7 (ML-02 U-Net station check). C4 CORS | Defensible ML-04 numbers | — |
| Fri 14 Nov | C1 unified `/api/tasks` registry; C2 caching; C3 lightweight endpoints; D2 EPSG:4326 layers + GeoJSON; D3 presentation bundle. Write PHASE1_API_CONTRACT, DATA_CATALOGUE, KNOWN_LIMITATIONS, PRESENTATION_READINESS, DEMO_CHECKLIST | **API contract frozen** | You review the contract |
| Sat 15 – Fri 21 Nov | D1 frontend build to the specification (intro, globe, data catalogue, 4 task sections, climate explorer, insights, architecture) | Working site, local | Mid-point review on 18 Nov |
| Sat 22 Nov | Integration test, performance pass, offline fallback using the bundle; C5 read-only demo mode | Release candidate | — |
| Sun 23 Nov | Rehearsal against the demo checklist; freeze; tag a release | Frozen demo | — |
| **Mon 24 Nov** | Presentation | — | — |

**Explicitly deferred** until after 24 Nov:

- ERA5, MERRA-2 and Copernicus Marine (B5);
- Supabase (C6), unless you want it;
- Docker and hosting (E1), unless a remote audience must reach the site;
- re-architecture of any kind.

**Not recommended at all:**

- switching the ML-03 production model to XGBoost after having seen the test results;
- forcing ML-04 metrics upward by resampling or by moving the baseline into the test years.

---

## 6. Decisions needed from you

1. **Approve P0 (A1–A3).** This covers:
   - re-downloading 3 corrupt NCEP files and rebuilding ML-04 as v2;
   - rewriting the 2 **unpushed** local commits so that data files are removed from history (nothing on GitHub is touched), then pushing.
2. **ERA5:** confirm it is deferred until after 24 Nov (recommended), or provide a CDS key now, accepting the schedule risk.
3. **Database:** keep local SQLite for the presentation (recommended), or create a new Supabase project. That is an external action and needs your go-ahead.
4. **Hosting:** run locally on the presentation laptop (recommended), or provide a public URL (Docker + host, about 0.5 day).
5. **Frontend scope:** confirm the section list in the brief. I will write the full Next.js/CesiumJS/GSAP specification on 14 Nov, against the frozen API.
