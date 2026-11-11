"""ML-03 stages:  python scripts/ml03/train.py prepare|samples|baselines|tiles|unet|validate|select|final|test"""
import argparse
import json

import _boot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["prepare", "samples", "baselines", "tiles", "unet", "validate", "select", "final", "test"])
    ap.add_argument("--workers", type=int, default=3)          # commit memory is the limit (small page file on C:)
    a = ap.parse_args()
    _boot.setup(f"train_{a.stage}")
    from aethentra.sar import dataset as D, training as T

    if a.stage == "prepare":
        c = D.prepare_all(a.workers)
        print(c.processing_status.str[:9].value_counts().to_dict()); print(D.usable(c).groupby("split").size().to_dict())
    elif a.stage == "samples":
        print(D.pixel_samples(a.workers))
    elif a.stage == "tiles":
        slope = json.loads((T.CKPT / "threshold.meta.json").read_text())["slope_db_per_deg"]   # fitted on train samples only
        print(D.build_tiles(slope, a.workers))
    else:
        fn = {"baselines": T.train_baselines, "unet": T.train_unets, "validate": T.validate_candidates, "select": T.select,
              "final": T.final_refit, "test": T.test_once}[a.stage]
        r = fn()
        flat = r if a.stage == "select" else {k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if not isinstance(vv, (dict, list))})
                                              for k, v in (r.get("metrics", r) if isinstance(r, dict) else {}).items()}
        print(json.dumps(flat, indent=1, default=str)[:4000])
    print("done", a.stage)


if __name__ == "__main__":          # required on Windows: process-pool workers re-import this module
    main()
