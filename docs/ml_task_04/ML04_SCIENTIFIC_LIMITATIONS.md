# ML-04 Scientific Limitations

1. **Statistical, not physical, anomalies.** Every output says how unusual a value is relative to a fixed baseline. That does not:
   - confirm an extreme event;
   - identify a cause;
   - show climate-change attribution.

   Compound co-occurrences are spatial and temporal coincidences only, with no causal relation implied.

2. **Single reanalysis, and NCEP R1 in particular.**
   - NCEP/NCAR R1 is a first-generation reanalysis with documented weaknesses at high southern latitudes. These include spurious pressure trends and lower skill in early decades (e.g. Marshall 2003, J. Climate; Bromwich & Fogt 2004, J. Climate).
   - Precipitation and cloud are model forecast fields with large errors over Antarctica (data tier C).
   - Sea-level pressure over the high plateau is an extrapolation (values up to about 1123 hPa).
   - ERA5 would be preferable, but it needs a personal CDS token that is not configured.

3. **Record ends 2026-03-17.** NOAA PSL's NCEP R1 daily files stop there. As a result:
   - multivariate and atmospheric anomalies stop at February 2026;
   - from March 2026 only sea-ice anomalies continue.

   The system does not claim real-time or continuous monitoring.

4. **Non-stationarity versus a fixed baseline.** Relative to 1981–2010, the multivariate flagged-area fraction rises from 5.3 % in training to 12.3 % in validation and 13.7 % in test (v2). Against the 1991–2020 baseline, univariate exceedance rates in test are close to the nominal 5 % (Phase 1 audit §3.6). A fixed baseline therefore flags persistent shifts as anomalies. This explains why some "events" (DBSCAN clusters linked across months) last about two years, for example 2015-10 to 2017-09 (24 months, v2). Those are persistent anomaly regimes, not discrete events.

   The trailing-30-year "rolling" method is provided to separate this effect.

5. **Small baseline samples.**
   - A 30-year monthly baseline means P05/P95 rest on one or two values per tail.
   - Monthly standard deviations from n = 30 are noisy.
   - Thresholds for years inside the baseline are calibrated in-sample, which understates how extreme out-of-sample years look. This mainly affects the percentile detector, which flags 43 % of test samples (v2) and is used for interpretation only.

6. **Evaluation relies on synthetic injections.**
   - No labelled real anomaly catalogue exists.
   - Synthetic recovery measures sensitivity to the injected patterns, not to real event types.
   - Real-world checks are limited: 16 stations, which are partly non-independent because of assimilation and point-vs-cell scale, and 5 literature events (qualitative).
   - Compound shifts are hard for every method (PR-AUC ≤ 0.05).

7. **Resolution and scale.**
   - 2.5° cells are about 280 km × 50–110 km. Coastal, katabatic and peninsula-scale events are smoothed.
   - SIC is averaged into these cells; native 25 km SIC anomaly maps are provided for detail.
   - Daily-mean wind vectors underestimate mean wind speed.

8. **Spatial dependence.** Cell-months are not independent, so flag counts are not counts of independent events. No geographic hold-out was used for selection; per-region numbers are descriptive.

9. **SIC imputation and gaps.**
   - Where SIC does not exist (ice sheet, or ocean coverage < 25 %), z_sic is set to 0.
   - For the four training months with a satellite-record gap (1984-08, 1986-12, 1987-12, 1988-01), the sea-ice features are also imputed as 0.

10. **Uncertainty.** The detectors give no calibrated probability. The confidence indicators (method agreement, data tier) are ordinal aids, not probabilities.

11. **Data-defect history.** v1 was built on three all-zero NCEP files (rhum 2001, rhum 2002, tcdc 2001). It is invalidated and archived.
    - v2 uses re-downloaded files.
    - Every download now passes a content check: not all-zero, not constant, no flat days, values inside a plausible range.
    - NCEP R1 humidity rises over 2021–2025 (domain mean about 72 % → 74 %). Whether this is physical or a reanalysis artefact cannot be established without a second reanalysis.
