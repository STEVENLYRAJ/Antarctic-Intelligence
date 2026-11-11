"""ML-03 acquisition:  python scripts/ml03/download_data.py [--charts] [--catalogue] [--scenes] [--land] [--start 2018-01-01 --end 2026-11-09]"""
import argparse
import json

import _boot

ap = argparse.ArgumentParser()
for f in ("charts", "catalogue", "scenes", "land"):
    ap.add_argument(f"--{f}", action="store_true")
ap.add_argument("--start", default="2018-01-01")
ap.add_argument("--end", default="2026-11-09")
ap.add_argument("--workers", type=int, default=6)
a = ap.parse_args()
log = _boot.setup("download")
import pandas as pd  # noqa: E402

from aethentra.sar import acquisition as A  # noqa: E402
from aethentra.sar.paths import INTERIM  # noqa: E402

if a.land:
    print(json.dumps(A.acquire_land(), indent=1))
if a.charts:
    c = A.acquire_charts(a.start, a.end)
    print(f"charts: {len(c)} ({c.chart_date.min()} .. {c.chart_date.max()})")
if a.catalogue:
    charts = pd.read_csv(INTERIM / "chart_catalogue.csv")
    charts = charts[(charts.chart_date >= a.start) & (charts.chart_date <= a.end)]
    cat = A.build_catalogue(charts, workers=a.workers)
    print(cat.groupby("split").agg(scenes=("scene_id", "count"), charts=("chart_date", "nunique")).to_string())
if a.scenes:
    cat = pd.read_csv(INTERIM / "scene_catalogue.csv")
    st = A.download_scenes(cat.scene_id.tolist(), workers=a.workers)
    cat["download_status"] = cat.scene_id.map(dict(zip(st.scene_id, st.status)))
    cat.to_csv(INTERIM / "scene_catalogue.csv", index=False)
    print(st.status.value_counts().to_dict())
