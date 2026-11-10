"""Tests for AETHENTRA Task 01 (weekly SIC forecasting).

Unit tests run on a SYNTHETIC cube (clearly labelled software fixture - never used for scientific results).
Integration tests run on the real artifacts and are skipped when those have not been produced.
"""
import json

import numpy as np
import pandas as pd
import pytest

from aethentra.baselines.baselines import BASELINES, fallback, predict_baseline
from aethentra.config import EXPERIMENTS_DIR, MODELS_DIR, load
from aethentra.evaluation.metrics import grid_sums, summarize
from aethentra.features.build import FeatureContext, feature_names, issue_dates
from aethentra.features.climatology import Climatology, doy_index
from aethentra.preprocessing.cube import Cube, cell_area_km2, sector_ids

NY, NX = 30, 32


# --------------------------------------------------------------------------- synthetic cube fixture
def make_synthetic_cube(d, start="2000-01-01", end="2002-12-31", missing_days=("2001-06-10",)):
    """SYNTHETIC test data: seasonal ice tongue on a 30x32 grid with a land block. Not real observations."""
    dates = pd.date_range(start, end, freq="D")
    rng = np.random.default_rng(0)
    yy, xx = np.mgrid[0:NY, 0:NX]
    ocean = ~((yy < 6) & (xx < 6))
    sic = np.full((len(dates), NY, NX), 255, np.uint8)
    for i, t in enumerate(dates):
        if str(t.date()) in missing_days:
            continue
        reach = 12 + 10 * np.sin(2 * np.pi * (t.dayofyear - 60) / 365)
        f = np.clip((reach - xx) * 12 + rng.normal(0, 2, (NY, NX)), 0, 100)
        f[~ocean] = 255
        sic[i] = np.rint(f).astype(np.uint8)
    np.save(d / "sic_daily.npy", sic)
    sd = np.where(sic <= 100, 5, 255).astype(np.uint8)
    np.save(d / "sic_stdev_daily.npy", sd)
    lat = np.linspace(-60, -75, NY)[:, None] * np.ones((1, NX))
    lon = np.linspace(-170, 170, NX)[None, :] * np.ones((NY, 1))
    area = np.full((NY, NX), 625.0)
    np.savez_compressed(d / "grid.npz", x=np.arange(NX) * 25e3, y=np.arange(NY)[::-1] * 25e3, lat=lat, lon=lon, ocean_mask=ocean,
                        cell_area_km2=area, dist_coast_km=np.zeros((NY, NX)), sector=sector_ids(lon, load("features")["sectors"]),
                        ocean_days=np.full((NY, NX), len(dates)), sector_names=np.array(list(load("features")["sectors"])))
    present = np.array([str(t.date()) not in missing_days for t in dates])
    pd.DataFrame({"date": dates.date, "present": present, "source_file": "synthetic", "valid_ocean_cells": 0,
                  "extent_mkm2": 0.0, "area_mkm2": 0.0}).to_csv(d / "calendar.csv", index=False)
    (d / "cube_meta.json").write_text(json.dumps({"start": start, "end": end, "shape": list(sic.shape), "synthetic": True}))
    return Cube(d)


@pytest.fixture(scope="module")
def syn(tmp_path_factory):
    d = tmp_path_factory.mktemp("cube")
    cube = make_synthetic_cube(d)
    clim = Climatology.fit(cube, "2000-01-01", "2001-12-31", 7)
    return FeatureContext(cube, clim, None)


# --------------------------------------------------------------------------- data loading / masking / alignment
def test_cube_loading_masks_missing(syn):
    c = syn.cube
    assert c.sic.shape == (len(c.dates), NY, NX)
    day = c.day("2000-03-01")
    assert np.isnan(day[~c.ocean]).all() and np.isfinite(day[c.ocean]).all()
    assert np.isnan(c.day("2001-06-10")).all()                     # missing day stays missing, never 0
    assert np.nanmax(day) <= 100 and np.nanmin(day) >= 0


def test_doy_index_leap_years():
    d = pd.to_datetime(["2000-02-28", "2000-02-29", "2000-03-01", "2001-03-01", "2000-12-31"])
    assert list(doy_index(d)) == [58, 58, 59, 59, 364]


def test_cell_area_true_scale_at_70S():
    proj = load("preprocessing")["grid"]["proj4"]
    a = cell_area_km2(np.array([[-70.0, -60.0]]), np.array([[0.0, 0.0]]), proj, 25000)
    assert a[0, 0] == pytest.approx(625.0, rel=2e-3)                 # true scale at the standard parallel
    assert a[0, 1] < a[0, 0]                                         # polar stereographic: cells shrink equatorward of 70S


def test_sector_ids_wrap_dateline():
    lon = np.array([-170.0, 170.0, 0.0, 50.0, 120.0, -100.0])
    s = sector_ids(lon, load("features")["sectors"])
    names = list(load("features")["sectors"])
    assert [names[i] for i in s] == ["ross", "ross", "weddell", "indian", "west_pacific", "bellingshausen_amundsen"]


