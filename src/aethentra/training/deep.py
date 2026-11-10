"""ML-01 deep-learning addendum (U-Net on gridded SIC + atmosphere predictor stacks), after the tree selection/test were frozen.

    stacks -> train (1979-2015, early stopping on 2016-2020 MAE) -> validate (full grids, same metrics as the trees)
           -> decide (frozen addendum record, validation only) -> refit (1979-2020, fixed epochs, climatology refitted on
              train+validation exactly like final_refit) -> test (once)

The U-Net predicts the residual (target week mean - persistence) on the same active cells as the tree models; persistence /
climatological fallback elsewhere; output clipped to 0-100 %. selection_record.json is NOT modified.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from ..config import PROCESSED_DIR, load
from ..features.build import STATIC_FEATURES, feature_names, issue_dates
from ..models.tree_models import fallback
from .pipeline import CKPT, FINAL, METRICS, _dump, evaluate_split, make_context, split_dates

LOG = logging.getLogger("aethentra.deep")
STACKS = PROCESSED_DIR / "cnn"
ARCH = {"base": 32, "depth": 4, "dropout": 0.1}
HP = {"epochs": 40, "lr": 1e-3, "weight_decay": 1e-4, "batch_size": 8, "patience": 8, "loss": "l1"}
NAME, FINAL_NAME = "cnn_unet_residual", "cnn_unet_final"
STATIC_SCALE = {"dist_coast_km": (0.0, 500.0), "lat": (-65.0, 10.0), "lon_sin": (0.0, 1.0), "lon_cos": (0.0, 1.0)}


def channels(with_atm: bool) -> list[str]:
    return [n for n in feature_names(with_atm) if n not in set(STATIC_FEATURES) | {"month"}]


def _ctx(period: str):
    cfg = load("training")
    t0, t1 = cfg["splits"]["train"]
    if period == "trainval":
        t1 = cfg["splits"]["validation"][1]
    ctx = make_context(t0, t1)
    return ctx, channels(ctx.atmos is not None)


def static_stack(ctx) -> np.ndarray:
    st = {"dist_coast_km": ctx.dist_coast, "lat": ctx.lat, "lon_sin": ctx.lon_sin, "lon_cos": ctx.lon_cos}
    out = [np.nan_to_num((st[k] - a) / s) for k, (a, s) in STATIC_SCALE.items()]
    return np.stack(out + [ctx.ocean.astype(np.float32)]).astype(np.float32)


def residual_target(ctx, F, t) -> np.ndarray:
    y, _ = ctx.target(t)
    m = ctx.active_mask(F) & np.isfinite(F["sic_d0"]) & np.isfinite(y)
    return np.where(m, y - F["sic_d0"], np.nan).astype(np.float32)


def build_stack(ctx, ch, dates, tag) -> dict:
    d = STACKS
    d.mkdir(parents=True, exist_ok=True)
    meta_p = d / f"{tag}.json"
    if meta_p.exists():
        return json.loads(meta_p.read_text())
    shape = ctx.ocean.shape
    X = np.lib.format.open_memmap(d / f"{tag}_X.npy.part", "w+", np.float16, (len(dates), len(ch), *shape))
    Y = np.lib.format.open_memmap(d / f"{tag}_Y.npy.part", "w+", np.float32, (len(dates), *shape))
    for i, t in enumerate(dates):
        F = ctx.features(t)
        X[i] = np.stack([F[k] for k in ch]).astype(np.float16)
        Y[i] = residual_target(ctx, F, t)
        if i % 100 == 0:
            LOG.info("stack %s %d/%d", tag, i, len(dates))
    X.flush(); Y.flush(); del X, Y
    for k in ("X", "Y"):
        (d / f"{tag}_{k}.npy.part").replace(d / f"{tag}_{k}.npy")
    meta = {"tag": tag, "n": len(dates), "dates": [str(t.date()) for t in dates], "channels": ch, "shape": list(shape),
            "climatology_period": list(ctx.clim.period)}
    meta_p.write_text(json.dumps(meta))
    return meta


def _open(tag):
    return np.load(STACKS / f"{tag}_X.npy", mmap_mode="r"), np.load(STACKS / f"{tag}_Y.npy", mmap_mode="r")


def stage_stacks():
    ctx, ch = _ctx("train")
    return {s: build_stack(ctx, ch, split_dates(s), s)["n"] for s in ("train", "validation")}


def _norm(X, seed=42, n=300):
    idx = np.sort(np.random.default_rng(seed).choice(len(X), min(n, len(X)), replace=False))
    s = np.asarray(X[idx], np.float32)
    m, sd = np.nanmean(s, axis=(0, 2, 3)), np.nanstd(s, axis=(0, 2, 3))
    return m, np.where(sd > 1e-6, sd, 1.0)


def _dataset(ctx, ch, tags, mean, std):
    import torch.utils.data as tud

    from ..models.unet import StackDataset
    st = static_stack(ctx)
    area = np.where(ctx.ocean, ctx.area / ctx.area[ctx.ocean].mean(), 0.0).astype(np.float32)
    parts = [StackDataset(*_open(t), st, mean, std, area, ch.index("sic_d0")) for t in tags]
    return (parts[0] if len(parts) == 1 else tud.ConcatDataset(parts)), st


def _save(net, directory, name, meta):
    import torch
    directory.mkdir(parents=True, exist_ok=True)
    torch.save(net.state_dict(), directory / f"{name}.pt")
    _dump(meta, directory / f"{name}.meta.json")


class CNNResidualModel:
    """U-Net with the ``predict_grid`` interface of ``TreeModel`` (residual over persistence, active cells only)."""

    def __init__(self, net, meta, static):
        self.net, self.meta, self.static = net, meta, static
        self.channels, self.name = meta["dynamic_channels"], meta["name"]
        self.mean = np.asarray(meta["norm_mean"], np.float32)[:, None, None]
        self.std = np.asarray(meta["norm_std"], np.float32)[:, None, None]
        self.vc = self.channels.index("sic_d0")

    @classmethod
    def load(cls, directory, name, ctx):
        import torch

        from ..models.unet import UNet
        meta = json.loads((directory / f"{name}.meta.json").read_text())
        net = UNet(meta["in_channels"], **meta["architecture"])
        net.load_state_dict(torch.load(directory / f"{name}.pt", map_location="cpu", weights_only=True))
        net.to("cuda" if torch.cuda.is_available() else "cpu")
        return cls(net, meta, static_stack(ctx))

    def predict_grid(self, F: dict, active: np.ndarray, clip: bool = True):
        from ..models.unet import predict
        x = np.stack([F[k] for k in self.channels]).astype(np.float16).astype(np.float32)   # same precision as training stacks
        valid = np.isfinite(x[self.vc])
        x = np.concatenate([np.nan_to_num((x - self.mean) / self.std), self.static, valid[None].astype(np.float32)], 0)
        res = predict(self.net, x)
        base = fallback(F["sic_d0"].copy(), F)
        m = active & np.isfinite(F["sic_d0"])
        raw = F["sic_d0"] + res
        info = {"model_cells": int(m.sum()), "pre_clip_below_0": int((raw[m] < 0).sum()), "pre_clip_above_100": int((raw[m] > 100).sum())}
        out = np.where(m, np.clip(raw, 0, 100) if clip else raw, base)
        return out.astype(np.float32), info


def train():
    from ..models.unet import UNet, fit
    if (CKPT / f"{NAME}.meta.json").exists():
        return json.loads((CKPT / f"{NAME}.meta.json").read_text())
    cfg = load("training")
    stage_stacks()
    ctx, ch = _ctx("train")
    mean, std = _norm(_open("train")[0], cfg["seed"])
    tr, st = _dataset(ctx, ch, ["train"], mean, std)
    va, _ = _dataset(ctx, ch, ["validation"], mean, std)
    cin = len(ch) + st.shape[0] + 1
    net = UNet(cin, **ARCH)
    rec = fit(net, tr, va, seed=cfg["seed"], log_path=METRICS / f"{NAME}_history.json", **HP)
    meta = {"name": NAME, "kind": "unet", "target_mode": "residual", "in_channels": cin, "architecture": ARCH, "hyperparameters": HP,
            "dynamic_channels": ch, "static_channels": list(STATIC_SCALE) + ["ocean"], "extra_channels": ["input_valid_mask"],
            "norm_mean": mean.tolist(), "norm_std": std.tolist(), "norm_fitted_on": "train split (300 random issue dates)",
            "train_dates": len(tr), "validation_dates": len(va), "train_period": cfg["splits"]["train"],
            "climatology_period": list(ctx.clim.period), "early_stopping": "validation area-weighted MAE of the residual (active cells)",
            "seed": cfg["seed"], "target": "weekly mean SIC (t+1..t+7) - persistence, percent", "loss": "area-weighted masked L1",
            **{k: v for k, v in rec.items() if k != "history"}}
    _save(net, CKPT, NAME, meta)
    return meta


def validate():
    out = METRICS / "validation_cnn" / "summary.json"
    if out.exists():
        return json.loads(out.read_text())
    ctx, _ = _ctx("train")
    return evaluate_split(ctx, split_dates("validation"), {NAME: CNNResidualModel.load(CKPT, NAME, ctx)},
                          baselines=("persistence",), tag="validation_cnn")


def decide():
    p = METRICS / "addendum_cnn_decision_record.json"
    if p.exists():
        return json.loads(p.read_text())
    if (METRICS / "test_cnn_addendum" / "summary.json").exists():
        raise RuntimeError("CNN test already evaluated; decision must precede it")
    sel = json.loads((METRICS / "selection_record.json").read_text())
    ref = next(r for r in sel["validation_table"] if r["method"] == sel["selected_model"])
    g = json.loads((METRICS / "validation_cnn" / "summary.json").read_text())["metrics"][NAME]
    cnn = {"siz_mae": g["seasonal_ice_zone"]["mae_pp"], "siz_rmse": g["seasonal_ice_zone"]["rmse_pp"],
           "iiee": g["all"]["iiee_mean_km2"], "extent_mae": g["all"]["extent_mae_km2"]}
    comp = {k: {NAME: cnn[k], sel["selected_model"]: ref[k], "cnn_better": bool(cnn[k] < ref[k])} for k in cnn}
    wins = sum(v["cnn_better"] for v in comp.values())
    rec = {"frozen_tree_selection": sel["selected_model"], "frozen_tree_selection_utc": sel["selection_utc"],
           "comparison_on_validation": comp, "cnn_better_on": f"{wins}/{len(comp)} selection criteria",
           "rule": "the U-Net replaces the operational model only if it is better on ALL validation selection criteria",
           "cnn_replaces_operational_model": wins == len(comp),
           "context": "Addendum after the tree-model test evaluation; the CNN test result is reported for comparison and is not used "
                      "to choose between models.", "test_set_accessed_before_decision_for_cnn": False,
           "frozen_utc": pd.Timestamp.now(tz="UTC").isoformat()}
    _dump(rec, p)
    return rec


def refit():
    from ..models.unet import UNet, fit
    if (FINAL / f"{FINAL_NAME}.meta.json").exists():
        return json.loads((FINAL / f"{FINAL_NAME}.meta.json").read_text())
    if not (METRICS / "addendum_cnn_decision_record.json").exists():
        raise RuntimeError("decision record missing")
    cfg = load("training")
    ctx, ch = _ctx("trainval")                                  # climatology refitted on 1979-2020, as final_refit does
    t0, v1 = cfg["splits"]["train"][0], cfg["splits"]["validation"][1]
    build_stack(ctx, ch, issue_dates(t0, v1), "trainval")
    m0 = json.loads((CKPT / f"{NAME}.meta.json").read_text())
    mean, std = _norm(_open("trainval")[0], cfg["seed"])
    ds, _ = _dataset(ctx, ch, ["trainval"], mean, std)
    net = UNet(m0["in_channels"], **ARCH)
    n_ep = int(m0["best_epoch"])
    rec = fit(net, ds, None, fixed_epochs=n_ep, seed=cfg["seed"], log_path=METRICS / f"{FINAL_NAME}_history.json",
              **{k: v for k, v in HP.items() if k not in ("epochs", "patience")})
    meta = {**m0, "name": FINAL_NAME, "train_period": [t0, v1], "train_dates": len(ds), "validation_dates": 0,
            "climatology_period": list(ctx.clim.period), "norm_mean": mean.tolist(), "norm_std": std.tolist(),
            "norm_fitted_on": "train+validation (300 random issue dates)", "selected_from": NAME,
            "early_stopping": f"none (fixed {n_ep} epochs = best epoch of {NAME})", **{k: v for k, v in rec.items() if k != "history"}}
    meta["best_val_metric"] = None
    _save(net, FINAL, FINAL_NAME, meta)
    return meta


def test_once():
    out = METRICS / "test_cnn_addendum" / "summary.json"
    if out.exists():
        raise RuntimeError("CNN test evaluation already exists; refusing to re-run.")
    dec = METRICS / "addendum_cnn_decision_record.json"
    if not dec.exists():
        raise RuntimeError("No frozen addendum decision record")
    ctx, _ = _ctx("trainval")
    res = evaluate_split(ctx, split_dates("test"), {FINAL_NAME: CNNResidualModel.load(FINAL, FINAL_NAME, ctx)}, baselines=(),
                         tag="test_cnn_addendum")
    res["tree_final_model_test_metrics_for_reference"] = json.loads((METRICS / "test_final" / "summary.json").read_text())["metrics"]["final_model"]
    res["evaluated_utc"] = pd.Timestamp.now(tz="UTC").isoformat()
    res["decision_record_frozen_utc"] = json.loads(dec.read_text())["frozen_utc"]
    _dump(res, out)
    return res
