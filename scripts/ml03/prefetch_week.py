"""Download (no classification) all EW HH acquisitions of one week:  python scripts/ml03/prefetch_week.py --week-start 2026-11-02"""
import argparse
import json

import _boot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week-start", required=True)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    log = _boot.setup("prefetch_week")
    from concurrent.futures import ThreadPoolExecutor

    import pandas as pd

    from aethentra.sar import acquisition as A
    from aethentra.sar.paths import INTERIM
    client = A._client()
    t0 = pd.Timestamp(a.week_start)
    rows = []
    for k in range(7):
        rows += A.search_scenes(t0 + pd.Timedelta(days=k), client, days=(0, 0), max_items=None)
    ids = sorted({r["scene_id"] for r in rows})
    (INTERIM / f"week_{a.week_start}_scenes.json").write_text(json.dumps(ids))
    log.info("week %s: %d acquisitions", a.week_start, len(ids))
    import time

    def one(sid):                       # transient network / COG read errors: retry, then skip the scene (logged)
        for k in range(3):
            try:
                A.download_scene(sid, client)
                return True
            except Exception as e:  # noqa: BLE001
                log.warning("scene %s attempt %d failed: %s", sid, k + 1, str(e)[:120])
                time.sleep(10 * (k + 1))
        return False
    with ThreadPoolExecutor(a.workers) as ex:
        ok = sum(ex.map(one, ids))
    print({"week": a.week_start, "acquisitions": len(ids), "downloaded": ok, "failed": len(ids) - ok})


if __name__ == "__main__":
    main()
