"""Weekly sea-ice detection map from ALL Antarctic EW HH acquisitions of one week.
    python scripts/ml03/generate_weekly_map.py --week-start 2026-10-26 [--max-scenes 400]
"""
import argparse
import json

import _boot

ap = argparse.ArgumentParser()
ap.add_argument("--week-start", required=True)
ap.add_argument("--max-scenes", type=int, default=400)
ap.add_argument("--workers", type=int, default=8)
a = ap.parse_args()
log = _boot.setup("weekly")
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

import pandas as pd  # noqa: E402

from aethentra.sar import acquisition as A  # noqa: E402
from aethentra.sar.inference import bundle, classify_scene, composite, export_weekly  # noqa: E402

from aethentra.sar.paths import INTERIM  # noqa: E402

t0 = pd.Timestamp(a.week_start)
client = A._client()
cached = INTERIM / f"week_{a.week_start}_scenes.json"          # written by prefetch_week.py
if cached.exists():
    ids = json.loads(cached.read_text())
else:
    ids = []
    for k in range(7):                     # search day by day (scene window = the day)
        ids += [s["scene_id"] for s in A.search_scenes(t0 + pd.Timedelta(days=k), client, days=(0, 0), max_items=None)]
ids = sorted(set(ids))[: a.max_scenes]
log.info("week %s: %d EW HH acquisitions", a.week_start, len(ids))
def _dl(sid):
    try:
        A.download_scene(sid, client)
    except Exception as e:  # noqa: BLE001  (scene skipped later if its files are missing)
        log.warning("download %s failed: %s", sid, str(e)[:120])


with ThreadPoolExecutor(a.workers) as ex:              # downloads in parallel (network bound)
    list(ex.map(_dl, ids))
bundle()
res = []
for i, s in enumerate(ids):
    try:
        r = classify_scene(s)
        r.pop("prob")
        res.append(r)
    except Exception as e:  # noqa: BLE001
        log.warning("scene %s failed: %s", s, str(e)[:150])
    if i % 20 == 0:
        log.info("classified %d/%d", i, len(ids))
wk = composite(res, a.week_start)
md = export_weekly(wk, bundle()[1].get("model_version"))
print(json.dumps({k: v for k, v in md.items() if k != "acquisitions"}, indent=1))
