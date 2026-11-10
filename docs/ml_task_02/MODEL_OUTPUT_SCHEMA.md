# AETHENTRA ML-02 — Model Output Schema (Phase 12)

A forecast is identified by `forecast_id = t2m7d_<YYYYMMDD issue>_<model_version>` and written to
`outputs/ml02/forecasts/<forecast_id>/`.

## NetCDF (`<forecast_id>.nc`, CF-1.8, native EPSG:3412 25 km grid, dims y=332, x=316; cells north of 60°S are NaN)
| Variable | Units | data_type | Meaning |
|---|---|---|---|
| `t2m_forecast` | °C | model_prediction | 7-day mean 2 m temperature, days t+1…t+7 |
| `t2m_anomaly_forecast` | °C | model_prediction | 7-day mean anomaly vs the 1981–2010 climatology of the same days |
| `anomaly_category` | 1 | model_prediction | 0 strong cold (< −2σ), 1 cold, 2 near normal, 3 warm, 4 strong warm (≥ 2σ) |
| `t2m_climatology_week` | °C | climatology_reference | climatological 7-day mean of the target week |
| `anomaly_persistence_reference` | °C | observation_derived_reference | anomaly of the issue day (persistence baseline) |
| `observed_anomaly_last_week`, `observed_t2m_last_week` | °C | reanalysis_observation | 7 days ending at the issue date |
| `t2m_anomaly_q10`, `t2m_anomaly_q90` | °C | model_prediction | only present if the interval passed test-period calibration (±5 pp) |
| `land_mask`, `region` | 1 | static | CDR land mask; 0 ocean, 1 Peninsula, 2 West, 3 East Antarctica |
Coordinates `x`, `y` (m, projection), 2-D `lat`, `lon`; `crs` grid-mapping variable (polar_stereographic, Hughes 1980 ellipsoid,
EPSG:3412). Global attributes: issue/target dates, model version, source, climatology period, history.

## JSON summary (`<forecast_id>.json`, pydantic `T2mForecastSummary`)
`forecast_id`, `data_type`, `product`, `issue_date`, `issue_time_utc`, `target_start`, `target_end`, `units`,
`climatology_reference_period`, `model_version`, `model_name`, `reanalysis_source`,
`regions[]` {`region`, `area_km2`, `forecast_mean_t2m_degC`, `climatology_mean_t2m_degC`, `forecast_mean_anomaly_degC`,
`last_week_observed_anomaly_degC`, `fraction_warm_ge_1sigma`, `fraction_cold_le_minus1sigma`, `fraction_extreme_abs_ge_2sigma`}
(regions: all, antarctica_land, southern_ocean, antarctic_peninsula, west_antarctica, east_antarctica, coastal_land, inland),
`input_quality` {`latest_input_date`, `t2m_cells_valid_fraction`, `history_days_available_of_56`, `predictors_missing[]`, `warnings[]`},
`uncertainty` {`validated`, `method`, `nominal_coverage`, `empirical_test_coverage`, `note`}, `test_metrics_reference`,
`provenance`, `limitations[]`, `files`, `generated_utc`.

## Frontend layers (`layers/`, written with `--layers`)
`manifest.json` lists every layer with `data_type`, units, period, colour range and the EPSG:4326 PNG bounds:
`historical_t2m_past_year`, `observed_t2m_latest_week`, `observed_anomaly_latest_week` (reanalysis_observation);
`forecast_t2m`, `forecast_anomaly`, `forecast_warm_regions`, `forecast_cold_regions`, `forecast_extreme_regions` (model_prediction);
`test_error_mae` (evaluation). Each as `<id>_3412.tif` (native grid GeoTIFF, nodata −9999) and `<id>_4326.png` (display overlay).
`regional_anomaly_summary.json` repeats the regional table for UI cards.

## API (`api/temperature.py`, mounted at `/temperature`)
`GET /temperature/health`, `GET /temperature/model/info`, `POST /temperature/forecast/weekly` {`issue_date`?, `write_layers`?},
`GET /temperature/forecast/latest`, `GET /temperature/forecast/history`, `GET /temperature/forecast/metrics`,
`GET /temperature/forecast/metadata`, `GET /temperature/forecast/{forecast_id}/files/{netcdf|summary_json}`.
