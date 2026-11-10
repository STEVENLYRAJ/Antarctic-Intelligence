# AETHENTRA ML-02 — Preprocessing (Phase 3)

Code: `src/aethentra/temperature/preprocessing/cube.py` · config `configs/ml02/preprocessing.yaml` · run `python scripts/ml02/preprocess.py --source ncep_r1|era5`.

## Target grid
* The ML-01 NSIDC Sea Ice Polar Stereographic South grid (EPSG:3412, 25 km, 332 × 316), restricted to cells with latitude ≤ 60°S:
  **55,512 cells** (21,691 land / ice shelf, 33,821 ocean). Near-equal-area (cell areas from the exact projection scale factor),
  no polar oversampling, and identical to the sea-ice grid so ML-01 observations can be used as predictors without regridding.
* ERA5 (0.25° ≈ 28 km meridionally) is therefore not materially degraded; NCEP R1 (~1.9°) is interpolated **up** to 25 km
  (the interpolated field carries no extra information — documented).

## Spatial processing
* **Bilinear interpolation** for continuous fields, in latitude × periodic longitude (seam at 0/360° handled; descending
  latitude handled; target latitudes beyond the source grid clamped to the edge row — affects only the pole cells for the
  Gaussian grid). Unit-tested against an analytic linear field.
* **Masks are never interpolated**: land/ocean comes from the CDR surface-type mask already on the target grid (ML-01
  static ocean mask). Ice shelves count as land.
* **Elevation**: source orography (NCEP `hgt.sfc`, or ERA5 surface geopotential / 9.80665) interpolated, clipped ≥ 0, 0 over ocean.
* **Distance to coast**: Euclidean distance transform on the 25 km mask (km). Coastal land = ≤ 100 km from the ocean; inland = > 100 km.
* **Regions** (land cells): Antarctic Peninsula (lon 80–55°W, lat ≥ 75°S); West Antarctica (remaining land 180–30°W);
  East Antarctica (remaining land 30°W–180°). Longitude-based, an approximation of the Transantarctic-Mountains divide (documented limitation).

## Temporal processing
* Inputs are daily means (ERA5: mean of 24 hourly values of the UTC day; NCEP R1: PSL daily means of 4 × 6-hourly).
* Daily calendar 1979-01-01 … 2025-12-31 (17,167 days). Duplicate timestamps dropped (count recorded); days outside the calendar ignored.
* Weekly aggregation happens in the label / feature code (never in the cube), with the issue time explicit.

## Units and quality control
* K → °C only when the file declares Kelvin (`K`, `degK`); Pa → hPa only when declared Pa/Pascals; unknown units raise an error (unit-tested).
* Two thresholds per variable: physically **impossible** → set missing; **doubtful** (outside the observed record, e.g. T2m < −89.2 °C,
  extrapolated MSL > 1090 hPa) → counted and kept (reanalysis values are not altered).
* Domain-mean day-to-day T2m jump > 8 °C is flagged (interim source: 1997-08-07 → excluded from training issue dates).
* Storage: int16 memory-mapped arrays (n_days × n_cells) with per-variable scale (0.01 °C, 0.1 hPa, 0.01 m s⁻¹); fill −32768.
* Outputs: `data/interim/ml02/<source>/{grid.npz, <var>.npy, calendar.csv, daily_qa.csv, cube_meta.json}`; `cube_meta.json` lists every
  input file with its MD5, the unit conversions applied, and the QA counts.
