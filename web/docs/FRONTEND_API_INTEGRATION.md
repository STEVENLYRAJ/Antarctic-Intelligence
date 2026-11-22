# Frontend ↔ API integration

**Client:** `src/lib/api/client.ts`.
- `apiGet<T>(path)` calls `/backend{path}`, which `next.config.ts` rewrites to `AETHENTRA_API_URL` (default `http://127.0.0.1:8000`).
- It retries twice on network errors and 5xx, with exponential back-off. 4xx errors are not retried.
- Requests are abortable.

**Hook:** `useApi<T>(path)` returns `{data, error, loading}` and aborts on unmount. `useApi(path, true)` reads static files from `public/`.

**Types:** `src/lib/api/types.ts`. Only the fields the UI reads are strictly typed. Everything else stays `unknown`.

## Connected endpoints (all verified returning 200 on 2026-11-20)
| Endpoint | Used by | Fields used |
|---|---|---|
| `GET /health` | (proxy check) | status |
| `GET /forecast/latest` | `/`, ML-01 | data_type, issue_date, target_start/end, extent_km2, area_km2, persistence/climatology_extent_km2, sectors[], model_version, limitations[] |
| `GET /forecast/metrics` | ML-01 | evaluation_period, issue_dates, metrics.{model}.all.{mae_pp, rmse_pp, r2, extent_mae_km2, iiee_mean_km2, edge_f1} |
| `GET /model/info` | ML-01 | model_version, model_family, selected_candidate, target, training_period, grid, features, operational_decision |
| `GET /temperature/forecast/latest` | `/`, ML-02 | data_type, dates, regions[].{forecast_mean_t2m_degC, forecast_mean_anomaly_degC}, climatology_reference_period, model_version |
| `GET /temperature/forecast/metrics` | ML-02 | n_issue_dates, issue_dates, source, metrics.{model}.all.{mae_degC, rmse_degC, acc_pattern_mean, msss_vs_climatology, r2_anomaly} |
| `GET /temperature/model/info` | ML-02 | kind, selected_from, n_features, train_period, source, selection, operational_decision |
| `GET /seaice-detection/detection/weekly` | `/`, ML-03 | week_start/end, n_acquisitions, observed_area_km2_nominal, cells_weekly_ice/water/variable, model_version |
| `GET /seaice-detection/detection/metrics` | ML-03 | n_scenes, charts, label_source, metrics.{model}.{miou, f1_ice, f1_water, overall_accuracy, ice_area_bias_pct} |
| `GET /seaice-detection/model/info` | ML-03 | kind, channels, architecture, loss, input, labels, trained_utc |
| `GET /api/ml04/latest` | `/`, ML-04 | latest_multivariate.{month, statistics, regions, model_version, selected_method} |
| `GET /api/ml04/monthly-summary` | ML-04, `/research` | rows[].{month, multivariate_flag_area_fraction, {var}_flag_area_fraction}, note |
| `GET /api/ml04/events` | ML-04 | definition, events[], note |
| `GET /api/ml04/metrics` | ML-04 | evaluation, test / validation.{method}.{pr_auc, roc_auc, recall_at_moderate, flag_rate_non_injected} |
| `GET /api/ml04/model-info` | ML-04 | model_version, selected_multivariate, family, params, features, periods, severity_thresholds, reference_methods |
| `GET /layers/{sic\|t2m\|sar\|anom}/latest` | ML pages, `/explore` | layers[].{id, title, data_type, units, period, issue_date, style, png_url, globe_png_url, globe_bounds}, limitations |
| `GET /layers/{p}/{id}/{layer}.png` | ML pages (2D) | image |
| `GET /globe/{p}/{id}/{layer}.png` | `/explore` (3D) — **new** | EPSG:4326 image, bounds in manifest / `X-Bounds` |

## Static presentation products (`public/data`, built from the archive; never the raw archive)
| File | Built by | Used by |
|---|---|---|
| `climate_series.json` (≈ 0.5 MB) | `build_climate_series.py`, extended by `build_globe_products.py` | `/`, `/intelligence`, `/research`, explorer region panel |
| `daily_series.json` (≈ 0.2 MB) | `build_globe_products.py c1 era5d` | `/intelligence` daily records, `/research` |
| `globe/catalog.json` + `globe/layers/<id>/<t>.png` (≈ 156 MB, 2,034 frames, 24 layers; ERA5 steps: era5m era5d era5m2 era5d2) | `build_globe_products.py` | `/explore` timeline layers, `/intelligence` then-vs-now |
| `globe/vectors/drift/<month>.json` | `build_globe_products.py c5` | `/explore` drift arrows |
| `imagery/*.jpg` + `index.json` | `fetch_gibs_imagery.py` (NASA GIBS WMS, EPSG:3031, cached) | `/` continent chapter and region cards, explorer region panel, polar basemap |
| `sar/<scene>/*.png` | `build_sar_examples.py` | ML-03 comparison slider |

The browser loads one frame at a time (plus two preloaded during playback).

## External services (browser → provider, no token)
- NASA GIBS WMTS: `BlueMarble_ShadedRelief_Bathymetry` (500m) and `MODIS_Terra_CorrectedReflectance_TrueColor` (250m, by date).
- Optional: Cesium ion World Terrain, only when `NEXT_PUBLIC_CESIUM_ION_TOKEN` is set.

## Data-integrity rules enforced in the UI
- Every value or layer shows a `DataBadge`. Prediction maps carry a dashed amber frame and a stamp.
- Metrics tables show every candidate exactly as returned. "Best" is computed per column for display only.
- ML-01 shows when the SIC-only fallback model issued the forecast. ML-02 shows that NCEP R1 ends in March 2026. ML-04 shows that its evaluation is synthetic.
- No mock or demo data is used anywhere.
- Freshness: issue dates, target periods and model versions are displayed next to each output.
