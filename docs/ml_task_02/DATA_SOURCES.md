# AETHENTRA ML-02 — Data Sources (acquisition, Phase 1)

Full description, status and licences: **TEMPERATURE_DATA_SOURCES.md**. Machine-readable inventory: `DATA_INVENTORY.csv`.
Configuration: `configs/ml02/data_sources.yaml`, `configs/ml02/stations.yaml`. Code: `src/aethentra/temperature/data/acquisition.py`.

```bash
python scripts/ml02/download_data.py --stations       # Zenodo 17164992 (MD5-verified) + GHCN-Daily Antarctic TAVG
python scripts/ml02/download_data.py --ncep-interim   # NCEP/NCAR R1 daily 2 m T (interim, anonymous OPeNDAP)
python scripts/ml02/download_data.py --era5           # ERA5 daily statistics via CDS (needs %USERPROFILE%\.cdsapirc)
```

Every downloaded file has a sibling `<file>.provenance.json`: source URL / CDS request, product version or record id,
retrieval time (UTC), MD5, size, and validation result. Complete files are never re-downloaded or overwritten.
Credentials are never written to the repository (`.env.example` lists the optional variables; `.env` is git-ignored).
Raw data live in `data/raw/era5/`, `data/raw/ncep_r1_2m/`, `data/raw/station_observations/` (git-ignored).
