"""ML-02 frontend layers (CesiumJS / Next.js) for one forecast: outputs/ml02/forecasts/<id>/layers/.

Every layer is labelled with data_type (reanalysis_observation | climatology_reference | model_prediction | evaluation).
GeoTIFFs are on the native EPSG:3412 25 km grid; PNG overlays are EPSG:4326 display renderings (nearest resampling).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ...visualization.layers import _png_4326, _tif
from ...visualization.style import DIVERGING
from ..paths import METRICS
from .predict import FORECAST_DIR

TEMP_DIV = DIVERGING.reversed()


def export_layers(s, fields: dict, ctx) -> dict:
    from matplotlib import colormaps
    d = FORECAST_DIR / s.forecast_id / "layers"
    d.mkdir(parents=True, exist_ok=True)
    cube = ctx.cube
    t = pd.Timestamp(s.issue_date)
    common = {"model_version": s.model_version, "source": s.reanalysis_source, "issue_date": str(s.issue_date),
              "climatology_reference_period": s.climatology_reference_period, "limitations": s.limitations}
    an = fields["t2m_anomaly_forecast"]
    cat = fields["anomaly_category"]
    seq = colormaps["cividis"]
    hist_mean = cube.window("t2m", t, 365).mean(0)
    specs = [
        ("historical_t2m_past_year", hist_mean, "reanalysis_observation", "degC", f"{(t - pd.Timedelta(days=364)).date()}..{t.date()} mean", seq, -60, 0),
        ("observed_t2m_latest_week", fields["observed_t2m_last_week"], "reanalysis_observation", "degC", f"7 days ending {t.date()}", seq, -60, 0),
        ("observed_anomaly_latest_week", fields["observed_anomaly_last_week"], "reanalysis_observation", "degC", f"7 days ending {t.date()}", TEMP_DIV, -10, 10),
        ("forecast_t2m", fields["t2m_forecast"], "model_prediction", "degC", f"{s.target_start}..{s.target_end}", seq, -60, 0),
        ("forecast_anomaly", an, "model_prediction", "degC", f"{s.target_start}..{s.target_end}", TEMP_DIV, -6, 6),
        ("forecast_warm_regions", np.where(cat >= 3, cat, np.nan), "model_prediction", "category", "warm (3) / strong warm (4)", TEMP_DIV, 0, 4),
        ("forecast_cold_regions", np.where((cat >= 0) & (cat <= 1), cat, np.nan), "model_prediction", "category", "strong cold (0) / cold (1)", TEMP_DIV, 0, 4),
        ("forecast_extreme_regions", np.where((cat == 0) | (cat == 4), cat, np.nan), "model_prediction", "category", "|anomaly| >= 2 sigma", TEMP_DIV, 0, 4),
    ]
    unet = s.model_name == "cnn_unet"                     # error map of the model that produced this forecast
    em = METRICS / ("test_cnn_addendum" if unet else "test_final") / "error_maps.npz"
    if em.exists():
        z = np.load(em)
        specs.append(("test_error_mae", z["cnn_unet_final__mae" if unet else "final_model__mae"], "evaluation", "degC", "per-cell MAE over the 2018-2025 test issue dates",
                      colormaps["magma_r"], 0, 4))
    layers = []
    for name, v, dtype, units, period, cmap, vmin, vmax in specs:
        g = cube.to_grid(v)
        _tif(d / f"{name}_3412.tif", g)
        bounds = _png_4326(d / f"{name}_4326.png", g, vmin, vmax, cmap)
        layers.append({"id": name, "data_type": dtype, "units": units, "period": period, "geotiff": f"{name}_3412.tif",
                       "png": f"{name}_4326.png", "png_bounds": bounds, "color_range": [vmin, vmax]})
    reg = [r.model_dump() for r in s.regions]
    (d / "regional_anomaly_summary.json").write_text(json.dumps({"forecast_id": s.forecast_id, "data_type": "model_prediction",
                                                                  "target_start": str(s.target_start), "target_end": str(s.target_end),
                                                                  "regions": reg}, indent=1))
    man = {"forecast_id": s.forecast_id, "crs_geotiff": "EPSG:3412 (NSIDC Sea Ice Polar Stereographic South, 25 km)",
           "layers": layers, "regional_summary": "regional_anomaly_summary.json", **common,
           "display_notes": "Distinguish data_type visually: observations/reanalysis vs model predictions vs evaluation layers."}
    (d / "manifest.json").write_text(json.dumps(man, indent=1))
    return man
