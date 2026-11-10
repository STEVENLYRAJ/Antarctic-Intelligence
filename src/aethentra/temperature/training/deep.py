"""ML-02 deep-learning addendum (U-Net), run after the tree-model selection and test were frozen.

    stacks -> train (train split, early stopping on validation) -> validate (full-grid, same metrics as the trees)
           -> decide (frozen addendum record, validation only) -> refit (train+validation, fixed epochs) -> test (once)

The frozen tree-model selection (selection_record.json) is NOT modified. The addendum decision record states, before the CNN
test evaluation, whether the CNN would replace the operational model; that decision uses validation metrics only.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from ..paths import METRICS, MODELS, PROCESSED, load
from .pipeline import CKPT, FINAL, _dump, evaluate_split, make_context, names_for, split_dates

LOG = logging.getLogger("aethentra.ml02.deep")
STACKS = PROCESSED / "cnn"
ARCH = {"base": 32, "depth": 4, "dropout": 0.1}
HP = {"epochs": 40, "lr": 1e-3, "weight_decay": 1e-4, "batch_size": 8, "patience": 8}
NAME, FINAL_NAME = "cnn_unet", "cnn_unet_final"


def _ctx_channels(source=None):
    from ..models.cnn import GridMap, dynamic_channels
    ctx = make_context(source)
    return ctx, dynamic_channels(names_for(ctx)), GridMap(ctx.cube.grid)


def build_stack(ctx, split: str, channels, gm) -> dict:
    """(n, C, H, W) float16 predictors + (n, H, W) float32 weekly-anomaly labels, via the tree models' feature code."""
    from ..models.cnn import dynamic_stack
    d = STACKS / ctx.cube.source
    d.mkdir(parents=True, exist_ok=True)
    meta_p = d / f"{split}.json"
    if meta_p.exists():
        return json.loads(meta_p.read_text())
    dates = split_dates(split, ctx.cube.source)
    X = np.lib.format.open_memmap(d / f"{split}_X.npy.part", "w+", np.float16, (len(dates), len(channels), *gm.shape))
    Y = np.lib.format.open_memmap(d / f"{split}_Y.npy.part", "w+", np.float32, (len(dates), *gm.shape))
    for i, t in enumerate(dates):
        F = ctx.features(t)
        X[i] = dynamic_stack(F, channels, gm).astype(np.float16)
        Y[i] = gm.to_grid(ctx.labels(t)[1])
        if i % 100 == 0:
            LOG.info("stack %s %d/%d", split, i, len(dates))
    X.flush(); Y.flush(); del X, Y
    for k in ("X", "Y"):
        (d / f"{split}_{k}.npy.part").replace(d / f"{split}_{k}.npy")
    meta = {"split": split, "n": len(dates), "dates": [str(t.date()) for t in dates], "channels": channels, "shape": list(gm.shape)}
    meta_p.write_text(json.dumps(meta))
    return meta


def _open(source, split):
    d = STACKS / source
    return np.load(d / f"{split}_X.npy", mmap_mode="r"), np.load(d / f"{split}_Y.npy", mmap_mode="r")


def stage_stacks(source=None):
    ctx, ch, gm = _ctx_channels(source)
    return {s: build_stack(ctx, s, ch, gm)["n"] for s in ("train", "validation")}


def _norm(X, seed=42, n=300):
    idx = np.sort(np.random.default_rng(seed).choice(len(X), min(n, len(X)), replace=False))
    s = np.asarray(X[idx], np.float32)
    m = np.nanmean(s, axis=(0, 2, 3))
    sd = np.nanstd(s, axis=(0, 2, 3))
    return m, np.where(sd > 1e-6, sd, 1.0)


def _datasets(ctx, ch, gm, splits, mean, std):
    import torch.utils.data as tud

    from ...models.unet import StackDataset
    from ..models.cnn import static_stack
    st = static_stack(ctx, gm)
    area = gm.to_grid(ctx.area / ctx.area.mean(), fill=0.0)
    parts = [StackDataset(*_open(ctx.cube.source, s), st, mean, std, area, ch.index("anom_w1")) for s in splits]
    return parts[0] if len(parts) == 1 else tud.ConcatDataset(parts), st


def _save(net, directory, name, meta):
    import torch
    directory.mkdir(parents=True, exist_ok=True)
    torch.save(net.state_dict(), directory / f"{name}.pt")
    _dump(meta, directory / f"{name}.meta.json")


def train(source=None):
    from ...models.unet import UNet, fit
    if (CKPT / f"{NAME}.meta.json").exists():
        return json.loads((CKPT / f"{NAME}.meta.json").read_text())
    cfg = load("training")
    ctx, ch, gm = _ctx_channels(source)
    stage_stacks(source)
    mean, std = _norm(_open(ctx.cube.source, "train")[0], cfg["seed"])
    tr, st = _datasets(ctx, ch, gm, ["train"], mean, std)
    va, _ = _datasets(ctx, ch, gm, ["validation"], mean, std)
    cin = len(ch) + st.shape[0] + 1
    net = UNet(cin, **ARCH)
    rec = fit(net, tr, va, seed=cfg["seed"], log_path=METRICS / f"{NAME}_history.json", **HP)
    meta = {"name": NAME, "kind": "unet", "in_channels": cin, "architecture": ARCH, "hyperparameters": HP, "dynamic_channels": ch,
            "static_channels": ["lat", "lon_sin", "lon_cos", "elevation_m", "dist_coast_km", "land", "coastal"],
            "extra_channels": ["input_valid_mask"], "norm_mean": mean.tolist(), "norm_std": std.tolist(),
            "norm_fitted_on": "train split (300 random issue dates)", "train_dates": len(tr), "validation_dates": len(va),
            "train_period": cfg["splits"]["train"], "early_stopping": "validation area-weighted RMSE", "seed": cfg["seed"],
            "source": ctx.cube.source, "grid_shape": list(gm.shape), "target": "weekly mean T2m anomaly (degC), t+1..t+7",
            "loss": "area-weighted masked MSE", **{k: v for k, v in rec.items() if k != "history"}}
    _save(net, CKPT, NAME, meta)
    return meta


