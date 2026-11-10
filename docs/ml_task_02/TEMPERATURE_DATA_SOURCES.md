# AETHENTRA ML-02 — Temperature Data Sources

Status per source: **ACQUIRED** (downloaded, checksummed, validated) · **PENDING** (code ready, needs credentials) · **NOT USED**.

| Role | Dataset | Access | Status |
|---|---|---|---|
| Primary gridded truth + predictors (designated) | ERA5 post-processed **daily statistics** on single levels (t2m, msl, u10, v10, d2m, tcc) and pressure levels (z500, t850), 0.25°, daily mean of 24 hourly values (UTC day), area 55–90°S; invariants lsm, z | Copernicus CDS API (`cdsapi`), free registration + ERA5 licence; key in `%USERPROFILE%\.cdsapirc` | **PENDING** — no CDS key on this machine at run time |
| Interim gridded truth + predictors (used for all results in this release) | NCEP/NCAR Reanalysis 1 daily means: **2 m air temperature** (T62 Gaussian, ~1.9°; `surface_gauss/air.2m.gauss.YYYY.nc`, subset ≤ 50°S); sea-level pressure + σ=0.995 u/v wind (2.5°, ML-01 files, ≤ 35°S); surface height `hgt.sfc.gauss` | NOAA PSL THREDDS OPeNDAP, anonymous | **ACQUIRED** 1979-01-01 … 2026-03-17 (48 + 3×48 files, MD5 recorded in `.provenance.json`) |
| Independent validation (primary) | Turner et al. update: *Daily Temperature and Temperature Anomaly Data at Staffed Antarctic Stations*, Zenodo record 17164992 (2025-09-20, CC-BY-4.0), 16 stations, daily Tmean from 6-hourly SYNOP | Zenodo API, anonymous | **ACQUIRED** 32 CSV, MD5 verified against the record; coverage to 2022 |
| Independent validation (supplementary) | NOAA GHCN-Daily TAVG, 45 stations south of 60°S with TAVG spanning ≤1990 … ≥2020 (31 used: the 14 GHCN stations that are the same sites as Zenodo stations are dropped in favour of the Zenodo series; `outputs/ml02/reports/station_inventory.csv`) | NCEI HTTPS, anonymous | **ACQUIRED** 45 CSV + station/inventory lists |
| Optional predictor | NOAA/NSIDC SIC CDR v6 (ML-01 cube, observations only, never ML-01 forecasts) | local (ML-01) | **ACQUIRED** (ML-01) |
| Not used | SCAR READER (monthly means only — not usable for weekly validation) | — | NOT USED |

## Why NCEP R1 is only an interim substitute

* Coarser (~1.9° vs 0.25°) and older assimilation system; documented warm/cold biases over the Antarctic plateau
  (the 2 m temperature reaches −102 °C, below the −89.2 °C observed record — flagged, not removed).
* A boundary-condition artefact on 1997-08-07 (ocean cells +12.7 °C mean, up to +43 °C in one day) — training issue dates
  overlapping 1997-08-06…10 are excluded.
* Winds are σ=0.995 (~40 m), not 10 m; dewpoint, cloud, z500 and t850 are not used in the interim configuration.
* **All ML-02 metrics in this release are skill against NCEP R1, not ERA5.** Station comparisons are the only
  independent check.

## Switching to ERA5 (no code change)

```bash
# once %USERPROFILE%\.cdsapirc exists and the ERA5 licences are accepted on the CDS website
python scripts/ml02/download_data.py --era5 --workers 4      # t2m first, newest years first; resumable
# edit configs/ml02/data_sources.yaml: primary: era5
python scripts/ml02/preprocess.py --source era5
python scripts/ml02/validate_data.py --source era5
bash scripts/ml02/run_all.sh era5                            # NEW test evaluation; archive the NCEP results first
```

Licences / citation: ERA5 — Hersbach et al. (2020), C3S CDS, Copernicus licence. NCEP R1 — Kalnay et al. (1996), NOAA PSL.
Stations — Turner et al. (2020) Int. J. Climatol. 40; Zenodo 17164992 (CC-BY-4.0); GHCN-Daily — Menne et al. (2012), doi:10.7289/V5D21VHZ.
