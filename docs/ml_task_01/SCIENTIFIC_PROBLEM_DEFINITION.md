# Scientific Problem Definition — AETHENTRA ML Task 01

## 1. Objective
Forecast **Antarctic sea-ice concentration (SIC)** one week ahead on the native 25 km grid of the NOAA/NSIDC passive-microwave
Climate Data Record v6 (G02202), and derive **sea-ice extent (SIE)** and **sea-ice area (SIA)** from the forecast.

## 2. Quantities

| Symbol | Definition | Units |
|---|---|---|
| `SIC_d(c)` | Daily CDR concentration `cdr_seaice_conc` of ocean cell *c* on day *d* (scale factor removed) | % (0–100) |
| **Target** `Y_t(c)` | **Mean of `SIC_d(c)` over d = t+1 … t+7** — a *weekly-average* quantity, not a daily value and not an anomaly. Defined when ≥ 5 of the 7 days are observed for that cell; otherwise the cell is excluded (never filled). | % |
| `SIE_t` | Σ area(c) over ocean cells with `Y_t(c) ≥ 15 %` (forecast: same on the predicted field) | km² |
| `SIA_t` | Σ area(c) · Y_t(c)/100 over ocean cells with `Y_t(c) ≥ 15 %` | km² |

Extent counts whole cells above the threshold; area weights each counted cell by its concentration, so SIA ≤ SIE always.
Both are computed from the **7-day-mean field**, which differs slightly from the mean of seven daily extents (documented in the evaluation).
The 15 % threshold is the community convention (NSIDC Sea Ice Index, OSI SAF); its limitation is that it is insensitive to changes
within the pack and sensitive to noise at low concentrations near the edge.

## 3. Timing and data availability (leakage control)

| Element | Definition |
|---|---|
| Issue time *t* | End of day *t* (23:59:59 UTC). |
| Inputs | Only observations dated ≤ *t*: daily SIC days t−55…t, CDR uncertainty t−6…t, atmosphere t−6…t. |
| Prediction window | Days t+1 … t+7 (horizon 7 days). |
| Issue cadence | Every 7 days from 1979-01-07 (non-overlapping target windows). |
| Latency assumption | The hindcast assumes day-*t* data are available at issue time. Operationally the CDR's near-real-time extension (ICDR, AMSR2 "am2" files) lags by ~1 day; the inference pipeline reports the actual age of the latest observation and warns when it is older than *t*. |

Persistence input = the latest valid daily value no older than 3 days (per cell); cells without any are passed to the model as missing.

## 4. Spatial domain, grid and masks
* Grid: NSIDC Polar Stereographic South 25 km (EPSG:3412), 332 × 316 cells, **kept unchanged** (labels are never regridded).
* Ocean mask: cells whose CDR `surface_type_mask` is *ocean* (50) on ≥ 99 % of days. Lakes (75), coast (200) and land (250) are excluded;
  missing values are never treated as 0 %.
* Cell area: exact, from the areal scale factor of the polar-stereographic projection (pyproj), 444–664 km² per cell
  (625 km² at the 70°S true-scale latitude).
* Atmospheric predictors are interpolated *to* the SIC grid (bilinear, continuous fields only); masks are never interpolated.

## 5. Physical constraints
* Forecast concentrations are clipped to [0, 100] %; the number of pre-clip violations is recorded per evaluation.
* The model predicts the **change relative to persistence** (residual target), which keeps forecasts anchored to the observed state;
  an absolute-target variant is trained as an ablation.

## 6. Uncertainty and quality information preserved
* The CDR's per-cell source standard deviation (`cdr_seaice_conc_stdev`) is carried as feature `unc_w1`.
* QA, temporal- and spatial-interpolation flags are summarised per day in the data-quality report (SMMR-era every-other-day interpolation, gaps).
* Prediction intervals (quantile regression) are reported **only if** their empirical coverage on the test period is within 5 pp of nominal.

## 7. Evaluation regions
* `all`: every ocean cell with a valid target (dominated by open water far from the ice → flattering numbers).
* `seasonal_ice_zone` (primary): ocean cells whose *training-period* climatology reaches 15 % on at least one day of the year.
* `ice_edge_band`: cells within 3 cells (~75 km) of both an observed ≥15 % and an observed <15 % cell.
* Five NSIDC sectors (Weddell 60°W–20°E, Indian 20–90°E, West Pacific 90–160°E, Ross 160°E–130°W, Bellingshausen–Amundsen 130–60°W),
  four austral seasons, three ice conditions (open water < 15 %, marginal 15–80 %, pack ≥ 80 %).
