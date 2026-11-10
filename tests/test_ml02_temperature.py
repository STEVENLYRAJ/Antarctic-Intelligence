"""ML-02 tests. All gridded data here are SYNTHETIC (software tests only, never scientific evidence)."""
import json

import numpy as np
import pandas as pd
import pytest

from aethentra.temperature.baselines.baselines import BASELINES, fit_damped_alpha, predict_baseline
from aethentra.temperature.climatology.climatology import Climatology, doy_index, smooth_circular
from aethentra.temperature.evaluation.metrics import Accumulator, classification, region_masks
from aethentra.temperature.features.build import FeatureContext, feature_names, issue_dates
from aethentra.temperature.labels.labels import Sigma, categorize, weekly_labels
from aethentra.temperature.preprocessing.cube import FILL, Cube, apply_weights, bilinear_weights, to_target_units

NY, NX = 8, 10
START, END = "1979-01-01", "1984-12-31"


@pytest.fixture(scope="module")
def syn(tmp_path_factory):
    """SYNTHETIC cube: seasonal cycle + latitude gradient + AR(1) weather noise; t2m and msl."""
    d = tmp_path_factory.mktemp("ml02_synthetic_cube")
    dates = pd.date_range(START, END, freq="D")
    rows, cols = np.meshgrid(np.arange(NY), np.arange(NX), indexing="ij")
    rows, cols = rows.ravel(), cols.ravel()
    n = rows.size
    lat = -62.0 - rows * 3.0
    lon = cols * 36.0 - 180.0
    land = cols >= 4
    region = np.where(land, np.where(cols < 6, 1, np.where(cols < 8, 2, 3)), 0)
    grid = {"rows": rows.astype(np.int16), "cols": cols.astype(np.int16), "lat": lat, "lon": lon, "area_km2": np.full(n, 625.0),
            "land": land, "dist_coast_km": np.abs(cols - 3.5) * 25.0, "coastal": land & (cols <= 5), "region": region.astype(np.int8),
            "region_names": np.array(["southern_ocean", "antarctic_peninsula", "west_antarctica", "east_antarctica"]),
            "shape": np.array([NY, NX]), "x": np.arange(NX), "y": np.arange(NY), "elevation_m": np.where(land, 1000.0, 0.0)}
    np.savez(d / "grid.npz", **grid)
    rng = np.random.default_rng(0)
    seas = -15 * np.cos(2 * np.pi * (dates.dayofyear.to_numpy() - 15) / 365.25)
    noise = np.zeros((len(dates), n))
    for i in range(1, len(dates)):
        noise[i] = 0.8 * noise[i - 1] + rng.normal(0, 2, n)
    t2m = -20 + seas[:, None] - 0.5 * (lat[None] + 62) + noise
    msl = 985 + rng.normal(0, 5, (len(dates), n))
    np.save(d / "t2m.npy", np.round(t2m / 0.01).astype(np.int16))
    np.save(d / "msl.npy", np.round(msl / 0.1).astype(np.int16))
    pd.DataFrame({"date": dates, "t2m": True, "msl": True}).to_csv(d / "calendar.csv", index=False)
    meta = {"source": "synthetic", "n_cells": n, "start": START, "end": END,
            "variables": {"t2m": {"scale": 0.01, "units": "degC"}, "msl": {"scale": 0.1, "units": "hPa"}}}
    (d / "cube_meta.json").write_text(json.dumps(meta))
    cube = Cube("synthetic", directory=d)
    clim = Climatology.fit(cube, ["t2m", "msl"], period=(1979, 1982), half=15)
    sigma = Sigma.fit(cube, clim, issue_dates("1979-01-01", "1982-12-31"))
    return {"cube": cube, "clim": clim, "sigma": sigma, "ctx": FeatureContext(cube, clim, sigma, None), "t2m": t2m, "dates": dates}


def test_unit_conversion_only_when_kelvin():
    a = np.array([273.15, 250.0])
    c, msg = to_target_units("t2m", a, "K")
    assert np.allclose(c, [0.0, -23.15]) and "273.15" in msg
    c2, msg2 = to_target_units("t2m", np.array([-5.0]), "degC")
    assert c2[0] == -5.0 and "already" in msg2
    with pytest.raises(ValueError):
        to_target_units("t2m", a, "furlongs")
    assert np.allclose(to_target_units("msl", np.array([100000.0]), "Pa")[0], 1000.0)