# --------------------------------------------------------------------------- labels / temporal alignment
def test_target_is_mean_of_next_seven_days(syn):
    t = pd.Timestamp("2000-04-10")
    y, n = syn.target(t)
    manual = np.nanmean(np.stack([syn.cube.day(t + pd.Timedelta(days=k)) for k in range(1, 8)]), axis=0)
    m = syn.cube.ocean
    np.testing.assert_allclose(y[m], manual[m], rtol=1e-6)
    assert (n[m] == 7).all()


def test_target_min_valid_days_rule(syn):
    y, n = syn.target(pd.Timestamp("2001-06-08"))                    # window 06-09..06-15 contains the missing day
    assert (n[syn.cube.ocean] == 6).all() and np.isfinite(y[syn.cube.ocean]).all()


def test_no_future_information_in_features(syn, tmp_path):
    """Corrupt everything after t; features at t must be unchanged."""
    t = pd.Timestamp("2001-03-15")
    F1 = syn.features(t)
    c2 = make_synthetic_cube(tmp_path)
    i = c2.idx(t) + 1
    arr = np.load(tmp_path / "sic_daily.npy", mmap_mode="r+")
    arr[i:] = 100
    arr.flush()
    ctx2 = FeatureContext(Cube(tmp_path), syn.clim, None)
    F2 = ctx2.features(t)
    for k in F1:
        np.testing.assert_array_equal(np.nan_to_num(F1[k], nan=-1), np.nan_to_num(F2[k], nan=-1), err_msg=k)
    y1, _ = syn.target(t)
    y2, _ = ctx2.target(t)
    assert not np.allclose(np.nan_to_num(y1), np.nan_to_num(y2))      # target DOES see the future (by definition)


def test_persistence_falls_back_to_latest_valid(syn):
    p, age = syn.persistence(pd.Timestamp("2001-06-10"))             # day t missing
    m = syn.cube.ocean
    np.testing.assert_allclose(p[m], syn.cube.day("2001-06-09")[m])
    assert (age[m] == 1).all()


def test_weekly_lag_features(syn):
    t = pd.Timestamp("2000-05-20")
    F = syn.features(t)
    w2 = np.nanmean(np.stack([syn.cube.day(t - pd.Timedelta(days=k)) for k in range(7, 14)]), axis=0)
    np.testing.assert_allclose(F["sic_w2"][syn.cube.ocean], w2[syn.cube.ocean], rtol=1e-5)
    assert set(feature_names(False)) <= set(F)


def test_climatology_uses_fit_period_only(syn):
    clim = Climatology.fit(syn.cube, "2000-01-01", "2000-12-31", 7)
    k = doy_index(pd.DatetimeIndex(["2000-03-01"]))[0]
    vals = []
    for t in pd.date_range("2000-02-22", "2000-03-08"):   # doy 52..66 incl. 29 Feb folded onto doy 58
        vals.append(syn.cube.day(t))
    np.testing.assert_allclose(clim.mean[k][syn.cube.ocean], np.nanmean(np.stack(vals), 0)[syn.cube.ocean], rtol=1e-4)


# --------------------------------------------------------------------------- splits
def test_issue_dates_respect_split_boundaries():
    cfg = load("training")["splits"]
    h = load("features")["labels"]["horizon_days"]
    sets = {}
    for k, (s, e) in cfg.items():
        d = issue_dates(s, e)
        assert (d >= pd.Timestamp(s)).all() and (d + pd.Timedelta(days=h) <= pd.Timestamp(e)).all()
        assert (np.diff(d.values).astype("timedelta64[D]").astype(int) == 7).all()
        sets[k] = d
    assert sets["train"].max() + pd.Timedelta(days=h) < sets["validation"].min()
    assert sets["validation"].max() + pd.Timedelta(days=h) < sets["test"].min()


# --------------------------------------------------------------------------- extent / metrics
def test_extent_and_area_definitions(syn):
    f = np.full((NY, NX), np.nan, np.float32)
    f[syn.cube.ocean] = 0
    f[10, 10], f[11, 11], f[12, 12] = 14.9, 15.0, 80.0
    assert syn.extent(f) == pytest.approx(2 * 625 / 1e6)
    s = grid_sums(f, f, np.full((NY, NX), 625.0), syn.cube.ocean)
    assert s["area_obs"] == pytest.approx(625 * 0.15 + 625 * 0.80)
    assert s["ext_obs"] == pytest.approx(2 * 625)


def test_metrics_values_and_iiee():
    obs = np.array([[0, 10, 20, 90]], float)
    pred = np.array([[0, 20, 10, 90]], float)
    area = np.ones_like(obs)
    s = grid_sums(pred, obs, area, np.ones_like(obs, bool))
    df = pd.DataFrame([s])
    m = summarize(df)
    assert m["mae_pp"] == pytest.approx(5.0) and m["bias_pp"] == pytest.approx(0.0)
    assert m["rmse_pp"] == pytest.approx(np.sqrt(50))
    assert m["iiee_mean_km2"] == pytest.approx(2.0)                 # one false positive + one false negative cell
    assert m["edge_iou"] == pytest.approx(1 / 3)


