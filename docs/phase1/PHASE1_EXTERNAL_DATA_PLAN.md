# Phase 1 External Data Plan: ERA5, MERRA-2, Copernicus Marine (for approval)

Checked on 2026-11-14.

**Credential handling.** No credential value was read out, printed or stored. Checks used only:

- whether the file exists;
- whether it parses;
- whether the login and password fields are present.

Every test file is under `data/raw/<source>/_test/`, which is git-ignored.

## 1. Authentication status

| Service | Configuration | Verified | Evidence |
|---|---|---|---|
| Copernicus CDS (ERA5) | `%USERPROFILE%\.cdsapirc` | **Yes** | Test download OK; ERA5 licence accepted; bulk download running (started 2026-11-14 with your approval) |
| NASA Earthdata (MERRA-2) | `%USERPROFILE%\_netrc` (entry for `urs.earthdata.nasa.gov`, login and password present) | **Yes** | HTTPS request redirected through the Earthdata login and returned HDF5 data; one monthly MERRA-2 file downloaded and validated (below). GES DISC authorisation works |
| Copernicus Marine | `%USERPROFILE%\.copernicusmarine\` | **No** | `copernicusmarine.login(check_credentials_valid=True)` returns False. The folder holds one 192-byte file named `.copernicusmarine`, which is not a toolbox credentials file (no `[credentials]` section, no username/password entries). The toolbox stores credentials as `.copernicusmarine-credentials` |

**Fix for Copernicus Marine** (in your own terminal, not in chat):

1. Run `copernicusmarine login`, enter your username and password, and answer `y` if it asks to overwrite.
2. Then run `copernicusmarine login --check-credentials-valid`. It should report valid credentials.

Catalogue browsing works without login, so the product details below are verified. Data subsetting needs the login.

## 2. MERRA-2 test result (real data)

- **Test file:** `MERRA2_400.tavgM_2d_slv_Nx.202001.nc4` (M2TMNXSLV v5.12.4, monthly mean single-level diagnostics), January 2020, downloaded in full: 78.8 MB in 36 s.
- **Grid:** global, 361 × 576 (0.5° latitude × 0.625° longitude); latitude −90…90; longitude −180…179.375.
- **Variables:** 94, including:
  - T2M, T2MDEW, QV2M, SLP, PS, U10M, V10M, TS;
  - H/T/U/V/Q at 250, 500 and 850 hPa;
  - **OMEGA500** (vertical velocity, Pa s⁻¹);
  - TQV and the cloud-top fields.
- **Validation:** T2M and SLP south of 50°S pass the content check.
- **Coverage (verified by HTTP range requests):** 1980-01 to **2026-09**. 2026-10 is not yet published (404).

**Other MERRA-2 collections** (one file each, size from HTTP range requests):

| Collection | File size |
|---|---|
| M2TMNXFLX (monthly fluxes: PRECTOT, PRECSNO) | 77 MB per month |
| M2SDNXSLV (daily T2M mean/min/max) | 1.7 MB per day |
| M2T1NXSLV (hourly single-level) | 420 MB per day |

## 3. Copernicus Marine: relevant products (catalogue, verified)

| Product / dataset | Variables | Resolution | Time coverage | AETHENTRA use |
|---|---|---|---|---|
| SEAICE_GLO_SEAICE_L4_REP_OBSERVATIONS_011_009 (OSI-SAF SIC CDR/ICDR), SH | ice_conc + uncertainties, status_flag | 25 km (0.2–0.25° regular in the ARCO service) | CDR from 1978 (catalogue); the continuous ICDR part listed here runs 2021-01-01 to 2025-09-29 | **Independent second SIC record** (different algorithm from NSIDC), for ML-01/ML-04 cross-validation |
| SEAICE_ANT_PHY_AUTO_L3_NRT_011_012 (DMI-ASIP) | ice_concentration, confidence, acq_time | 1 km (0.0125° × 0.025°) | 2023-02-02 to 2026-11-11, daily | ML-03 comparison with an automated product (pseudo-reference, not truth). One day is already on disk (`DATAS/dmi_asip_seaice_mosaic_ant_20230202.nc`) |
| SEAICE_ANT_PHY_L3_MY_011_018, `drift-amsr_P3D` | eastward/northward sea-ice velocity | 0.25° | 2003-04-01 to 2026-10-31 | Sea-ice drift context (optional) |
| GLOBAL_MULTIYEAR_PHY_001_030 (GLORYS12 reanalysis), P1M / P1D | **sithick**, siconc, thetao (SST), so, uo/vo, usi/vsi, mlotst, zos | 1/12° (0.083°), down to 80°S | Daily 1993-01-01 to 2026-09-22; monthly over the same span (catalogue) | **Sea-ice thickness and ocean temperature** (the ocean side of ML-04 compound events) |
| SST_GLO_SST_L4_REP_OBSERVATIONS_010_011 (OSTIA reprocessed) | analysed_sst, sea_ice_fraction | 0.05° daily | 1981-10-01 to 2026-06-30 | SST. **Not recommended:** about 370 GB for 50–90°S daily. Use GLORYS thetao or ERA5 SST instead |
| SEAICE_GLO_SEAICE_L4_NRT_OBSERVATIONS_011_001, SH AMSR2/SSMIS | ice_conc | 0.1° | 2024-09-28 to 2026-11-13 | Near-real-time SIC (optional) |

## 4. What already exists (no duplicate downloads)

| Already on disk | Covers | Do not re-download |
|---|---|---|
| NSIDC SIC CDR v6 daily 1979 to 2026-11-01 (ML-01 cube) | SIC | NSIDC SIC (OSI-SAF is a *different* record, so it is not a duplicate) |
| NCEP R1 (8 variables) to 2026-03-17 | Atmosphere (interim) | — |
| ERA5 (running): monthly means for 11 single-level and 4×2 pressure-level variables; daily (6-hourly averaged) 1979–2026 | Atmosphere, including snow depth, surface pressure, vertical velocity and PV | MERRA-2 would be a second reanalysis, not a duplicate; recommended only as an independent check |
| DMI-ASIP 2023-02-02 (one day) | — | That day |
| GHCN-D / Zenodo stations | In-situ temperature | — |

## 5. Proposed downloads (awaiting your approval)

Downloads are subset south of 50°S and to the variables listed. Sizes are estimates.

| # | Source | What | Volume on disk | Time | Priority |
|---|---|---|---|---|---|
| M1 | MERRA-2 M2TMNXSLV | Monthly 1980-01 to 2026-09 (561 files). Each global file is streamed, subset to ≤ 50°S and about 20 variables (T2M, T2MDEW, QV2M, SLP, PS, U10M, V10M, TS, OMEGA500, H500, T500, T850, U/V500, U/V850, TQV), then the global file is discarded | ≈ 1 GB (44 GB streamed) | ≈ 2 h with 4 parallel connections | **High:** independent reanalysis check of NCEP/ERA5 trends (Phase 1 audit §3.6) |
| M2 | MERRA-2 M2TMNXFLX | Monthly PRECTOT and PRECSNO, same approach | ≈ 0.1 GB (43 GB streamed) | ≈ 2 h | Medium |
| M3 | MERRA-2 M2SDNXSLV | Daily T2M mean/min/max 1980–2026 (about 17,000 files) | ≈ 5 GB subset | ≈ 6–10 h | Low (optional) |
| C1 | OSI-SAF SIC CDR (SH) | Daily 1979–2025 + ICDR, ≤ 50°S | ≈ 3–5 GB | ≈ 1–2 h | **High:** independent SIC validation |
| C2 | GLORYS12 monthly | sithick, siconc, thetao (surface), ≤ 50°S, 1993–2026 | ≈ 3 GB | ≈ 1 h | **High:** ice thickness and ocean side of ML-04 |
| C3 | DMI-ASIP 1 km | Only the ML-03 test-scene dates (≈ 100 days), ≤ 50°S | ≈ 2–4 GB | ≈ 1 h | Medium |
| C4 | Ice drift AMSR P3D | 2003–2026, 0.25° | ≈ 1 GB | < 1 h | Low |
| E1 | ERA5 monthly SST (addition to the running ERA5 job list) | 1979–2026 | ≈ 0.3 GB | 1 CDS job | Medium (cheaper than OSTIA) |

**Total new disk use:** about 15–20 GB (H: has 176 GB free; the ERA5 download currently running needs up to about 60 GB).

**Not proposed:**

- OSTIA daily (about 370 GB);
- MERRA-2 hourly (420 MB per day);
- any re-download of NSIDC or NCEP.

## 6. Scientific caveats to carry forward

- **MERRA-2** starts in 1980. It is a different reanalysis, so use it for cross-checks, not mixed into the same baseline.
- **ERA5 snow depth** over the ice sheet is a fixed value (not a physical snow signal). It is meaningful only over sea ice and the ice-sheet margins.
- **GLORYS12** is a model reanalysis (assimilating observations). Its ice thickness has no dense observational constraint in the Southern Ocean.
- **DMI-ASIP** is an automated CNN product. Agreement with ML-03 is not independent validation.
