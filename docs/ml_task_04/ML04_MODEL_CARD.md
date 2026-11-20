# ML-04 Model Card: Antarctic Climate Anomaly Detector (v2)

> **v1 was invalidated (2026-11-12).**
>
> - **Cause:** three NCEP R1 raw files (rhum 2001, rhum 2002, tcdc 2001) were all zeros and contaminated both baselines.
> - **Fix:** the files were re-downloaded through a new content check and ML-04 was rebuilt from preprocessing.
> - **Result:** a new frozen decision and a new single test (v2).
> - **Do not cite v1 numbers.** v1 artefacts are kept under `models/ml04/v1_invalidated/` and `experiments/ml04/v1_invalidated/`.

| | |
|---|---|
| Model version | `aethentra-ml04-lof-k20-20261111-v2` |
| Operational multivariate detector | Local Outlier Factor (novelty mode, k = 20, fitted on 50,000 training cell-months) |
| Reference methods (always shown) | z-score, empirical percentile, robust median/MAD, Mahalanobis distance; seasonal (trailing 3-month) and rolling (trailing 30-year) z for reporting |
| Unit of analysis | One 2.5° cell (87.5° S–50° S) in one calendar month |
| Inputs | 9 standardised anomalies against the 1981–2010 calendar-month baseline: t2m, slp, wind speed, rhum, precipitation, cloud, z500, SIC, and month-to-month SIC change |
| Data | NCEP/NCAR R1 daily (NOAA PSL) and NOAA/NSIDC SIC CDR v6. All raw files pass the content check |
| Training | 1979–2010 (884,736 cell-months; only samples with all atmospheric variables) |
| Selection | Validation 2011–2017. Decision v2 frozen 2026-11-11 03:41 UTC (`models/ml04/decision.json`) |
| Test | 2018–2025, evaluated once (03:41:53 UTC) after the freeze |
| Output | Anomaly score, base-rate severity class, per-variable ablation contributions, and agreement with the univariate methods |

## Intended use

- Screening monthly Antarctic reanalysis and sea-ice fields for statistically unusual conditions, especially unusual combinations of variables.
- Prioritising cases for expert review.
- Producing maps and summaries with a traceable baseline.

**Not intended for:** confirming extreme events, attributing causes or climate change, operational warnings, or daily or point-scale decisions.

## Severity and confidence

**Severity** is the percentile of the score within its 1979–2010 training distribution:

| Class | Percentile range |
|---|---|
| normal | < P90 |
| mild | P90–P95 |
| moderate (flag) | P95–P98 |
| strong | P98–P99.5 |
| extreme | ≥ P99.5 |

"Extreme" means statistically extreme relative to the baseline climate, not an impact category.

**Confidence is reported separately** and is not a probability:

- **method agreement (k/4):** how many of z, percentile, MAD and LOF flag the case;
- **data tier (A/B/C):** see the data documentation.

## Evaluation (v2)

No labelled set of real Antarctic anomalies exists. Detectors were therefore compared on **synthetic injected anomalies**, which are labelled synthetic everywhere:

- 1 % of real cell-months in each split;
- injections are univariate 3–5σ spikes, moderate 1.5–2.5σ compound shifts, or covariance breaks;
- prevalence is 1 %, so a random detector scores PR-AUC ≈ 0.01.

| Method | Val PR-AUC | Test PR-AUC | Test lift over random | Univariate | Compound | Covariance break | Recall at moderate | Flag rate, non-injected |
|---|---|---|---|---|---|---|---|---|
| **LOF k=20 (selected)** | **0.273** | **0.296** | **≈30×** | 0.167 | 0.031 | 0.285 | 0.84 | 0.130 |
| Mahalanobis | 0.171 | 0.161 | ≈16× | 0.065 | 0.022 | 0.133 | 0.84 | 0.123 |
| Autoencoder (bottleneck 5) | 0.139 | 0.140 | ≈14× | 0.062 | 0.015 | 0.117 | 0.70 | 0.092 |
| One-Class SVM (ν = 0.01) | 0.097 | 0.104 | ≈10× | 0.056 | 0.019 | 0.046 | 0.84 | 0.137 |
| z-score (max \|z\|) | 0.056 | 0.056 | ≈6× | 0.045 | 0.013 | 0.012 | 0.66 | 0.144 |
| Isolation Forest (4096) | 0.036 | 0.039 | ≈4× | 0.015 | 0.013 | 0.013 | 0.51 | 0.117 |
| MAD | 0.033 | 0.036 | ≈4× | 0.022 | 0.009 | 0.009 | 0.40 | 0.086 |
| Percentile | 0.024 | 0.023 | ≈2× | 0.008 | 0.009 | 0.007 | 0.89 | 0.433 |