def test_land_and_missing_never_counted_as_zero():
    obs = np.array([[np.nan, 50.0]])
    pred = np.array([[0.0, 40.0]])
    s = grid_sums(pred, obs, np.ones_like(obs), np.ones_like(obs, bool))
    assert s["n"] == 1 and s["abs"] == pytest.approx(10.0)


# --------------------------------------------------------------------------- baselines / bounds / model
def test_baselines_bounded_and_filled(syn):
    F = syn.features(pd.Timestamp("2001-02-01"))
    for b in BASELINES:
        p = predict_baseline(b, F)
        assert np.isfinite(p).all() and p.min() >= 0 and p.max() <= 100, b
    G = {k: v.copy() for k, v in F.items()}
    G["sic_d0"][:] = np.nan
    oc = syn.cube.ocean
    expect = np.clip(np.where(np.isfinite(F["sic_w1"]), F["sic_w1"], F["clim_target"]), 0, 100)
    np.testing.assert_allclose(fallback(G["sic_d0"], G)[oc], expect[oc], rtol=1e-6)


def test_tree_model_train_predict_bounds_and_roundtrip(syn, tmp_path):
    from aethentra.models.tree_models import TreeModel
    names = feature_names(False)
    rng = np.random.default_rng(1)
    tabs = [syn.table(t, names, 0.5, rng)[0] for t in issue_dates("2000-03-01", "2001-12-31")]
    tr = pd.concat(tabs[:-10]); va = pd.concat(tabs[-10:])
    p = dict(load("training")["models"]["lightgbm"]); p.update(n_estimators=50, num_leaves=15, min_data_in_leaf=20)
    m = TreeModel("lightgbm", names, p, "residual", "syn_lgbm").fit(tr, va)
    m.save(tmp_path)
    m2 = TreeModel.load(tmp_path, "syn_lgbm")
    np.testing.assert_allclose(m.predict_sic(va), m2.predict_sic(va), rtol=1e-5)
    F = syn.features(pd.Timestamp("2002-03-01"))
    g, info = m2.predict_grid(F, syn.active_mask(F))
    assert g.min() >= 0 and g.max() <= 100 and info["model_cells"] > 0


# --------------------------------------------------------------------------- integration (real artifacts)
FINAL = MODELS_DIR / "final" / "final_model.meta.json"
needs_final = pytest.mark.skipif(not FINAL.exists(), reason="final model not trained yet")


@needs_final
def test_final_model_loads_and_selection_preceded_test():
    sel = json.loads((EXPERIMENTS_DIR / "metrics" / "selection_record.json").read_text())
    assert sel["test_set_accessed_before_selection"] is False
    test = EXPERIMENTS_DIR / "metrics" / "test_final" / "summary.json"
    if test.exists():
        import os
        assert os.path.getmtime(EXPERIMENTS_DIR / "metrics" / "selection_record.json") < os.path.getmtime(test)
    meta = json.loads(FINAL.read_text())
    assert meta["train_period"] == [load("training")["splits"]["train"][0], load("training")["splits"]["validation"][1]]


@needs_final
def test_forecast_output_schema_and_bounds():
    from aethentra.inference.prediction_schema import ForecastSummary
    from aethentra.inference.predict import run_forecast
    s, fields = run_forecast(write=False)
    assert isinstance(s, ForecastSummary)
    f = fields["sic_forecast"]
    assert np.nanmin(f) >= 0 and np.nanmax(f) <= 100
    assert (s.target_end - s.target_start).days == 6 and (s.target_start - s.issue_date).days == 1
    assert s.extent_km2 > 0 and s.area_km2 < s.extent_km2
    assert s.data_type == "model_prediction"


@needs_final
def test_api_endpoints():
    from fastapi.testclient import TestClient
    from api.main import app
    c = TestClient(app)
    assert c.get("/health").json()["model_available"] is True
    info = c.get("/model/info").json()
    assert "features" in info and "file" not in info
    r = c.post("/forecast/weekly", json={})
    assert r.status_code == 200, r.text
    fid = r.json()["forecast_id"]
    assert c.get("/forecast/latest").status_code == 200
    assert c.get(f"/forecast/{fid}/files/netcdf").status_code == 200
    assert c.get("/forecast/../etc/files/netcdf").status_code == 404
    assert c.get(f"/forecast/{fid}/files/model").status_code == 404
    assert c.post("/forecast/weekly", json={"issue_date": "1900-01-01"}).status_code == 422
    assert c.post("/forecast/weekly", json={"issue_date": "not-a-date"}).status_code == 422


def test_masked_filter_never_returns_inf():
    from aethentra.features.build import _masked_filter
    a = np.zeros((20, 20), np.float32); v = np.zeros((20, 20), bool)
    a[0, 0], v[0, 0] = 1e-3, True                       # single valid cell; far cells have no valid neighbour
    out = _masked_filter(a, v, 7)
    assert not np.isinf(out).any() and np.isnan(out[19, 19]) and np.isfinite(out[0, 0])
