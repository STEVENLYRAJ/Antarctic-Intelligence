"""ML-03 dataset: preprocess + label every catalogued scene, pixel samples for the baselines, U-Net tiles per split.

The split is a property of the SCENE (via its chart date) and is fixed before tiling, so tiles of one scene never cross splits.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from .features import PIXEL_FEATURES, UNET_CHANNELS, scene_feature_maps
from .labels import ICE, INVALID, WATER, save_labels, scene_labels
from .paths import INTERIM, PROCESSED, load

LOG = logging.getLogger("aethentra.ml03.dataset")


def _prepare(row: dict) -> dict:
    from .preprocessing import process_scene
    sid = row["scene_id"]
    try:
        meta = process_scene(sid)
        from .preprocessing import load_scene
        scene, meta = load_scene(sid)
        lab, info = scene_labels(sid, row["chart_date"], scene, meta)
        save_labels(sid, lab, info)
        return {"scene_id": sid, "processing_status": "processed", "valid_fraction": meta["valid_fraction"],
                **{f"n_{k}": v for k, v in info["counts"].items()}, "chart_coverage": info["chart_coverage_of_valid_sar"]}
    except Exception as e:  # noqa: BLE001
        return {"scene_id": sid, "processing_status": f"failed: {str(e)[:150]}"}


def prepare_all(workers: int = 6) -> pd.DataFrame:
    cat = pd.read_csv(INTERIM / "scene_catalogue.csv")
    todo = cat[cat["download_status"] == "downloaded"]
    with ProcessPoolExecutor(workers) as ex:
        res = pd.DataFrame(list(ex.map(_prepare, todo[["scene_id", "chart_date"]].to_dict("records"), chunksize=4)))
    cat = cat.drop(columns=[c for c in res.columns if c != "scene_id" and c in cat.columns]).merge(res, on="scene_id", how="left")
    cat.to_csv(INTERIM / "scene_catalogue.csv", index=False)
    return cat


def usable(cat: pd.DataFrame) -> pd.DataFrame:
    """Scenes with enough chart-labelled water/ice pixels to be informative (rule fixed before any model is trained)."""
    ok = cat["processing_status"].eq("processed") & ((cat["n_water"] + cat["n_ice"]) >= 2000)
    return cat[ok]


# ------------------------------------------------------------------------------------------- pixel samples (baselines)
def _sample(args) -> pd.DataFrame | None:
    sid, split, n, seed = args
    from .labels import load_labels
    from .preprocessing import load_scene
    scene, meta = load_scene(sid)
    lab = load_labels(sid)
    F = scene_feature_maps(scene, meta, slope=0.0)
    rng = np.random.default_rng(seed)
    parts = []
    for c in (WATER, ICE):
        idx = np.flatnonzero(lab.ravel() == c)
        if idx.size:
            parts.append(rng.choice(idx, min(n, idx.size), replace=False))
    if not parts:
        return None
    idx = np.concatenate(parts)
    df = pd.DataFrame({k: F[k].ravel()[idx].astype(np.float32) for k in PIXEL_FEATURES + ["lon"]})
    df["label"] = lab.ravel()[idx]
    df["scene_id"], df["split"] = sid, split
    df["month"] = pd.Timestamp(meta["acquired"]).month
    return df


def pixel_samples(workers: int = 6) -> dict:
    cfg = load("training")
    cat = usable(pd.read_csv(INTERIM / "scene_catalogue.csv"))
    PROCESSED.mkdir(parents=True, exist_ok=True)
    jobs = [(r.scene_id, r.split, cfg["pixel_sample_per_scene"], cfg["seed"] + i) for i, r in enumerate(cat.itertuples())]
    with ProcessPoolExecutor(workers) as ex:
        dfs = [d for d in ex.map(_sample, jobs, chunksize=4) if d is not None]
    tab = pd.concat(dfs, ignore_index=True)
    tab.to_parquet(PROCESSED / "pixel_samples.parquet")
    out = tab.groupby(["split", "label"]).size().unstack().to_dict()
    (PROCESSED / "pixel_samples.json").write_text(json.dumps({"rows": len(tab), "by_split_label": {str(k): v for k, v in out.items()},
                                                              "features": PIXEL_FEATURES}, indent=1))
    return out


# ------------------------------------------------------------------------------------------- U-Net tiles
def _tiles(args):
    """Tiles of one scene written to a per-scene .npz (workers return only positions -> bounded parent memory)."""
    sid, slope, out_dir = args
    from .labels import load_labels
    from .preprocessing import load_scene
    f = out_dir / f"{sid}.npz"
    if f.exists():
        return sid, [tuple(x) for x in np.load(f)["pos"]]
    cfg = load("sar_preprocessing")["tiles"]
    scene, meta = load_scene(sid)
    lab = load_labels(sid)
    F = scene_feature_maps(scene, meta, slope=slope, glcm=False)
    n, s = cfg["size"], cfg["stride"]
    h, w = lab.shape
    X, Y, pos = [], [], []
    for i in range(0, max(h - n, 0) + 1, s):
        for j in range(0, max(w - n, 0) + 1, s):
            y = lab[i:i + n, j:j + n]
            if y.shape != (n, n) or np.isin(y, (WATER, ICE)).mean() < cfg["min_valid_fraction"]:
                continue
            X.append(np.stack([np.nan_to_num(F[k][i:i + n, j:j + n]).astype(np.float16) if k != "valid" else F["valid"][i:i + n, j:j + n].astype(np.float16)
                               for k in UNET_CHANNELS]))
            Y.append(y)
            pos.append((i, j))
    np.savez(f, X=np.stack(X) if X else np.zeros((0, len(UNET_CHANNELS), n, n), np.float16),
             Y=np.stack(Y) if Y else np.zeros((0, n, n), np.uint8), pos=np.array(pos, int).reshape(-1, 2))
    return sid, pos


def build_tiles(slope: float, workers: int = 6) -> dict:
    """Raw (un-normalised) tile channels per split; NaN stored as 0 + valid channel; normalisation fitted on train tiles.
    Per-scene tile files are concatenated into memory-mapped split arrays (never held in RAM at once)."""
    cat = usable(pd.read_csv(INTERIM / "scene_catalogue.csv"))
    d = PROCESSED / "tiles"
    sd = d / "scenes"
    sd.mkdir(parents=True, exist_ok=True)
    n = load("sar_preprocessing")["tiles"]["size"]
    out = {}
    for split in ("train", "validation", "test"):
        ids = cat.loc[cat["split"] == split, "scene_id"].tolist()
        with ProcessPoolExecutor(workers) as ex:
            res = list(ex.map(_tiles, [(s, slope, sd) for s in ids], chunksize=2))
        total = sum(len(p) for _, p in res)
        X = np.lib.format.open_memmap(d / f"{split}_X.npy", "w+", np.float16, (total, len(UNET_CHANNELS), n, n))
        Y = np.lib.format.open_memmap(d / f"{split}_Y.npy", "w+", np.uint8, (total, n, n))
        k, index = 0, []
        for sid, pos in res:
            if not pos:
                continue
            z = np.load(sd / f"{sid}.npz")
            X[k:k + len(pos)], Y[k:k + len(pos)] = z["X"], z["Y"]
            k += len(pos)
            index += [(sid, i, j) for i, j in pos]
        X.flush(); Y.flush(); del X, Y
        pd.DataFrame(index, columns=["scene_id", "row", "col"]).to_csv(d / f"{split}_index.csv", index=False)
        out[split] = {"tiles": total, "scenes": len({s for s, _, _ in index})}
    (d / "tiles.json").write_text(json.dumps({**out, "channels": UNET_CHANNELS, "incidence_slope_db_per_deg": slope}, indent=1))
    return out
