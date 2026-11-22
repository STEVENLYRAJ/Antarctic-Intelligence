# Copernicus Marine (CMEMS): Antarctic dataset inventory for ML-01…ML-04 (for approval)

Checked on 2026-11-14 with copernicusmarine toolbox 2.5.1.

**Nothing has been downloaded** except one day of OSI-SAF ice concentration, read into memory as an authentication test and not saved.

**Credentials:**

- `%USERPROFILE%\.copernicusmarine\.copernicusmarine-credentials` exists.
- `copernicusmarine.login(check_credentials_valid=True)` returns **True**.
- An authenticated read of `OSISAF-GLO-SEAICE_CONC_TIMESERIES-SH-LA-OBS` for 2020-09-15, 50–90°S, returned 1 × 200 × 1,800 values (%, max 100).
- No credential value was displayed.

**Formats:**

- `subset` streams from the ARCO (Zarr) service and writes NetCDF-4.
- `get` returns the provider's original NetCDF files.

**Size estimates:** these are for a subset to 50–90°S and the listed variables. "Raw" means uncompressed float32; NetCDF on disk is typically 25–50 % of that, because land and open-ocean cells are NaN or zero.

## 1. Sea ice: observations

| Product (provider) | Dataset ID | Variables | Grid | Time coverage | Est. size (50–90°S) | Relevance |
|---|---|---|---|---|---|---|
| SEAICE_GLO_SEAICE_L4_REP_OBSERVATIONS_011_009 (MET Norway / EUMETSAT OSI SAF) | `OSISAF-GLO-SEAICE_CONC_TIMESERIES-SH-LA-OBS` (OSI-450 CDR) | ice_conc, algorithm/smearing/total uncertainty, status_flag, raw_ice_conc_values | 0.2° (ARCO regridding of the 25 km EASE2 original) | 1978-10-25 to 2020-12-31 (13,675 days) | ice_conc + total uncertainty: raw ≈ 40 GB → **≈ 8–12 GB** | **ML-01/ML-04:** independent second SIC CDR (different algorithm from NSIDC CDR v6) |
| same | `OSISAF-GLO-SEAICE_CONC_CONT_TIMESERIES-SH-LA-OBS` (OSI-430 ICDR) | same | 0.25° × 0.3° | 2021-01-01 to 2025-09-29 | ≈ 1 GB | Continuation of the CDR |
| same | `osisaf_obs-si_glo_phy_sic-south_my_amsr_cdr_P1D-m` / `_icdr_P1D-m` (AMSR CDR) | same | 0.2° | 2002-06-01 to 2020-12-31 / 2021-01-01 to 2026-10-29 | ≈ 6 GB / ≈ 2 GB | Higher-resolution AMSR record (optional) |
| SEAICE_GLO_SEAICE_L4_NRT_OBSERVATIONS_011_001 (MET Norway) | `osisaf_obs-si_glo_phy-sic-south_nrt_amsr2_l4_P1D-m`, `..._ssmis_...`, `siedge_nrt_sh`, `sitype_nrt_sh`, `sidrift_nrt_sh` | ice_conc, ice_edge, ice_type, drift | 0.1° (drift 0.5°) | 2024-09/11 to 2026-11-13 | ≈ 1 GB per variable | NRT; overlaps NSIDC (low added value) |
| SEAICE_ANT_PHY_AUTO_L3_NRT_011_012 (DMI) | `cmems_obs-si_ant_phy_nrt_l3-1km_P1D` (DMI-ASIP) | ice_concentration, confidence, acq_time | 1 km (0.0125° × 0.025°), 45–86°S | 2023-02-02 to 2026-11-11 | ≈ 20–40 MB per day → all days ≈ 30–50 GB; **ML-03 test dates only (≈ 100 days) ≈ 2–4 GB** | **ML-03:** automated SAR+AMSR2 CNN product. Comparison only; not independent truth |
| ANTARCTIC_OMI_SI_extent_obs (MET Norway) | `antarctic_omi_si_extent_obs` | siextent, monthly climatology mean/std | Domain index (time series) | 1979-01 to 2024-12 (monthly) | < 1 MB | Extent cross-check |
| ANTARCTIC_OMI_SI_extent (Mercator) | `antarctic_omi_si_extent` | siextents from 4 reanalyses (cglo, glor, oras, mean, std) | Time series | 1993-01 to 2023-12 | < 1 MB | Model-based extent |

## 2. Sea-ice thickness and drift

