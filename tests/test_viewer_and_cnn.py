"""Viewer / map-layer endpoints and the shared U-Net candidate (synthetic tensors only; torch tests skip if torch is absent)."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_viewer_served(client):
    r = client.get("/viewer/")
    assert r.status_code == 200 and "AETHENTRA" in r.text
    assert client.get("/", follow_redirects=False).status_code == 307


@pytest.mark.parametrize("product", ["sic", "t2m"])
def test_layers_latest_labelled(client, product):
    r = client.get(f"/layers/{product}/latest")
    if r.status_code == 404:
        pytest.skip("no forecast with layers generated")
    d = r.json()
    assert d["layers"] and all(lyr["data_type"] for lyr in d["layers"])
    assert any(lyr["data_type"] == "model_prediction" for lyr in d["layers"])
    rasters = [lyr for lyr in d["layers"] if "png_url" in lyr]
    png = client.get(rasters[0]["png_url"])
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert "/" not in "".join(lyr["id"] for lyr in d["layers"])           # logical ids only, never paths


@pytest.mark.parametrize("url", ["/layers/xyz/latest", "/layers/sic/..%2F..%2Fconfigs/x.png", "/layers/sic/sic7d_20261101_x/forecast_7day_mean.png",
                                 "/layers/t2m/sic7d_20261101_aethentra-sic-weekly-20261108-v1/forecast_t2m.png"])
def test_layers_reject_unknown(client, url):
    assert client.get(url).status_code == 404


def test_gridmap_roundtrip():
    from aethentra.temperature.models.cnn import GridMap
    rows, cols = np.array([5, 5, 6, 9]), np.array([3, 4, 3, 7])
    gm = GridMap({"rows": rows, "cols": cols})
    v = np.array([1.0, 2.0, 3.0, 4.0], np.float32)
    g = gm.to_grid(v)
    assert g.shape == (5, 5) and np.isnan(g).sum() == 25 - 4
    np.testing.assert_array_equal(gm.to_cells(g), v)


def test_unet_shape_and_masked_loss():
    torch = pytest.importorskip("torch")
    from aethentra.models.unet import UNet, masked_loss
    net = UNet(5, base=8, depth=3)
    x = torch.randn(2, 5, 37, 45)                                      # odd size: padded internally, cropped back
    assert net(x).shape == (2, 1, 37, 45)
    y = torch.zeros(2, 37, 45); y[:, :5] = float("nan")
    w = torch.ones(2, 37, 45); w[:, :5] = 0
    p = torch.zeros(2, 1, 37, 45); p[:, :, :5] = 1e6                  # huge error only where the target is undefined
    assert float(masked_loss(p, y, w)) == 0.0 and float(masked_loss(p, y, w, "l1")) == 0.0


def test_unet_learns_synthetic_shift():
    torch = pytest.importorskip("torch")
    from aethentra.models.unet import StackDataset, UNet, fit
    rng = np.random.default_rng(0)
    X = rng.normal(size=(24, 2, 16, 16)).astype(np.float32)
    Y = (0.5 * X[:, 0] + 1.0).astype(np.float32)                         # SYNTHETIC test data
    ds = StackDataset(X, Y, np.zeros((1, 16, 16), np.float32), np.zeros(2, np.float32), np.ones(2, np.float32), np.ones((16, 16), np.float32), 0)
    rec = fit(UNet(4, base=8, depth=2, dropout=0.0), ds, ds, epochs=30, lr=3e-3, batch_size=8, patience=30)
    assert rec["best_val_metric"] < 0.5 * float(np.sqrt(((Y - Y.mean()) ** 2).mean()) + 1.0)
