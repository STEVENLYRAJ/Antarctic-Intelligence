"""Classify one Sentinel-1 EW HH scene:  python scripts/ml03/predict.py --scene-id S1A_EW_GRDM_1SSH_...  (writes outputs/ml03/segmentation/<id>/)"""
import argparse
import json

import _boot

ap = argparse.ArgumentParser()
ap.add_argument("--scene-id", required=True)
a = ap.parse_args()
log = _boot.setup("predict")
from aethentra.sar.inference import SEG_DIR, classify_scene  # noqa: E402

r = classify_scene(a.scene_id)
print(json.dumps(json.loads((SEG_DIR / a.scene_id / "metadata.json").read_text()), indent=1)[:2500])