def test_bilinear_reproduces_linear_field_and_wraps_longitude():
    src_lat = np.linspace(-55, -90, 141)                  # descending like ERA5
    src_lon = np.arange(0, 360, 0.25)
    f = (2 * src_lat)[:, None] + 0 * src_lon[None]        # linear in latitude only
    lat = np.array([-60.1, -77.33, -89.9])
    lon = np.array([359.9, -120.3, 10.0])
    out = apply_weights(f, bilinear_weights(src_lat, src_lon, lat, lon))
    assert np.allclose(out, 2 * lat, atol=1e-6)
    g = np.cos(np.radians(src_lon))[None] + 0 * src_lat[:, None]
    out2 = apply_weights(g, bilinear_weights(src_lat, src_lon, np.array([-70.0]), np.array([359.9])))
    assert abs(out2[0] - np.cos(np.radians(359.9))) < 1e-4    # interpolated across the 359.75 -> 0 seam


def test_doy_and_circular_smoothing():
    d = pd.to_datetime(["2000-02-28", "2000-02-29", "2000-03-01", "2001-03-01", "2000-12-31"])
    assert list(doy_index(d)) == [58, 58, 59, 59, 364]
    a = np.arange(365, dtype=float)[:, None]
    s = smooth_circular(a, 1)
    assert np.isclose(s[0, 0], (364 + 0 + 1) / 3) and np.isclose(s[100, 0], 100)


def test_climatology_and_labels_alignment(syn):
    cube, clim, t2m, dates = syn["cube"], syn["clim"], syn["t2m"], syn["dates"]
    t = pd.Timestamp("1983-06-12")
    tw, aw, cw = weekly_labels(cube, clim, t)
    i = dates.get_loc(t)
    assert np.allclose(tw, t2m[i + 1:i + 8].mean(0), atol=0.01)            # t+1 .. t+7, not including t
    assert np.allclose(cw, clim.mean["t2m"][doy_index(pd.date_range(t + pd.Timedelta(days=1), periods=7))].mean(0))
    assert np.allclose(aw, tw - cw, atol=1e-5)


def test_features_never_use_future_data(syn, tmp_path):
    ctx = syn["ctx"]
    t = pd.Timestamp("1983-09-04")
    F1 = ctx.features(t)
    cube = ctx.cube
    raw = np.load(cube.dir / "t2m.npy")
    raw2 = raw.copy()
    raw2[cube.idx(t) + 1:] = FILL                                           # wipe everything after the issue day
    d2 = tmp_path / "cut"
    d2.mkdir()
    for f in cube.dir.iterdir():
        if f.name != "t2m.npy":
            (d2 / f.name).write_bytes(f.read_bytes())
    np.save(d2 / "t2m.npy", raw2)
    ctx2 = FeatureContext(Cube("synthetic", directory=d2), ctx.clim, ctx.sigma, None)
    F2 = ctx2.features(t)
    for k in F1:
        assert np.allclose(F1[k], F2[k], equal_nan=True), k
    tw2, _, _ = ctx2.labels(t)
    assert np.isnan(tw2).all()                                            # labels need the future, features do not


def test_issue_dates_respect_split_boundaries():
    d = issue_dates("2011-01-01", "2017-12-31")
    assert d.min() >= pd.Timestamp("2011-01-01")
    assert (d + pd.Timedelta(days=7)).max() <= pd.Timestamp("2017-12-31")
    assert (np.diff(d.values).astype("timedelta64[D]").astype(int) == 7).all()
    tr, va = issue_dates("1979-01-01", "2010-12-31"), issue_dates("2011-01-01", "2017-12-31")
    assert (tr + pd.Timedelta(days=7)).max() < va.min()


def test_categories():
    c = categorize(np.array([-3, -1.5, 0, 1.5, 3, np.nan]), np.ones(6))
    assert list(c) == [0, 1, 2, 3, 4, -1]


def test_baselines_and_damped_alpha(syn):
    ctx = syn["ctx"]
    t = pd.Timestamp("1983-03-06")
    F = ctx.features(t)
    sig = ctx.sigma.for_date(t)
    rows = pd.concat([ctx.table(d, feature_names(["t2m"], False, True)) .assign(season="MAM") for d in issue_dates("1980-03-01", "1980-05-25")])
    alpha = fit_damped_alpha(rows)
    assert 0 < alpha["MAM_land"] < 1.5
    for b in BASELINES:
        p = predict_baseline(b, F, sig, alpha, "MAM")
        assert p.shape == F["anom_w1"].shape and np.isfinite(p).all()
    assert np.all(predict_baseline("climatology", F) == 0)
    assert np.allclose(predict_baseline("persistence", F), F["anom_d0"])