**Selection.** Validation rank-sum of the four PR-AUCs, among candidates with seed-stability Spearman ≥ 0.9:

- LOF 4, Mahalanobis 8, OCSVM 12, z 17, IF 20, MAD 23, percentile 28.
- The autoencoders were ineligible: their stability was 0.85–0.87.

The test confirms the validation ranking.

**Reading the numbers:**

1. **Low absolute PR-AUC.** The negatives are real cell-months, and many of them are genuinely unusual relative to 1981–2010.
2. **Compound injections** (PR-AUC ≤ 0.031 for every method) are an **evaluation-design limitation**. A ±2σ shift in two roughly independent variables lies near the median Mahalanobis length of normal 9-dimensional samples, so no density detector can separate it. Compound events are reported through the explicit co-occurrence rule instead.
3. **Isolation Forest** does poorly on single-variable spikes in 9 dimensions, because it picks split features at random.
4. **Flag rates on real non-injected data** are 12–14 % for most detectors in test, against the nominal 5 %. This mostly reflects a changed climate relative to the fixed 1981–2010 baseline. See the limitations, and the Phase 1 audit (§3.6) for the baseline-sensitivity analysis.
5. **The percentile detector is unsuitable as a flag rule.** It flags 43 % of test cell-months, because its calibration is in-sample with n = 30. It is used for interpretation only.
6. **What changed from v1:** compared with v1 (defective data), humidity now has realistic variance. That makes the univariate detectors flag more often, and lowers every detector's PR-AUC slightly. The ranking is unchanged.

## Seed stability (validation, Spearman between seeds 42 and 7)

| Detector | Spearman |
|---|---|
| Isolation Forest | 0.99 |
| LOF k=100 | 0.99 |
| OCSVM | 0.96–1.00 |
| LOF k=20 | 0.93 |
| Autoencoders | 0.85–0.87 |

## Independent real-data checks (after the freeze)

**Stations.** GHCN-D monthly TAVG anomalies at 16 stations, compared with the NCEP cell t2m z:

| Split | Pearson r | Cohen κ |
|---|---|---|
| Train | 0.78 | — |
| Validation | 0.81 | — |
| Test (1,530 pairs) | 0.72 | 0.40 |

**Literature-documented events.** This check is qualitative (n = 5) and was not used for selection. "Detected" means at least 20 % of the box's cell-months were flagged in the stated direction.

| Event | Mean z in box | Univariate flagged | LOF flagged |
|---|---|---|---|
| Feb 2020 Peninsula warm event | +2.0 | 60 % | 9 % |
| Mar 2022 East Antarctic heatwave | +1.0 | 26 % | 17 % |
| 2023 record-low winter sea ice | −0.66 | 17 % | 19 % |
| 2016 spring sea-ice retreat | −0.39 | 11 % | 19 % |
| Jan–Feb 2017 sea-ice low | ≈0 | 1 % | 21 % |

The daily extent product independently marks 277 record-low-for-date days in 2023.

**What this means:** single-variable events need the univariate products. The multivariate detector complements them; it does not replace them.

## Retraining policy

**Frozen:** baselines, detectors, thresholds and the decision.

**Requires a new release number in `configs/ml04/anomaly.yaml`, a new frozen decision and a single new test:**

- any change of data, baseline or model;
- a data defect (as happened with v1 → v2).
