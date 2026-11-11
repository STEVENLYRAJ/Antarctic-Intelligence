"""ML-04 end-to-end driver (fail-fast; each stage is resumable).

    python scripts/ml04/run_all.py                    # all stages
    python scripts/ml04/run_all.py --from features    # resume
    python scripts/ml04/run_all.py --only preprocess --vars t2m slp

Stages: download, preprocess, climatology, features, fit, validate, test, score, products, export, store.
The 'test' stage runs once (single-test rule); it is skipped if experiments/ml04/metrics/test.json exists.
"""
import argparse
import datetime as dt
import json
import time

from _boot import setup

log = setup("run_all")
STAGES = ["download", "preprocess", "climatology", "features", "fit", "validate", "test", "score", "products", "export", "store"]


def stage_download(a):
    from aethentra.anomaly.acquisition import acquire
    r = acquire(4)
    failed = [x["file"] for x in r if x["status"] == "failed"]
    if failed:
        raise RuntimeError(f"download failed: {failed}")


def stage_preprocess(a):
    from aethentra.anomaly import preprocessing as P
    for v in [x for x in (a.vars or P.ATM_VARS) if x in P.ATM_VARS]:
        log.info("daily %s: %s", v, P.build_daily_atm(v, force=a.force))
    if not a.vars or "sic" in a.vars:
        log.info("daily sic: %s", P.build_daily_sic(force=a.force))
    if not a.vars:
        log.info("monthly: %s", P.build_monthly(force=a.force))
        log.info("native sic monthly: %s", P.build_native_sic_monthly(force=a.force))
        P.extent_indices(force=a.force)
        rep = P.quality_report()
        log.info("quality: %s", json.dumps({k: (v["last"], v["range_ok"]) for k, v in rep["variables"].items()}))


def stage_climatology(a):
    from aethentra.anomaly import climatology as C
    for name in ("model", "reporting"):
        log.info("monthly clim %s: %s", name, C.build_monthly_climatology(name))
    log.info("daily clim reporting: %s", C.build_daily_climatology("reporting"))


def stage_features(a):
    from aethentra.anomaly.features import build_table
    df = build_table()
    log.info("feature table: %d rows", len(df))


def stage_fit(a):
    from aethentra.anomaly.training import fit_all
    log.info("fit: %s", fit_all())


def stage_validate(a):
    from aethentra.anomaly.training import validate
    log.info("decision: %s", json.dumps(validate()))


def stage_test(a):
    from aethentra.anomaly.paths import METRICS
    from aethentra.anomaly.training import test_once
    if (METRICS / "test.json").exists() and not a.force_test:
        log.info("test already evaluated once: skipped")
        return
    r = test_once(force=a.force_test)
    log.info("test: %s", json.dumps({k: round(v["pr_auc"], 3) for k, v in r["metrics"].items()}))


def stage_score(a):
    from aethentra.anomaly.training import score_all
    log.info("scored %d cell-months", len(score_all()))


def stage_products(a):
    from aethentra.anomaly import products as P
    log.info("reporting cube: %s", P.reporting_cube())
    t = P.scored_table()
    P.univariate_thresholds_model()
    e = P.explain_flagged(t)
    log.info("explained flagged: %d", len(e))
    log.info("compound co-occurrence rows: %d", len(P.compound_cooccurrence()))
    cl, ev = P.clusters_and_events(t)
    log.info("clusters %d, events %d", len(cl), len(ev))
    P.monthly_summary(t)
    P.seasonal_summary()
    P.extent_anomalies()
    log.info("t2m spells: %d", len(P.daily_t2m_spells()))
    log.info("stations: %s", json.dumps(P.station_agreement()))
    log.info("reference events: %s", json.dumps(P.literature_events(t), default=str))


def stage_export(a):
    import numpy as np
    import pandas as pd
    from aethentra.anomaly.export import export_month
    from aethentra.anomaly.paths import FEATURES
    tab = pd.read_parquet(FEATURES / "table.parquet", columns=["month", "atm_valid", "sic_available"])
    last_atm = tab.loc[tab["atm_valid"], "month"].max()
    last_sic = tab.loc[tab["sic_available"], "month"].max()
    for m in sorted({last_atm, last_sic} | set(a.months or [])):
        log.info("export %s: %s", m, export_month(m)["statistics"])
    del np


def stage_store(a):
    import xarray as xr
    import pandas as pd
    from aethentra.anomaly import products as P, storage as S
    from aethentra.anomaly.export import model_version
    from aethentra.anomaly.paths import FEATURES, OUTPUTS, PROCESSED
    S.register_models()
    S.register_datasets(json.loads((PROCESSED / "quality_report.json").read_text()))
    t = P.scored_table()
    e = pd.read_parquet(FEATURES / "explained_flagged.parquet")
    with xr.open_dataset(OUTPUTS / "anomalies_monthly_1991-2020.nc") as ds:
        log.info("events stored: %s", S.write_events(t, e, ds, model_version()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", choices=STAGES)
    ap.add_argument("--only", choices=STAGES)
    ap.add_argument("--vars", nargs="*")
    ap.add_argument("--months", nargs="*")
    ap.add_argument("--force", action="store_true", help="rebuild preprocessing outputs")
    ap.add_argument("--force-test", action="store_true", help="re-run the single test (logged in test.json)")
    a = ap.parse_args()
    todo = [a.only] if a.only else STAGES[STAGES.index(a.start):] if a.start else STAGES
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    done = []
    try:
        for s in todo:
            t0 = time.time()
            log.info("=== stage %s", s)
            globals()[f"stage_{s}"](a)
            done.append(s)
            log.info("=== stage %s done in %.0fs", s, time.time() - t0)
        status = "success"
    except Exception:
        status = "failed"
        log.exception("stage failed")
        raise
    finally:
        try:
            from aethentra.anomaly.storage import log_run
            log_run(started, status if done == todo else "failed", done, {"requested": todo})
        except Exception:  # noqa: BLE001
            log.warning("could not log run")