| Product (provider) | Dataset ID | Variables | Grid | Coverage | Est. size | Relevance |
|---|---|---|---|---|---|---|
| SEAICE_GLO_PHY_L4_NRT_011_014 (FMI; ESA SMOS + CryoSat-2) | `esa_obs-si_ant_phy-sit_nrt_l4-multi_P1D-m` | **sea_ice_thickness** + uncertainty, sea_ice_concentration, flags | 0.1° | **2025-04-18 to 2026-10-12** (short) | ≈ 1–2 GB | The only **observed** Antarctic ice thickness. Too short for baselines; useful for 2025–26 context |
| SEAICE_ANT_PHY_L3_MY_011_018 (IFREMER) | `cmems_obs-si_ant_physic_my_drift-amsr_P3D` (also P2D) | eastward/northward sea-ice velocity | 0.25° | 2003-04-01 to 2026-10-31 | ≈ 2–4 GB | Ice dynamics context (ML-01 feature candidate) |
| same | `..._drift-cfosat(-ssmi-merged)_P2D/P3D/P30D` | velocities | 0.5° | 2020-05 to 2022-10 | < 0.5 GB | Short record (skip) |
| SEAICE_GLO_PHY_L4_MY_011_020 (DTU Space) | `cmems_obs-si_glo_phy-drift-south_my_l4_P1D-m` (Sentinel-1 SAR drift) | dX/dY mean/std, divergence, QoS | 0.1° | 2014-10-06 to 2026-11-01 | ≈ 10–20 GB | High-resolution drift (optional; large) |
| SEAICE_GLO_SEAICE_L4_NRT_OBSERVATIONS_011_006 (DTU Space) | `cmems_sat-si_glo_drift_nrt_south_d` | same | 0.1° | 2024-06-02 to 2026-11-13 | ≈ 3 GB | NRT version (skip) |

## 3. Ocean: reanalyses and observations

| Product (provider) | Dataset ID | Variables | Grid | Coverage | Est. size (50–80°S) | Relevance |
|---|---|---|---|---|---|---|
| GLOBAL_MULTIYEAR_PHY_001_030 (Mercator, GLORYS12) | `cmems_mod_glo_phy_my_0.083deg_P1M-m` | **sithick**, siconc, usi/vsi, thetao, so, uo/vo (50 depths), mlotst, bottomT, zos | 1/12° (≈ 8 km); **southern limit 80°S** | 1993-01 to 2026-08 (404 months) | Surface and ice fields (siconc, sithick, thetao/so at 0.5 m, mlotst): raw ≈ 12 GB → **≈ 4–6 GB** | **ML-04 ocean side** (SST, mixed layer) and **ice thickness** (model) |
| same | `cmems_mod_glo_phy_my_0.083deg_P1D-m` | same | 1/12° | 1993-01-01 to 2026-09-22 | ≈ 30× the monthly size (≈ 150 GB): **not recommended** | — |
| same | `..._static`, `..._climatology_P1M-m` | bathymetry, mask; 1993–2016 climatology | 1/12° | — | < 1 GB | Mask and bathymetry (small) |
| GLOBAL_MULTIYEAR_PHY_ENS_001_031 (CMCC) | `cmems_mod_glo_phy-mnstd_my_0.25deg_P1M-m` | siconc/sithick/thetao/so/mlotst **ensemble mean and std** (GLORYS, ORAS, C-GLORS) | 0.25° | 1993-01 to 2025-12 | Surface and ice: ≈ 1 GB | **Structural uncertainty** of model ice thickness and SST (recommended over a single reanalysis for spread) |
| GLOBAL_ANALYSISFORECAST_PHY_001_024 (Mercator) | `cmems_mod_glo_phy_anfc_0.083deg_P1M-m` / `P1D-m` (ice: siconc, sithick, sisnthick, siage, sialb, ist), `...thetao...`, `...sst-anomaly...` | Ice, snow on ice, SST anomaly | 1/12° | 2022-06 to 2026-11-23 (includes about 10 days of forecast) | Monthly ice, surface only: ≈ 0.5 GB | Recent and near-real-time ocean and ice state, beyond the GLORYS end (2026-09) |
| MULTIOBS_GLO_PHY_TSUV_3D_MYNRT_015_012 (CLS) | `cmems_obs-mob_glo_phy_my_0.125deg_P1M-m` (+ `nrt`) | Observation-based to/so (3-D), geostrophic currents, MLD | 0.125°, to 82°S | 1993-01 to 2025-05 (my); 2024-08 to 2026-10 (nrt) | Surface only: ≈ 1 GB | **Observation-based** ocean temperature (independent of models) |
| SST_GLO_SST_L4_REP_OBSERVATIONS_010_011 (Met Office, OSTIA) | `METOFFICE-GLO-SST-L4-REP-OBS-SST` | analysed_sst, analysis_error, sea_ice_fraction, mask | 0.05° | 1981-10-01 to 2026-06-30 (daily) | **≈ 370 GB raw** (daily 0.05°, 50–90°S): **not recommended** | ERA5 SST (approved E1) already uses OSTIA from 2007 onward, so OSTIA largely duplicates it |
| SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001 (Met Office) | `METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2` | same | 0.05° | 2024-01-17 to 2026-11-13 | ≈ 20 GB raw | Skip |