def validate(source=None):
    from ..models.cnn import CNNModel
    out = METRICS / "validation_cnn" / "summary.json"
    if out.exists():
        return json.loads(out.read_text())
    ctx = make_context(source)
    return evaluate_split(ctx, split_dates("validation"), {NAME: CNNModel.load(CKPT, NAME, ctx)}, "validation_cnn",
                          baselines=("persistence", "damped_persistence"))


def decide():
    """Validation-only comparison of the U-Net against the frozen selection; written before any CNN test evaluation."""
    p = METRICS / "addendum_cnn_decision_record.json"
    if p.exists():
        return json.loads(p.read_text())
    if (METRICS / "test_cnn_addendum" / "summary.json").exists():
        raise RuntimeError("CNN test already evaluated; decision must precede it")
    cfg = load("training")
    sel = json.loads((METRICS / "selection_record.json").read_text())
    best = sel["selected_model"]
    src = "validation_tuned" if best == "lgbm_tuned" else "validation_candidates"
    ref = json.loads((METRICS / src / "summary.json").read_text())["metrics"][best]
    cnn = json.loads((METRICS / "validation_cnn" / "summary.json").read_text())["metrics"][NAME]
    comp, wins = {}, 0
    for reg, met, d in cfg["selection_metrics"]:
        a, b = cnn[reg][met], ref[reg][met]
        better = (a < b) if d == "min" else (a > b)
        wins += better
        comp[f"{reg}:{met}"] = {NAME: a, best: b, "cnn_better": bool(better)}
    replace = wins == len(cfg["selection_metrics"])
    rec = {"frozen_tree_selection": best, "frozen_tree_selection_utc": sel["frozen_utc"], "comparison_on_validation": comp,
           "cnn_better_on": f"{wins}/{len(comp)} selection metrics",
           "rule": "the U-Net replaces the operational model only if it is better on ALL validation selection metrics",
           "cnn_replaces_operational_model": replace,
           "context": "Addendum after the tree-model test evaluation; the CNN test result is reported for comparison and is not used "
                      "to choose between models.", "test_set_accessed_before_decision_for_cnn": False,
           "frozen_utc": pd.Timestamp.now(tz="UTC").isoformat()}
    _dump(rec, p)
    return rec


def refit(source=None):
    from ...models.unet import UNet, fit
    if (FINAL / f"{FINAL_NAME}.meta.json").exists():
        return json.loads((FINAL / f"{FINAL_NAME}.meta.json").read_text())
    if not (METRICS / "addendum_cnn_decision_record.json").exists():
        raise RuntimeError("decision record missing")
    cfg = load("training")
    ctx, ch, gm = _ctx_channels(source)
    m0 = json.loads((CKPT / f"{NAME}.meta.json").read_text())
    mean, std = np.asarray(m0["norm_mean"], np.float32), np.asarray(m0["norm_std"], np.float32)
    ds, st = _datasets(ctx, ch, gm, ["train", "validation"], mean, std)
    net = UNet(m0["in_channels"], **ARCH)
    n_ep = int(m0["best_epoch"])
    rec = fit(net, ds, None, fixed_epochs=n_ep, seed=cfg["seed"], log_path=METRICS / f"{FINAL_NAME}_history.json",
              **{k: v for k, v in HP.items() if k not in ("epochs", "patience")})
    meta = {**m0, "name": FINAL_NAME, "train_period": [cfg["splits"]["train"][0], cfg["splits"]["validation"][1]],
            "train_dates": len(ds), "validation_dates": 0, "early_stopping": f"none (fixed {n_ep} epochs = best epoch of {NAME})",
            "norm_fitted_on": m0["norm_fitted_on"] + " (reused from cnn_unet)", "selected_from": NAME,
            **{k: v for k, v in rec.items() if k != "history"}}
    meta["best_val_metric"] = None
    _save(net, FINAL, FINAL_NAME, meta)
    return meta


def test_once(source=None):
    from ..models.cnn import CNNModel
    out = METRICS / "test_cnn_addendum" / "summary.json"
    if out.exists():
        raise RuntimeError("CNN test evaluation already exists; refusing to re-run.")
    dec = METRICS / "addendum_cnn_decision_record.json"
    if not dec.exists():
        raise RuntimeError("No frozen addendum decision record")
    ctx = make_context(source)
    res = evaluate_split(ctx, split_dates("test"), {FINAL_NAME: CNNModel.load(FINAL, FINAL_NAME, ctx)}, "test_cnn_addendum", baselines=())
    tree = json.loads((METRICS / "test_final" / "summary.json").read_text())["metrics"]
    res["tree_final_model_test_metrics_for_reference"] = tree["final_model"]
    res["evaluated_utc"] = pd.Timestamp.now(tz="UTC").isoformat()
    res["decision_record_frozen_utc"] = json.loads(dec.read_text())["frozen_utc"]
    _dump(res, out)
    return res
