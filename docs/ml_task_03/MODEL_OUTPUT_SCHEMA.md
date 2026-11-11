# ML-03 — Model Output Schema

## Acquisition products `outputs/ml03/segmentation/<scene_id>/`

| file | content |
|---|---|
| `sea_ice_probability.tif` | float32 ice probability, nodata −1, EPSG:3031 400 m |
| `sea_ice_class.tif` | uint8: 0 water, 1 ice, 2 uncertain (0.35 < p < 0.65), 255 invalid |
| `segmentation.nc` | CF NetCDF: probability, class, ice / water / uncertain / invalid masks, x/y |
| `metadata.json` | scene id, acquisition + processing time, sensor, mode, polarisation, resolution, CRS, model version, pixel counts, nominal ice area, processing provenance, warnings |

## Weekly products `outputs/ml03/weekly_maps/week_<YYYY-MM-DD>/`

| file | content |
|---|---|
| `valid_acquisitions.tif` | uint16 number of acquisitions classifying the 2 km cell |
| `ice_detections.tif` | uint16 number of those classifying it as ice |
| `detection_frequency.tif` | float32 ice detections / valid acquisitions, −1 unobserved |
| `weekly_class.tif` | uint8: 0 water (≤ 1/3), 1 ice (≥ 2/3), 2 variable, 255 unobserved |
| `metadata.json` | week, acquisitions used, observed area, class counts, methodology, model version |

## API (`/seaice-detection`)

`/health`, `/model/info`, `POST /detect/sea-ice {scene_id}`, `/detection/latest`, `/detection/history`, `/detection/weekly[?week_start=]`, `/detection/metrics`, `/detection/metadata`, `/detection/{scene_id}/files/{probability_tif|class_tif|netcdf}`, `/detection/weekly/{week_start}/files/{detection_frequency|valid_acquisitions|ice_detections|weekly_class}`.