## 4. Overlap with data already in the repository (avoid duplicates)

| Existing AETHENTRA data | Overlapping CMEMS product | Overlap type | Recommendation |
|---|---|---|---|
| NOAA/NSIDC SIC CDR v6, daily 1979 to 2026-11-01 (`data/raw/aethentra/nsidc_g02202_v6`, ML-01 cube) | OSI-SAF SIC CDR/ICDR (011_009) | Same variable and sensors, **different algorithm and producer** | Download **once**, for cross-validation only (independent algorithm). Not a duplicate |
| same | OSI-SAF NRT SIC (011_001) | Same variable, NRT | **Skip** (redundant) |
| NSIDC Sea Ice Index extent (G02135) | ANTARCTIC_OMI_SI_extent_obs | Extent from OSI-SAF | Tiny; optional |
| `DATAS/dmi_asip_seaice_mosaic_ant_20230202.nc` (one day) | DMI-ASIP 011_012 | Identical product | Skip 2023-02-02; take only ML-03 test-scene dates |
| ERA5 `siconc` and SST (downloading; ERA5 SST is OSTIA-based from 2007) | OSTIA 010_011 / 010_001 | Largely the same source after 2007 | **Skip OSTIA** |
| ML-03 Sentinel-1 scenes (3.6 GB) | DTU SAR drift (011_020) | Derived from Sentinel-1, but a different quantity (motion) | No duplicate; optional |
| None (no ice thickness, ocean temperature or drift data exist) | GLORYS12, ENS 001_031, SMOS/CryoSat thickness, MULTIOBS, IFREMER drift | New information | Candidates |

## 5. Recommended minimal set (awaiting approval)

| # | Dataset | Variables / subset | Est. disk | Purpose |
|---|---|---|---|---|
| **C1** | `OSISAF-GLO-SEAICE_CONC_TIMESERIES-SH-LA-OBS` + `..._CONT_TIMESERIES-SH-LA-OBS` | ice_conc, total_standard_uncertainty, status_flag; 50–90°S; 1978-10 to 2025-09 | ≈ 9–13 GB | Independent SIC validation (ML-01, ML-04) |
| **C2** | `cmems_mod_glo_phy_my_0.083deg_P1M-m` (GLORYS12 monthly) | siconc, sithick, thetao and so at the top level, mlotst; 50–80°S; 1993-01 to 2026-08 | ≈ 4–6 GB | Ocean and ice-thickness variables for ML-04 compound events |
| **C3** | `cmems_mod_glo_phy-mnstd_my_0.25deg_P1M-m` | siconc/sithick/thetao mean and std; 50–80°S; 1993–2025 | ≈ 1 GB | Reanalysis spread (uncertainty) |
| **C4** | `cmems_obs-si_ant_phy_nrt_l3-1km_P1D` (DMI-ASIP) | ice_concentration, confidence; ML-03 test chart dates only (≈ 100 days, 2025-01 to 2026-10) | ≈ 2–4 GB | ML-03 comparison (pseudo-reference) |
| C5 (optional) | `cmems_obs-si_ant_physic_my_drift-amsr_P3D` | velocities, 2003–2026 | ≈ 2–4 GB | Ice drift context |
| C6 (optional) | `esa_obs-si_ant_phy-sit_nrt_l4-multi_P1D-m` | thickness + uncertainty, 2025-04 to 2026-10 | ≈ 1–2 GB | Observed thickness, recent only |
| C7 (optional) | `cmems_obs-mob_glo_phy_my_0.125deg_P1M-m` | to and so at the surface, 1993–2025 | ≈ 1 GB | Observation-based SST/salinity |

**Total:** C1–C4 ≈ 16–24 GB; with all options ≈ 21–31 GB. H: has about 176 GB free before the ERA5 and MERRA-2 downloads now running (up to about 60 GB and about 6 GB).

**Not recommended:**

- GLORYS daily (≈ 150 GB);
- OSTIA (≈ 370 GB, and duplicates ERA5 SST);
- the full DMI-ASIP archive (30–50 GB);
- OSI-SAF NRT and the DTU NRT drift (redundant).
