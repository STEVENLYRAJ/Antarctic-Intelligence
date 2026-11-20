"""Export real Sentinel-1 / ML-03 image pairs for the frontend before-after comparison slider.

For the processed scenes in outputs/ml03/segmentation, pick the scenes with the most balanced ice / open-water
mix, then render on the identical EPSG:3031 400 m grid:
  sar.png    calibrated sigma0 HH in dB (greyscale, -28..-2 dB), from the ML-03 interim scene cache
  class.png  model classes: ice (white), open water (navy), uncertain (amber), invalid (transparent)
  prob.png   model sea-ice probability (0..1)
Nothing is synthetic: both images come from the pipeline's own files. Output: web/public/data/sar/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from aethentra.sar.paths import INTERIM  # noqa: E402

SEG = ROOT / "outputs" / "ml03" / "segmentation"
OUT = ROOT / "web" / "public" / "data" / "sar"
N = 4


def main() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cands = []
    for d in SEG.iterdir():
        m = d / "metadata.json"
        npz = INTERIM / "scenes" / f"{d.name}.npz"
        if not m.exists() or not npz.exists():
            continue
        md = json.loads(m.read_text())
        pc = md.get("pixel_counts", {})
        tot = pc.get("water", 0) + pc.get("ice", 0) + pc.get("uncertain", 0)
        if tot < 150_000:
            continue
        bal = min(pc.get("water", 0), pc.get("ice", 0)) / tot
        cands.append((bal, d, md))
    cands.sort(key=lambda x: -x[0])
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for bal, d, md in cands[:N]:
        z = np.load(INTERIM / "scenes" / f"{d.name}.npz")
        s0 = z["s0_db"]
        with xr.open_dataset(d / "segmentation.nc") as ds:
            cls = ds["sea_ice_class"].values
            prob = ds["sea_ice_probability"].values
            ice, water, unc, inv = (ds[k].values.astype(bool) for k in ("sea_ice_mask", "open_water_mask", "uncertain_mask", "invalid_mask"))
        if s0.shape != cls.shape:
            print("shape mismatch, skipped", d.name, s0.shape, cls.shape)
            continue
        ok = np.isfinite(s0) & ~inv
        rows, cols = np.where(ok)
        r0, r1, c0, c1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
        sl = (slice(r0, r1), slice(c0, c1))
        o = OUT / d.name
        o.mkdir(exist_ok=True)
        g = np.clip((s0[sl] + 28) / 26, 0, 1)
        rgba = np.dstack([g, g, g, ok[sl].astype(float)])
        plt.imsave(o / "sar.png", rgba)
        c = np.zeros(cls[sl].shape + (4,))
        c[water[sl]] = (0.04, 0.14, 0.32, 1)
        c[ice[sl]] = (0.93, 0.97, 1.0, 1)
        c[unc[sl]] = (1.0, 0.71, 0.28, 1)
        plt.imsave(o / "class.png", c)
        p = matplotlib.colormaps["Blues_r"](np.nan_to_num(prob[sl], nan=0))
        p[..., 3] = np.where(ok[sl], 1, 0)
        plt.imsave(o / "prob.png", p)
        pc = md["pixel_counts"]
        valid = pc["water"] + pc["ice"] + pc["uncertain"]
        index.append({"scene_id": d.name, "acquired": md["acquired"], "sensor": md.get("sensor"), "mode": md.get("mode"),
                      "polarization": md.get("polarization"), "resolution_m": md.get("resolution_m"),
                      "model_version": md.get("model_version"), "data_type": md.get("data_type"),
                      "fractions": {k: round(pc[k] / valid, 4) for k in ("ice", "water", "uncertain")},
                      "nominal_ice_area_km2": md.get("nominal_ice_area_km2"),
                      "width": int(c1 - c0), "height": int(r1 - r0),
                      "files": {k: f"/data/sar/{d.name}/{k}.png" for k in ("sar", "class", "prob")}})
        print("exported", d.name, round(bal, 3))
    (OUT / "index.json").write_text(json.dumps(index, indent=1))


if __name__ == "__main__":
    main()
