# Data Sources — selection rationale (Phase 2)

File-level provenance (URLs, retrieval times, MD5): `DATA_SOURCES_AND_PROVENANCE.md`. Configuration: `configs/data_sources.yaml`.

## Primary sea-ice concentration dataset — decision

| Candidate | Algorithm / sensor | Period | Grid | Access | Decision |
|---|---|---|---|---|---|
| **NOAA/NSIDC SIC CDR v6 (G02202)** | NASA Team + Bootstrap combination; SMMR, SSM/I, SSMIS; AMSR2 ICDR | 1978-10 → 2026-11 (daily) | 25 km EPSG:3412 | Public HTTPS | **Selected** — longest consistent daily record, documented uncertainty and QA flags, explicit masks, no login. |
| NSIDC-0803 AMSR2 daily SIC | AMSR2 | 2012 → | 12.5 / 25 km | Earthdata login | Rejected as primary (too short); candidate for a higher-resolution follow-up. |
| NSIDC Sea Ice Index (G02135) | NASA Team (NSIDC-0051/0081) | 1978 → | 25 km | Public | Used as **independent extent comparison** (daily CSV). Its gridded fields are the same sensor family, so not independent for SIC. |
| CMEMS OSI SAF SIC CDR (…011_009) | OSI SAF hybrid algorithm | 1978 → | 25 km EASE2 | Copernicus Marine account | Preferred **independent gridded** comparison; not acquired (account). |
| CMEMS Antarctic extent OMI / reanalysis | OSI SAF / reanalysis | monthly | scalar | Copernicus account (observation OMI file already local) | Extent comparison only. |

Products are **not** mixed: labels and SIC predictors come only from G02202 v6. Comparison products differ in algorithm, land mask and
grid (G02135 vs CDR v6 differences are quantified in DATA_QUALITY_REPORT.md).

## Atmospheric predictors — decision

ERA5 (preferred; `EXTERNAL APIs/API.py`, `PRESSUREAPI.py`) requires a CDS token that is not configured, so NCEP/NCAR Reanalysis 1 daily
means (public OPeNDAP, 2.5°) are used as an **interim** source. Selected variables and rationale:

| Variable | Physical rationale for 1-week SIC change | Used |
|---|---|---|
| Near-surface air temperature (`air.sig995`) | Thermodynamic growth/melt, especially at the margin | yes (+ anomaly) |
| 10 m-like winds (`uwnd`, `vwnd` sig995) | Wind-driven drift; equatorward (v > 0) winds spread the pack, poleward winds compact it | yes (+ speed) |
| Sea-level pressure (`slp`) | Large-scale circulation (e.g. Amundsen Sea Low) | yes (+ anomaly) |
| SST, cloud cover, precipitation, geopotential, humidity, vertical velocity | Plausible but second order at 1-week lead or largely captured by the SIC history / air temperature; also not all available at sea-level from R1 dailies | not in v1 |

Optional ocean / drift / thickness predictors (CMEMS, ORAS5, GLORYS) all require accounts and are listed in NEXT_STEPS.md.
