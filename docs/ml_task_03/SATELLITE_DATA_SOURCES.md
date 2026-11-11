# ML-03 — Satellite and Reference Data Sources

| source | role | access used | status |
|---|---|---|---|
| **Sentinel-1 A/B EW GRDM HH** (ESA Copernicus, Level-1 GRD, 40 m pixels, 6×2 looks) | model input | Microsoft Planetary Computer STAC `sentinel-1-grd` (COG + SAFE `calibration`/`noise` XML), anonymous SAS token | **downloaded + validated** (md5 per file, provenance JSON per scene in `data/raw/sentinel1/<scene>/`) |
| **USNIC Antarctic weekly/biweekly ice charts** (SIGRID-3 shapefiles, 2018-01 → 2026-10) | pixel labels (expert analyses) | `usicecenter.gov/File/DownloadArchive?prd=…`, anonymous | **387 charts downloaded** (zip md5 + provenance in `data/raw/ice_charts/usnic_antarctic/<date>/`) |
| Natural Earth 10 m land + Antarctic ice shelves | land / ice-shelf mask | naciscdn.org, public domain | downloaded |
| DMI-ASIP Antarctic SIC mosaic (CMEMS SEAICE_ANT_PHY_AUTO_L3_NRT_011_012), 1 km | comparison only | local file `DATAS/dmi_asip_seaice_mosaic_ant_20230202.nc`; more days need a Copernicus Marine account | 1 day available |
| NSIDC G02202 v6 (25 km SIC) | coarse context (ML-01) | already on disk | not used as pixel labels (25 km) |
| Copernicus Data Space (CDSE), ASF | official full-resolution SAFE downloads | catalogue reachable; download needs accounts | **not used** (no credentials) |
| AI4Arctic ASIP v2 | Arctic training data | not downloaded | **not used**: Arctic data cannot validate an Antarctic model |
| OSI SAF / Bremen AMSR2 ASI | coarse independent comparison | reachable | not used in this release (see NEXT_STEPS.md) |

## Sentinel-1 acquisition choices

* **Mode EW (400 km swath, GRDM)**: ESA's acquisition plan over Antarctic sea ice is EW; IW covers mostly coasts/land.
* **Polarisation HH only**: Antarctic EW products are single-pol `1SSH`; HV is not available, so no model depends on it.
* **Resolution**: each scene is read at the ×8 COG overview (≈ 320 m) and resampled to 400 m — matched to the chart-label scale
  (km) and to the measured bandwidth (≈ 1 MB/s). Full-resolution reading is a configuration change (`overview_factor: 1`).
* **Scene selection**: for every chart, the 80 EW HH acquisitions closest to (and not after) the chart valid date are searched
  (centroid south of 55°S) and 2 are drawn per chart, stratified by longitude sector (seed 42). Scene catalogue:
  `data/interim/ml03/scene_catalogue.csv` (id, time, footprint, polarisation, mode, orbit, sector, split, download/processing status).

## Label caveats (USNIC charts)

Charts are expert interpretations of multi-sensor imagery (including Sentinel-1) over the days before the valid date, drawn at
chart scale (polygons of tens of km). They are independent of our model but **not pixel-perfect truth**: boundaries can be displaced
by kilometres and ice drifts between the image and the chart. Hence the uncertain buffer around class boundaries and the wording
"agreement with the chart" for all metrics.
