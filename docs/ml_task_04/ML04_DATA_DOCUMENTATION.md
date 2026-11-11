# ML-04 Data Documentation

The full dataset inventory, including provenance, coverage and licences, is in `ML04_DATA_INVENTORY.csv`. Every raw file has a `.provenance.json` sidecar recording:

- source URL;
- retrieval time (UTC);
- MD5 checksum;
- subset applied;
- units.

## Sources

| Variable (ML-04 name) | Source field | Native grid | Conversion | Data tier |
|---|---|---|---|---|
| `t2m` | NCEP R1 `air.sig995` (σ = 0.995, ~40 m above the surface) | 2.5° | K → °C | A |
| `slp` | NCEP R1 `slp` | 2.5° | Pa → hPa | A (B on the high plateau, see below) |
| `wspd` | NCEP R1 `uwnd`, `vwnd` (σ 0.995) | 2.5° | Speed of the daily-mean vector | B |
| `rhum` | NCEP R1 `rhum.sig995` | 2.5° | % (relative to water) | B |
| `prate` | NCEP R1 `prate.sfc` (forecast field) | T62 Gaussian | kg m⁻² s⁻¹ × 86400 → mm day⁻¹ | C |
| `tcdc` | NCEP R1 `tcdc.eatm` (forecast field) | T62 Gaussian | % | C |
| `z500` | NCEP R1 `hgt`, 500 hPa | 2.5° | m | A |
| `sic` | NOAA/NSIDC CDR v6 `cdr_seaice_conc` | 25 km EPSG:3412 | % | A |

**Data tiers:**

- **A:** strongly constrained by assimilated observations or satellites.
- **B:** partly constrained.
- **C:** model forecast field with large known errors over Antarctica.

The tier is attached to every stored anomaly record.

**Coverage, as verified in `data/processed/ml04/quality_report.json`:**

- All NCEP variables: 1979-01-01 to **2026-03-17**. That is where NOAA PSL's R1 daily files end.
- SIC: 1979-01-01 to 2026-11-01.

**Gaps:**

- **SIC:** a 2.5° cell-day counts as missing only when the whole grid has no data. 69 such days fall inside the record. They come from the SMMR failure in August 1984, missing days in December 1986, and the SSM/I transition gap from December 1987 to January 1988. The months 1984-08, 1986-12, 1987-12 and 1988-01 therefore have no monthly SIC. All four are in the training period.
- **tcdc:** 1 missing day.

## Preprocessing (Phase 2)

- **Grid:**
  - NCEP 2.5° rows from 50° S to 87.5° S, 144 longitudes. The 90° S row is dropped because it holds 144 copies of the pole.
  - Gaussian fields are linearly interpolated in latitude, then periodically in longitude.
  - For SIC, valid 25 km ocean pixels are averaged, area-weighted, into the 2.5° cell that contains their centre. A cell needs ≥ 25 % ocean coverage. Pixel-centre assignment means the coverage fraction can exceed 1 (up to 1.2); it is used only as a threshold.
- **Time:**
  - Daily UTC dates.
  - Monthly means need ≥ 80 % valid days.
  - Leap days share the Feb 28 climatology.
- **Data-quality findings:**
  1. The PSL 2026 `uwnd` file repeats 2025 dates, with all values NaN, after 2026-03-17. A guard now writes only rows belonging to the file's own year.
  2. Sea-level pressure reaches up to 1123 hPa over the high East Antarctic plateau. This is a known artefact of reducing pressure to sea level from about 3 km elevation, not a data error. The plausibility bound was widened to 1130 hPa, and SLP anomalies on the plateau should be read with caution.
  3. The 2026 `vwnd` and `uwnd` files differ in length; wind speed uses their common dates.
- **Independent extent check:** daily total extent computed from the CDR, compared with the NSIDC Sea Ice Index v4 file on disk.

## Baselines (Phase 3)

| Name | Years | Use |
|---|---|---|
| reporting | 1991–2020 (fixed, WMO normal) | NetCDF anomaly cube, maps, seasonal summaries, extent anomalies, daily spells, univariate database records |
| model | 1981–2010 (fixed, inside the training period) | All ML features, severity thresholds and evaluations |

**Statistics stored** (per cell and calendar month, plus per day of year with a ±15-day window):

- mean;
- standard deviation, with a per-variable floor;
- median;
- MAD × 1.4826;
- P05, P10, P90, P95;
- minimum and maximum;
- the sorted sample.

**Percentile ranks** use the Weibull plotting position rank/(n+1). With n = 30, each tail beyond P05/P95 rests on only one or two values.

## Outputs

| Path | Content |
|---|---|
| `outputs/ml04/anomalies_monthly_1991-2020.nc` | Monthly value, anomaly, z, percentile and severity for 9 variables, 1979-01 to 2026-11 (CF attributes, EPSG:4326) |
| `outputs/ml04/anomaly_maps/anom_YYYY-MM/` | GeoTIFF layers (native 2.5° EPSG:4326 plus an EPSG:3412 display copy), native 25 km SIC anomaly, manifest and summary JSON |
| `outputs/ml04/summaries/*.csv` | Monthly summary, seasonal summary, daily extent anomalies, daily warm/cold spells |
| `data/processed/ml04/features/*.parquet` | Feature table, scores, explained flagged samples, clusters, events, compound co-occurrence |
| `data/processed/ml04/ml04.sqlite` | Models, datasets, anomaly records, processing runs |

Raw and derived data are excluded from Git by the existing `.gitignore` rules for `data/`, `outputs/` and `models/`.
