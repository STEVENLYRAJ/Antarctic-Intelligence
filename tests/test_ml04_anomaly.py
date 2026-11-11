"""ML-04 tests. Unit tests use SYNTHETIC arrays (labelled as such; software testing only, never presented as real events).
Integration tests run against the built artefacts and are skipped when a pipeline stage has not been run."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from aethentra.anomaly import climatology as C
from aethentra.anomaly.detectors import (Autoencoder, Mahalanobis, SkModel, mad_score, percentile_score, severity_of,
                                         severity_thresholds, zscore_score)
from aethentra.anomaly.features import FEATS, model_matrix, split_of
from aethentra.anomaly.paths import FEATURES, METRICS, MODELS, OUTPUTS, load

RNG = np.random.default_rng(0)


# ------------------------------------------------------------- baselines / anomaly definitions
def test_percentile_rank_weibull():
    s = np.sort(np.arange(1, 30, dtype=np.float32))[:, None]          # 29 sorted values -> n + 1 = 30
    assert C.percentile_rank(np.array([15.0], np.float32), s)[0] == pytest.approx(15 / 30)
    assert C.percentile_rank(np.array([0.0], np.float32), s)[0] == pytest.approx(0.5 / 30)    # below record
    assert np.isnan(C.percentile_rank(np.array([np.nan], np.float32), s)[0])


def test_noleap_doy_feb29_shares_feb28_and_no_shift_in_common_years():
    d = pd.DatetimeIndex(["2020-02-28", "2020-02-29", "2020-03-01", "2021-03-01", "2020-12-31", "2021-12-31"])
    assert list(C.noleap_doy(d)) == [59, 59, 60, 60, 365, 365]


def test_baselines_and_splits_are_leakage_free():
    cfg = load("anomaly")
    tr, va, te = cfg["splits"]["train"], cfg["splits"]["validation"], cfg["splits"]["test"]
    assert tr[1] < va[0] and va[1] < te[0]                              # chronological, non-overlapping
    m = cfg["baselines"]["model"]
    assert tr[0] <= m["start"] and m["end"] <= tr[1]                    # model baseline inside the training period
    y = np.arange(1979, 2027)
    s = split_of(y)
    assert set(s[(y >= 2018) & (y <= 2025)]) == {"test"} and set(s[y <= 2010]) == {"train"}


def test_severity_classes_follow_training_base_rates():
    s = RNG.normal(size=200_000)                                         # SYNTHETIC scores
    thr = severity_thresholds(s, load("anomaly")["severity"]["classes"])
    sev = severity_of(s, thr)
    rates = pd.Series(sev).value_counts(normalize=True)
    assert rates["normal"] == pytest.approx(0.90, abs=0.005)
    assert rates["extreme"] == pytest.approx(0.005, abs=0.001)
    assert list(thr) == ["mild", "moderate", "strong", "extreme"] and np.all(np.diff(list(thr.values())) > 0)


# ------------------------------------------------------------- statistical detectors
def test_statistical_scores_pick_the_extreme_variable():
    z = np.zeros((3, len(FEATS)), np.float32)
    z[1, 0], z[2, 3] = 4.0, -6.0                                         # SYNTHETIC anomalies
    assert list(zscore_score(z)) == [0.0, 4.0, 6.0]
    assert mad_score(z)[2] == 6.0
    p = np.full((2, len(FEATS)), 0.5)
    p[1, 2] = 0.01
    assert percentile_score(p)[0] == pytest.approx(0) and percentile_score(p)[1] == pytest.approx(-np.log10(0.02))


def test_model_matrix_imputes_sic_and_clips():
    z = np.zeros((1, len(FEATS)), np.float32)
    z[0, FEATS.index("sic")] = np.nan
    z[0, 0] = 50
    m = model_matrix(z)
    assert m[0, FEATS.index("sic")] == 0 and m[0, 0] == 8


def _synthetic_correlated(n=20_000, seed=1):
    r = np.random.default_rng(seed)
    a = r.normal(size=n)
    Z = r.normal(size=(n, len(FEATS))) * 0.6
    Z[:, 0], Z[:, 6] = a, 0.9 * a + 0.3 * r.normal(size=n)               # strongly correlated pair (like t2m ~ z500)
    return Z.astype(np.float32)


def test_mahalanobis_detects_covariance_break_that_zscore_misses():
    Z = _synthetic_correlated()
    moy = np.tile(np.arange(1, 13), len(Z) // 12 + 1)[:len(Z)]
    m = Mahalanobis().fit(Z, moy)
    x = np.zeros((2, len(FEATS)), np.float32)
    x[0, 0], x[0, 6] = 2.0, 1.8                                         # consistent with the correlation
    x[1, 0], x[1, 6] = 2.0, -1.8                                        # SYNTHETIC covariance break
    s = m.score(x, np.array([1, 1]))
    assert s[1] > 2 * s[0]
    assert zscore_score(x)[0] == zscore_score(x)[1]


@pytest.mark.parametrize("kind,params", [("isolation_forest", {"n_estimators": 100, "max_samples": 256}),
                                         ("lof", {"n_neighbors": 20}), ("ocsvm", {"nu": 0.05, "gamma": "scale"})])
def test_ml_detectors_recover_synthetic_injections(kind, params):
    from sklearn.metrics import average_precision_score
    Z = _synthetic_correlated(6000)
    m = SkModel(kind, params, n_fit=4000).fit(Z)
    test = _synthetic_correlated(2000, seed=2)
    lab = np.zeros(len(test), bool)
    lab[:40] = True
    test[:40, [1, 2, 3]] += 3.0                                          # SYNTHETIC 3-variable shift (5 sigma per dim)
    # note: a 1-variable spike in 9-D is a known weak spot of Isolation Forest (random feature choice); see ML04 docs
    assert average_precision_score(lab, m.score(test)) > 0.5


def test_isolation_forest_is_reproducible_with_fixed_seed():
    Z = _synthetic_correlated(3000)
    a = SkModel("isolation_forest", {"n_estimators": 50}).fit(Z).score(Z[:100])
    b = SkModel("isolation_forest", {"n_estimators": 50}).fit(Z).score(Z[:100])
    np.testing.assert_allclose(a, b, rtol=0, atol=1e-12)


def test_autoencoder_trains_and_scores_injection_higher():
    Z = _synthetic_correlated(4000)
    ae = Autoencoder(bottleneck=3, epochs=15).fit(Z, None, Z[:500])
    x = Z[:2].copy()
    x[1, 0], x[1, 6] = 3.0, -3.0                                        # SYNTHETIC covariance break
    s = ae.score(x)
    assert s[1] > s[0] and ae.best_epoch >= 1
    import pickle
    ae2 = pickle.loads(pickle.dumps(ae))
    np.testing.assert_allclose(ae2.score(x), s, rtol=1e-5)


# ------------------------------------------------------------- integration (built artefacts)
built = pytest.mark.skipif(not (FEATURES / "table.parquet").exists(), reason="ML-04 feature table not built")
modelled = pytest.mark.skipif(not (MODELS / "decision.json").exists(), reason="ML-04 models not fitted")


@built
def test_feature_table_alignment_and_coordinates():
    df = pd.read_parquet(FEATURES / "table.parquet")
    z = np.load(FEATURES / "z.npy", mmap_mode="r")
    assert len(df) == z.shape[0] and z.shape[1] == len(FEATS)
    assert df["lat"].between(-87.5, -50).all() and df["lon"].between(0, 357.5).all()
    assert df.groupby("month").size().nunique() == 1                    # every month has the full grid
    tr = df[(df["split"] == "train") & df["atm_valid"]]
    zt = np.asarray(z[tr.index.values[::50]])
    assert abs(np.nanmean(zt[:, 0])) < 0.15                              # z of t2m ~ centred inside the training baseline
    assert not df.loc[df["month"] >= "2026-04", "atm_valid"].any()       # NCEP R1 record ends 2026-03-17


@built
def test_quality_report_ranges():
    from aethentra.anomaly.paths import PROCESSED
    q = json.loads((PROCESSED / "quality_report.json").read_text())
    assert all(v["range_ok"] for v in q["variables"].values())
    assert q["variables"]["t2m"]["last"] == "2026-03-17"


@modelled
def test_decision_frozen_and_single_test():
    d = json.loads((MODELS / "decision.json").read_text())
    assert d["selected_multivariate"] not in ("zscore", "percentile", "mad")
    if (METRICS / "test.json").exists():
        t = json.loads((METRICS / "test.json").read_text())
        assert t["decision_frozen_utc"] == d["frozen_utc"] and t["evaluated_utc"] > d["frozen_utc"]


@modelled
def test_display_resampling_and_regions():
    from aethentra.anomaly.export import to_3412
    from aethentra.anomaly.products import regions
    a = np.arange(16 * 144, dtype=np.float32).reshape(16, 144)
    b = to_3412(a)
    assert b.shape == (332, 316) and np.isfinite(b).mean() > 0.3
    r = regions()
    assert (r != "").all() and {"east_antarctica", "weddell", "ross"} <= set(r.ravel())


@modelled
def test_api_endpoints():
    from fastapi.testclient import TestClient
    from api.main import app
    c = TestClient(app)
    assert c.get("/api/ml04/health").status_code == 200
    assert c.get("/api/ml04/anomalies?start=2026-13").status_code == 422
    if (OUTPUTS / "anomalies_monthly_1991-2020.nc").exists():
        r = c.get("/api/ml04/spatial-data?month=2022-03&variable=t2m&field=z").json()
        assert len(r["values"]) == 16 and len(r["values"][0]) == 144
        obs = {"month": "2022-03", "latitude": -75.1, "longitude": 123.3, "t2m": -30.0, "slp": 1000, "wspd": 5, "rhum": 70,
               "prate": 0.2, "tcdc": 40, "z500": 5000}
        r = c.post("/api/ml04/detect", json={"observations": [obs]})
        assert r.status_code == 200 and r.json()["results"][0]["variables"]["t2m"]["z"] is not None
        bad = dict(obs, t2m=80)
        assert c.post("/api/ml04/detect", json={"observations": [bad]}).status_code == 422