def test_metrics_and_classification(syn):
    g = syn["cube"].grid
    acc = Accumulator(g, np.full(g["lat"].size, 625.0))
    o = np.linspace(-3, 3, g["lat"].size)
    acc.add(pd.Timestamp("2000-01-02"), "DJF", o + 1.0, o, o - 20, categorize(o + 1, np.ones_like(o)), categorize(o, np.ones_like(o)))
    s = acc.summary()["all"]
    assert np.isclose(s["mae_degC"], 1.0) and np.isclose(s["bias_degC"], 1.0) and np.isclose(s["rmse_degC"], 1.0)
    assert np.isclose(s["acc_pattern_mean"], np.sum((o + 1) * o) / np.sqrt(np.sum((o + 1) ** 2) * np.sum(o * o)))
    cm = np.eye(5) * 10
    r = classification(cm)
    assert r["balanced_accuracy"] == 1.0 and r["warm_ge_1sigma"]["f1"] == 1.0
    assert set(region_masks(g)) >= {"all", "antarctica_land", "southern_ocean", "coastal_land", "inland"}


def test_anomaly_model_roundtrip(syn, tmp_path):
    from aethentra.temperature.models.anomaly_model import AnomalyModel
    ctx = syn["ctx"]
    names = feature_names(["t2m", "msl"], False)
    tr = pd.concat([ctx.table(d, names) for d in issue_dates("1979-03-01", "1981-12-31")])
    va = pd.concat([ctx.table(d, names) for d in issue_dates("1982-01-01", "1982-12-31")])
    m = AnomalyModel("lightgbm", names, {"learning_rate": 0.1, "num_leaves": 15, "min_data_in_leaf": 20, "n_estimators": 50}, name="syn")
    m.fit(tr, va)
    m.save(tmp_path)
    m2 = AnomalyModel.load(tmp_path, "syn")
    F = ctx.features(pd.Timestamp("1983-05-01"))
    p1, p2 = m.predict_cells(F), m2.predict_cells(F)
    assert np.allclose(p1, p2, atol=1e-5) and np.isfinite(p1).all()


def test_selection_frozen_before_ml02_test():
    from aethentra.temperature.paths import METRICS
    t = METRICS / "test_final" / "summary.json"
    if not t.exists():
        pytest.skip("ML-02 test evaluation not run yet")
    sel = json.loads((METRICS / "selection_record.json").read_text())
    assert sel["test_set_accessed_before_selection"] is False
    assert pd.Timestamp(sel["frozen_utc"]) < pd.Timestamp(json.loads(t.read_text()).get("evaluated_utc", "2100-01-01"), tz="UTC")


ml02_final = pytest.mark.skipif(not (__import__("aethentra.temperature.paths", fromlist=["MODELS"]).MODELS / "final" / "final_model.meta.json").exists(),
                                reason="ML-02 final model not trained yet")


@ml02_final
def test_ml02_forecast_output_schema_and_physics():
    from aethentra.temperature.inference.predict import load_bundle, run_forecast
    b = load_bundle()
    s, f = run_forecast("2024-07-07", bundle=b, write=False)
    assert str(s.target_start) == "2024-07-08" and str(s.target_end) == "2024-07-14"
    assert s.data_type == "model_prediction" and s.climatology_reference_period == [1981, 2010]
    t, a, c = f["t2m_forecast"], f["t2m_anomaly_forecast"], f["t2m_climatology_week"]
    ok = np.isfinite(a)
    assert ok.mean() > 0.99
    assert np.allclose(t[ok], c[ok] + a[ok], atol=1e-4)                     # absolute = climatology + anomaly
    assert np.nanmin(t) > -100 and np.nanmax(t) < 25                         # physically plausible weekly means
    assert set(np.unique(f["anomaly_category"][ok])) <= {0, 1, 2, 3, 4}
    assert {r.region for r in s.regions} >= {"all", "antarctica_land", "east_antarctica"}


@ml02_final
def test_ml02_api_endpoints():
    from fastapi.testclient import TestClient
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from api.main import app
    c = TestClient(app)
    assert c.get("/temperature/health").json()["model_available"] is True
    info = c.get("/temperature/model/info").json()
    assert info["n_features"] == len(info["features"])
    r = c.post("/temperature/forecast/weekly", json={"issue_date": "2025-06-01"})
    assert r.status_code == 200 and r.json()["forecast_id"].startswith("t2m7d_20250601")
    assert c.post("/temperature/forecast/weekly", json={"issue_date": "1979-01-02"}).status_code == 422
    assert c.get("/temperature/forecast/latest").status_code == 200
    assert c.get("/temperature/forecast/../../etc/files/netcdf").status_code == 404
    assert c.get("/health").status_code == 200                                # ML-01 service untouched
