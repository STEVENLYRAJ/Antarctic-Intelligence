# ML-03 — Model Interpretability and Error Report

Computed on the TEST scenes after the single test evaluation (`src/aethentra/sar/analysis.py`). Error = disagreement with the USNIC chart (water/ice pixels).

Overall pixel error rate 0.078 over 29,810,452 pixels.

## Incidence-angle sensitivity

| incidence (°) | pixels | error rate |
|---|---|---|
| 18–21 | 2,201,366 | 0.097 |
| 21–24 | 2,716,607 | 0.092 |
| 24–27 | 2,771,687 | 0.095 |
| 27–30 | 3,052,161 | 0.088 |
| 30–33 | 3,041,907 | 0.078 |
| 33–36 | 3,207,051 | 0.066 |
| 36–39 | 3,452,624 | 0.066 |
| 39–42 | 4,013,525 | 0.070 |
| 42–45 | 4,716,439 | 0.069 |
| 45–48 | 637,085 | 0.075 |

## Coastal confusion (distance to coast)

| km | pixels | error rate |
|---|---|---|
| 0–10 | 534,460 | 0.153 |
| 10–25 | 836,852 | 0.101 |
| 25–50 | 1,382,040 | 0.093 |
| 50–100 | 2,511,630 | 0.084 |
| 100–200 | 4,259,680 | 0.109 |
| 200–400 | 3,984,729 | 0.053 |
| 400–2000 | 16,301,061 | 0.070 |

## Wind-roughened / bright open water (chart water pixels)

| HH σ⁰ (dB) | pixels | false-ice rate |
|---|---|---|
| -30–-28 | 216,036 | 0.052 |
| -28–-26 | 432,039 | 0.055 |
| -26–-24 | 726,426 | 0.030 |
| -24–-22 | 1,065,846 | 0.026 |
| -22–-20 | 1,496,384 | 0.034 |
| -20–-18 | 1,667,904 | 0.030 |
| -18–-16 | 1,546,900 | 0.029 |
| -16–-14 | 1,373,613 | 0.036 |
| -14–-12 | 1,238,716 | 0.053 |
| -12–-10 | 1,063,147 | 0.067 |
| -10–-8 | 901,770 | 0.042 |
| -8–-6 | 774,947 | 0.045 |
| -6–-4 | 702,094 | 0.033 |
| -4–-2 | 614,160 | 0.014 |
| -2–0 | 391,977 | 0.009 |

## Dark sea ice (chart ice pixels: new ice, nilas, wet/melting ice)

| HH σ⁰ (dB) | pixels | missed-ice rate |
|---|---|---|
| -30–-28 | 10,110 | 0.443 |
| -28–-26 | 17,941 | 0.367 |
| -26–-24 | 36,803 | 0.336 |
| -24–-22 | 95,486 | 0.250 |
| -22–-20 | 245,854 | 0.194 |
| -20–-18 | 702,635 | 0.094 |
| -18–-16 | 1,725,531 | 0.080 |
| -16–-14 | 2,980,295 | 0.074 |
| -14–-12 | 3,710,595 | 0.075 |
| -12–-10 | 2,762,697 | 0.126 |
| -10–-8 | 1,673,958 | 0.236 |
| -8–-6 | 776,973 | 0.229 |
| -6–-4 | 252,036 | 0.152 |
| -4–-2 | 77,613 | 0.168 |
| -2–0 | 28,808 | 0.158 |

## Seasonal

| month | pixels | error rate |
|---|---|---|
| 1 | 3,396,646 | 0.158 |
| 2 | 3,126,646 | 0.063 |
| 3 | 2,791,041 | 0.026 |
| 4 | 2,000,000 | 0.141 |
| 5 | 2,470,275 | 0.087 |
| 6 | 2,282,888 | 0.031 |
| 7 | 2,270,287 | 0.113 |
| 8 | 2,800,000 | 0.051 |
| 9 | 2,409,569 | 0.077 |
| 10 | 2,800,000 | 0.043 |
| 11 | 2,000,000 | 0.055 |
| 12 | 1,463,100 | 0.092 |

## Ice-edge score vs tolerance (post-test sensitivity, final model)

Mean scene boundary F1 by tolerance: 2 (evaluation setting) km: 0.022, 4 km: 0.042, 10 km: 0.107. The 2 km evaluation tolerance is tighter than the 4 km chart-boundary buffer, so low values mainly reflect chart-scale edge placement, not only model error.

Chart-uncertain pixels (10–70 % concentration or boundary buffer) predicted as ice: 0.405 (the model is forced to a binary decision there; these pixels are excluded from all scores).

Top rf feature importances: lat 0.112, std15 0.109, mean15 0.097, glcm_entropy 0.094, glcm_homogeneity 0.064, mean7 0.063, doy_sin 0.060, glcm_contrast 0.058

Top xgb feature importances: glcm_entropy 0.315, mean7 0.158, std15 0.130, mean15 0.124, lat 0.041, doy_cos 0.033, doy_sin 0.030, dist_coast_km 0.027

## Comparison with DMI-ASIP (pseudo-label, one day)

Not computed: no overlap: the DMI-ASIP file has valid data over only 1.3% of its Antarctic grid on 2023-02-02, none of it within the 3 processed Sentinel-1 scene(s) of that day.

## Validation categories

* Model prediction vs **pseudo-label agreement** (DMI-ASIP): above.
* **Independent validation**: agreement with USNIC expert charts (independent of the model, chart-scale).
* **Expert-confirmed validation**: none yet (no reviewer available; ANNOTATION_GUIDELINES.md).