"""ML-03 tests. Arrays below are SYNTHETIC and only test software logic; no scientific claim rests on them."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]


def test_sigrid_ct_mapping():
    from aethentra.sar.labels import ICE, INVALID, UNCERTAIN, WATER, ct_class
    assert [ct_class(c) for c in ("00", "01", "02")] == [WATER] * 3
    assert [ct_class(c) for c in ("13", "46", "68", "10")] == [UNCERTAIN] * 4
    assert [ct_class(c) for c in ("70", "79", "81", "91", "92")] == [ICE] * 5
    assert ct_class("-9") == INVALID and ct_class("99") == INVALID


def test_boundary_buffer_marks_only_near_edges():
    from aethentra.sar.labels import ICE, INVALID, UNCERTAIN, WATER, buffer_boundaries
    lab = np.full((40, 40), WATER, np.uint8)
    lab[:, 20:] = ICE
    lab[:, :3] = INVALID
    out = buffer_boundaries(lab, 4)
    assert (out[:, 16:24] == UNCERTAIN).all()
    assert (out[:, 3:15] == WATER).all() and (out[:, 25:] == ICE).all() and (out[:, :3] == INVALID).all()


def test_separable_lut_equals_bilinear():
    from aethentra.sar.preprocessing import _grid_interp
    lines = np.array([0.0, 100.0, 200.0])
    pix = [np.array([0.0, 50.0, 100.0])] * 3
    vals = [np.array([1.0, 2.0, 3.0]) + k for k in range(3)]                 # f = 1 + p/50 + l/100 (bilinear exactly)
    L, P = np.array([0.0, 50.0, 150.0]), np.array([25.0, 75.0])
    got = _grid_interp(lines, pix, vals, L, P)
    exp = 1 + P[None, :] / 50 + L[:, None] / 100
    np.testing.assert_allclose(got, exp)


def test_footprint_multipolygon():
    from aethentra.sar.acquisition import footprint_points
    g = {"type": "MultiPolygon", "coordinates": [[[[170, -70], [180, -70], [180, -72], [170, -70]]], [[[-180, -70], [-170, -70], [-180, -72], [-180, -70]]], []]}
    assert footprint_points(g).shape == (8, 2)


def test_scene_metrics_perfect_and_area():
    from aethentra.sar.evaluation import scene_record, summarize, true_pixel_area_km2
    lab = np.zeros((30, 30), np.uint8); lab[:, 15:] = 1
    valid = np.ones_like(lab, bool)
    area = np.full(lab.shape, 0.16)
    rec = scene_record(lab == 1, None, lab, lab, valid, area, 400)
    s = summarize(pd.DataFrame([rec]))
    assert s["iou_ice"] == 1 and s["iou_water"] == 1 and abs(s["ice_area_bias_km2"]) < 1e-9
    assert rec["boundary_f1"] == 1.0
    a = true_pixel_area_km2(np.array([-71.0, -60.0]), np.array([0.0, 0.0]), 400)
    assert abs(a[0] - 0.16) < 0.002 and a[1] < a[0]                         # true scale at 71S; map scale > 1 equatorward -> less true area


def test_weekly_composite_counts():
    from aethentra.sar.inference import composite, weekly_grid
    tr, shape = weekly_grid()
    meta = {"transform": [400.0, 0, 0.0, 0, -400.0, 0.0], "resolution_m": 400}
    c1 = np.ones((10, 10), np.uint8)                                          # 2 x 2 weekly cells, all ice
    c2 = np.zeros((10, 10), np.uint8); c2[:, :5] = 255                       # same area: water in right half only
    wk = composite([{"scene_id": "a", "meta": meta, "class": c1}, {"scene_id": "b", "meta": meta, "class": c2}], "2026-01-05")
    i0, j0 = int(-tr.f / tr.e), int(-tr.c / tr.a)
    assert wk["n_valid"][i0, j0] == 1 and wk["n_valid"][i0, j0 + 1] == 2
    assert wk["frequency"][i0, j0 + 1] == 0.5 and wk["class"][i0, j0 + 1] == 2
    assert np.isnan(wk["frequency"][0, 0])                                     # unobserved cells are never filled


def test_scene_splits_are_disjoint():
    p = ROOT / "data" / "interim" / "ml03" / "scene_catalogue.csv"
    if not p.exists():
        pytest.skip("scene catalogue not built")
    cat = pd.read_csv(p)
    assert cat.groupby("scene_id")["split"].nunique().max() == 1
    for s, (a, b) in {"train": ("2018-01-01", "2022-12-31"), "validation": ("2023-01-01", "2024-12-31")}.items():
        d = pd.to_datetime(cat.loc[cat.split == s, "chart_date"])
        assert d.min() >= pd.Timestamp(a) and d.max() <= pd.Timestamp(b)
    t = ROOT / "data" / "processed" / "ml03" / "tiles"
    if (t / "train_index.csv").exists():
        ids = {s: set(pd.read_csv(t / f"{s}_index.csv").scene_id) for s in ("train", "validation", "test")}
        assert not (ids["train"] & ids["validation"]) and not (ids["train"] & ids["test"]) and not (ids["validation"] & ids["test"])


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


@pytest.mark.parametrize("url", ["/seaice-detection/detection/S1X_bad/files/netcdf", "/seaice-detection/detection/weekly/../x/files/weekly_class",
                                 "/seaice-detection/detection/weekly/2026-01-01/files/nope"])
def test_api_rejects_unknown(client, url):
    assert client.get(url).status_code == 404


def test_api_detect_validates_id(client):
    assert client.post("/seaice-detection/detect/sea-ice", json={"scene_id": "../../etc"}).status_code in (422, 503)
    assert client.get("/seaice-detection/health").status_code == 200
