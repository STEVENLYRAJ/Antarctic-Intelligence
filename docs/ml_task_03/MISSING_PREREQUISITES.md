# ML-03 — Missing Prerequisites

| # | prerequisite | impact | workaround used | how to resolve |
|---|---|---|---|---|
| 1 | Copernicus Data Space (CDSE) account | cannot download full-resolution SAFE products directly from ESA | identical official GRD data from Microsoft Planetary Computer (anonymous, COG + SAFE annotations) | register at dataspace.copernicus.eu; set `CDSE_USERNAME` / `CDSE_PASSWORD` |
| 2 | Copernicus Marine account | DMI-ASIP Antarctic product (SEAICE_ANT_PHY_AUTO_L3_NRT_011_012) only for the single local day 2023-02-02 | USNIC charts as labels; DMI-ASIP used only as a one-day pseudo-label comparison | `copernicusmarine login`, then `scripts/ml03/download_data.py --dmi-asip` |
| 3 | ESA SNAP | no SNAP graph (orbit refinement, terrain flattening) | calibration + thermal-noise removal from the product LUTs in Python; GCP geocoding (sea ice is at sea level, so terrain correction is unnecessary over ocean) | install SNAP if land/ice-shelf geometry becomes important |
| 4 | Dual-polarisation imagery | Antarctic EW acquisitions are mostly HH-only (1SSH) | HH-only models; HV handled as optional channel | none (acquisition plan of ESA) |
| 5 | Human/expert annotators | no expert-confirmed pixel labels | annotation protocol + QGIS workflow written; chart-derived labels with buffered (uncertain) boundaries | annotate the exported review tiles following ANNOTATION_GUIDELINES.md |
| 6 | Full-resolution (40 m) processing | storage/bandwidth (≈ 1 MB/s measured) | scenes read at the ×8 COG overview (≈ 320 m) and resampled to 400 m — matched to chart-label scale | rerun with `--overview 1` when bandwidth allows |
