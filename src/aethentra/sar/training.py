"""ML-03 models, training, selection (validation only), final refit and the single test evaluation.

    samples -> threshold / rf / xgb -> tiles -> unet (bce, bce+dice) -> validate (full scenes) -> select (frozen)
            -> final refit (train+validation, fixed iterations/epochs) -> test (once; all candidates on the same test scenes)
"""
from __future__ import annotations

import json
import logging
import pickle
import time

import numpy as np
import pandas as pd

from .dataset import usable
from .evaluation import grouped, scene_record, summarize, true_pixel_area_km2
from .features import PIXEL_FEATURES, UNET_CHANNELS, scene_feature_maps, unet_input
from .labels import load_labels
from .paths import INTERIM, METRICS, MODELS, PROCESSED, load
from .preprocessing import load_scene

LOG = logging.getLogger("aethentra.ml03.training")
CKPT, FINAL = MODELS / "checkpoints", MODELS / "final"


def _dump(o, p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, indent=1, default=lambda x: x.item() if hasattr(x, "item") else str(x)))


def _samples():
    return pd.read_parquet(PROCESSED / "pixel_samples.parquet")


# ============================================================================== models (common interface: prob map)
class ThresholdModel:
    kind = "threshold"

    def __init__(self, slope=0.0, thr=-15.0, name="threshold"):
        self.slope, self.thr, self.name = slope, thr, name

    def fit(self, df):
        y = df["label"].to_numpy() == 1
        best = (-1, 0, 0)
        for b in np.arange(-0.40, 0.401, 0.02):
            s = df["s0"].to_numpy() + b * (df["inc"].to_numpy() - 35.0)
            for t in np.arange(-30, 0, 0.1):
                p = s > t
                ba = 0.5 * ((p & y).sum() / max(y.sum(), 1) + (~p & ~y).sum() / max((~y).sum(), 1))
                if ba > best[0]:
                    best = (ba, b, t)
        self.train_balanced_accuracy, self.slope, self.thr = best
        return self

    def prob_map(self, F):
        return np.where(F["valid"] > 0, (F["s0"] + self.slope * (F["inc"] - 35.0) > self.thr).astype(np.float32), np.nan)

    def meta(self):
        return {"kind": self.kind, "slope_db_per_deg": self.slope, "threshold_db": self.thr, "reference_incidence_deg": 35.0,
                "train_balanced_accuracy": self.train_balanced_accuracy}


class TabularModel:
    def __init__(self, kind, params, name):
        self.kind, self.params, self.name, self.model = kind, params, name, None

    def fit(self, tr, va=None, n_estimators=None, seed=42):
        X, y = tr[PIXEL_FEATURES].to_numpy(np.float32), (tr["label"] == 1).to_numpy()
        t0 = time.time()
        if self.kind == "random_forest":
            from sklearn.ensemble import RandomForestClassifier
            self.model = RandomForestClassifier(random_state=seed, **self.params).fit(np.nan_to_num(X, nan=-999), y)
            self.best_iteration = self.params["n_estimators"]
        else:
            import xgboost as xgb
            p = {k: v for k, v in self.params.items() if k not in ("n_estimators", "early_stopping_rounds")}
            n = n_estimators or self.params["n_estimators"]
            pos = y.mean()
            self.model = xgb.XGBClassifier(n_estimators=n, random_state=seed, scale_pos_weight=(1 - pos) / max(pos, 1e-6),
                                           early_stopping_rounds=self.params["early_stopping_rounds"] if va is not None else None, **p)
            ev = [(va[PIXEL_FEATURES].to_numpy(np.float32), (va["label"] == 1).to_numpy())] if va is not None else None
            self.model.fit(X, y, eval_set=ev, verbose=False)
            self.best_iteration = int(self.model.best_iteration + 1) if va is not None else n
        self.fit_seconds = time.time() - t0
        return self

    def prob_map(self, F):
        ok = F["valid"] > 0
        out = np.full(ok.shape, np.nan, np.float32)
        if ok.any():
            X = np.stack([F[k][ok] for k in PIXEL_FEATURES], 1).astype(np.float32)
            if self.kind == "random_forest":
                X = np.nan_to_num(X, nan=-999)
            out[ok] = self.model.predict_proba(X)[:, 1]
        return out

    def meta(self):
        imp = getattr(self.model, "feature_importances_", None)
        return {"kind": self.kind, "params": self.params, "best_iteration": self.best_iteration, "fit_seconds": self.fit_seconds,
                "features": PIXEL_FEATURES, "feature_importance": dict(zip(PIXEL_FEATURES, map(float, imp))) if imp is not None else None}


class UNetModel:
    kind = "unet"

    def __init__(self, net, norm, name, meta=None):
        self.net, self.norm, self.name, self._meta = net, norm, name, meta or {}

    def prob_map(self, F):
        import torch
        x = unet_input(F, self.norm)
        dev = next(self.net.parameters()).device
        self.net.eval()
        with torch.no_grad(), torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
            logit = self.net(torch.from_numpy(x[None]).to(dev)).float().cpu().numpy()[0, 0]
        return np.where(F["valid"] > 0, 1 / (1 + np.exp(-logit)), np.nan).astype(np.float32)

    def meta(self):
        return self._meta


def save_model(m, directory, extra=None):
    directory.mkdir(parents=True, exist_ok=True)
    meta = {"name": m.name, **m.meta(), **(extra or {})}
    if m.kind == "unet":
        import torch
        torch.save(m.net.state_dict(), directory / f"{m.name}.pt")
        meta["norm"] = m.norm
    else:
        with open(directory / f"{m.name}.pkl", "wb") as f:
            pickle.dump(m, f)
    _dump(meta, directory / f"{m.name}.meta.json")
    return meta


def load_model(directory, name):
    meta = json.loads((directory / f"{name}.meta.json").read_text())
    if meta["kind"] == "unet":
        import torch

        from ..models.unet import UNet
        net = UNet(len(UNET_CHANNELS), **meta["architecture"])
        net.load_state_dict(torch.load(directory / f"{name}.pt", map_location="cpu", weights_only=True))
        net.to("cuda" if torch.cuda.is_available() else "cpu")
        return UNetModel(net, {k: tuple(v) for k, v in meta["norm"].items()}, name, meta)
    with open(directory / f"{name}.pkl", "rb") as f:
        return pickle.load(f)


# ============================================================================== baselines
def train_baselines():
    cfg = load("training")
    s = _samples()
    tr, va = s[s.split == "train"], s[s.split == "validation"]
    out = {}
    th = ThresholdModel().fit(tr.sample(min(len(tr), 400_000), random_state=cfg["seed"]))
    out["threshold"] = save_model(th, CKPT, {"train_rows": len(tr)})
    rf = TabularModel("random_forest", cfg["random_forest"], "rf").fit(tr.sample(min(len(tr), 400_000), random_state=cfg["seed"]), seed=cfg["seed"])
    out["rf"] = save_model(rf, CKPT, {"train_rows": min(len(tr), 400_000)})
    xg = TabularModel("xgboost", cfg["xgboost"], "xgb").fit(tr, va, seed=cfg["seed"])
    out["xgb"] = save_model(xg, CKPT, {"train_rows": len(tr), "validation_rows": len(va)})
    _dump({k: {kk: vv for kk, vv in v.items() if kk != "feature_importance"} for k, v in out.items()}, METRICS / "baseline_training_records.json")
    return out


# ============================================================================== U-Net
class TileSet:
    def __init__(self, split, norm, augment=False, seed=0):
        d = PROCESSED / "tiles"
        self.X = np.load(d / f"{split}_X.npy", mmap_mode="r")
        self.Y = np.load(d / f"{split}_Y.npy", mmap_mode="r")
        self.norm, self.augment = norm, augment
        self.rng = np.random.default_rng(seed)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, i):
        import torch
        x = np.asarray(self.X[i], np.float32)
        v = x[UNET_CHANNELS.index("valid")] > 0
        for c, k in enumerate(UNET_CHANNELS):
            if k != "valid":
                m, s = self.norm[k]
                x[c] = np.where(v, (x[c] - m) / s, 0)
        y = np.asarray(self.Y[i])
        if self.augment:                      # SAR look direction / orbit geometry vary: ice-water contrast is orientation-free
            k = self.rng.integers(4)
            x, y = np.rot90(x, k, (1, 2)), np.rot90(y, k)
            if self.rng.random() < 0.5:
                x, y = x[:, :, ::-1], y[:, ::-1]
            x = x.copy()
            x[0] = x[0] +(self.rng.normal(0, 0.05) + self.rng.normal(0, 0.05, x[0].shape)) * (x[-1] > 0)
        return torch.from_numpy(np.ascontiguousarray(x)), torch.from_numpy(np.ascontiguousarray(y).astype(np.int64))


def tile_norm() -> dict:
    X = np.load(PROCESSED / "tiles" / "train_X.npy", mmap_mode="r")
    idx = np.random.default_rng(42).choice(len(X), min(2000, len(X)), replace=False)
    s = np.asarray(X[np.sort(idx)], np.float32)
    v = s[:, UNET_CHANNELS.index("valid")] > 0
    return {k: (float(s[:, c][v].mean()), float(s[:, c][v].std() + 1e-6)) for c, k in enumerate(UNET_CHANNELS) if k != "valid"}


def seg_loss(logit, y, dice_w):
    import torch
    import torch.nn.functional as Fn
    m = (y == 0) | (y == 1)
    t = (y == 1).float()
    lg = logit[:, 0]
    bce = (Fn.binary_cross_entropy_with_logits(lg, t, reduction="none") * m).sum() / m.sum().clamp_min(1)
    if dice_w <= 0:
        return bce
    p = torch.sigmoid(lg) * m
    dice = 1 - (2 * (p * t).sum() + 1) / (p.sum() + (t * m).sum() + 1)
    return (1 - dice_w) * bce + dice_w * dice


def _tile_iou(net, loader, dev):
    import torch
    net.eval()
    tp = fp = fn = tn = 0
    with torch.no_grad(), torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
        for x, y in loader:
            p = (net(x.to(dev)).float()[:, 0] > 0).cpu()
            m = (y == 0) | (y == 1)
            t = y == 1
            tp += int((p & t & m).sum()); fp += int((p & ~t & m).sum()); fn += int((~p & t & m).sum()); tn += int((~p & ~t & m).sum())
    return 0.5 * (tp / max(tp + fp + fn, 1) + tn / max(tn + fp + fn, 1))


def train_unet(name: str, dice_w: float, splits=("train",), fixed_epochs: int | None = None, norm=None):
    import torch
    from torch.utils.data import ConcatDataset, DataLoader

    from ..models.unet import UNet
    cfg = load("training")
    u = cfg["unet"]
    torch.manual_seed(cfg["seed"])
    norm = norm or tile_norm()
    ds = ConcatDataset([TileSet(s, norm, augment=True, seed=cfg["seed"]) for s in splits])
    tl = DataLoader(ds, batch_size=u["batch_size"], shuffle=True, num_workers=0, generator=torch.Generator().manual_seed(cfg["seed"]))
    vl = None if fixed_epochs else DataLoader(TileSet("validation", norm), batch_size=u["batch_size"])
    arch = {"base": u["base"], "depth": u["depth"], "dropout": u["dropout"]}
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    net = UNet(len(UNET_CHANNELS), **arch).to(dev)
    n_ep = fixed_epochs or u["epochs"]
    opt = torch.optim.AdamW(net.parameters(), lr=u["lr"], weight_decay=u["weight_decay"])
    sch = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=u["lr"], total_steps=n_ep * len(tl), pct_start=0.1)
    hist, best, best_state, best_ep, bad, t0 = [], -1, None, 0, 0, time.time()
    for ep in range(1, n_ep + 1):
        net.train()
        tot = 0.0
        for x, y in tl:
            x, y = x.to(dev), y.to(dev)
            with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
                lg = net(x)
            loss = seg_loss(lg.float(), y, dice_w)
            opt.zero_grad(set_to_none=True); loss.backward(); opt.step(); sch.step()
            tot += float(loss)
        rec = {"epoch": ep, "train_loss": tot / len(tl), "seconds": round(time.time() - t0, 1)}
        if vl is not None:
            rec["val_tile_miou"] = _tile_iou(net, vl, dev)
            if rec["val_tile_miou"] > best + 1e-4:
                best, best_ep, bad = rec["val_tile_miou"], ep, 0
                best_state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
            else:
                bad += 1
        hist.append(rec)
        LOG.info("%s epoch %s", name, rec)
        if vl is not None and bad >= u["patience"]:
            break
    if best_state is not None:
        net.load_state_dict(best_state)
    meta = {"kind": "unet", "architecture": arch, "channels": UNET_CHANNELS, "loss": "BCE" if dice_w <= 0 else f"(1-{dice_w})*BCE + {dice_w}*Dice",
            "label_encoding": "0 water, 1 ice; 2 uncertain and 255 invalid ignored in loss", "optimizer": "AdamW + OneCycle",
            "lr": u["lr"], "weight_decay": u["weight_decay"], "batch_size": u["batch_size"], "tile_size": 256,
            "augmentation": "rot90 x4, horizontal flip, sigma0 gain (0.05 sd) + pixel noise (0.05 sd) in normalised units",
            "epochs_run": len(hist), "best_epoch": best_ep or n_ep, "best_val_tile_miou": best if vl is not None else None,
            "train_splits": list(splits), "train_tiles": len(ds), "seconds": round(time.time() - t0, 1), "device": str(dev),
            "gpu": torch.cuda.get_device_name(0) if dev.type == "cuda" else None, "seed": cfg["seed"],
            "n_parameters": int(sum(p.numel() for p in net.parameters())), "history": hist}
    return UNetModel(net, norm, name, meta)


def train_unets():
    out = {}
    for name, dw in (("unet_bce", 0.0), ("unet_bce_dice", load("training")["unet"]["dice_weight"])):
        if (CKPT / f"{name}.meta.json").exists():
            continue
        m = train_unet(name, dw)
        out[name] = save_model(m, CKPT)
    return out


# ============================================================================== full-scene evaluation
def scene_ids(split: str) -> pd.DataFrame:
    return usable(pd.read_csv(INTERIM / "scene_catalogue.csv")).query("split == @split")


def evaluate(models: dict, split: str, tag: str, save_maps: bool = False) -> dict:
    cat = scene_ids(split)
    slope = json.loads((PROCESSED / "tiles" / "tiles.json").read_text())["incidence_slope_db_per_deg"]
    need_glcm = any(getattr(m, "kind", "") in ("random_forest", "xgboost") for m in models.values())
    rows, rel, t0 = [], {}, time.time()
    for i, r in enumerate(cat.itertuples()):
        scene, meta = load_scene(r.scene_id)
        lab, raw = load_labels(r.scene_id), load_labels(r.scene_id, raw=True)
        F = scene_feature_maps(scene, meta, slope=slope, glcm=need_glcm)
        area = true_pixel_area_km2(F["lat"], F["lon"], meta["resolution_m"])
        for name, m in models.items():
            prob = m.prob_map(F)
            pred = np.nan_to_num(prob) >= 0.5
            rec = scene_record(pred, prob if m.kind != "threshold" else None, lab, raw, scene["valid"], area, meta["resolution_m"])
            if "_reliability" in rec:
                rel[name] = rel.get(name, 0) + rec.pop("_reliability")
            rows.append({"model": name, "scene_id": r.scene_id, "chart_date": r.chart_date, "sector": r.sector,
                         "month": pd.Timestamp(r.acquired).month, **rec})
            if save_maps and name in save_maps:
                d = METRICS / tag / "maps"
                d.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(d / f"{r.scene_id}__{name}.npz", prob=prob.astype(np.float16))
        if i % 25 == 0:
            LOG.info("eval %s: %d/%d scenes %.0f s", tag, i, len(cat), time.time() - t0)
    df = pd.DataFrame(rows)
    seasons = {m: s for s, ms in load("evaluation")["seasons"].items() for m in ms}
    df["season"] = df["month"].map(seasons)
    out_dir = METRICS / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "per_scene.csv", index=False)
    res = {"tag": tag, "split": split, "n_scenes": int(cat.shape[0]), "first_chart": str(cat.chart_date.min()), "last_chart": str(cat.chart_date.max()),
           "seconds": round(time.time() - t0, 1), "label_source": "USNIC Antarctic charts (agreement, not independent ground truth)",
           "metrics": {m: summarize(g) for m, g in df.groupby("model")},
           "by_sector": {m: grouped(g, "sector") for m, g in df.groupby("model")},
           "by_season": {m: grouped(g, "season") for m, g in df.groupby("model")},
           "reliability": {m: {"bins": np.linspace(0, 1, 11).tolist(), "water_counts": h[:, 0].tolist(), "ice_counts": h[:, 1].tolist()}
                           for m, h in rel.items()}}
    _dump(res, out_dir / "summary.json")
    return res


def validate_candidates():
    names = ["threshold", "rf", "xgb", "unet_bce", "unet_bce_dice"]
    models = {n: load_model(CKPT, n) for n in names if (CKPT / f"{n}.meta.json").exists()}
    return evaluate(models, "validation", "validation_candidates")


# ============================================================================== selection / final / test
COMPLEXITY = {"threshold": 0, "rf": 1, "xgb": 1, "unet_bce": 2, "unet_bce_dice": 2}


def select():
    if (METRICS / "test_final" / "summary.json").exists():
        raise RuntimeError("test already evaluated; selection is frozen")
    v = json.loads((METRICS / "validation_candidates" / "summary.json").read_text())["metrics"]
    crit = [("miou", -1), ("f1_ice", -1), ("boundary_f1_scene_mean", -1), ("abs_area_bias_pct", 1)]
    tab = pd.DataFrame({m: {**x, "abs_area_bias_pct": abs(x["ice_area_bias_pct"])} for m, x in v.items()}).T
    ranks = sum((tab[c].astype(float) * s).rank() for c, s in crit)
    best = sorted(ranks.index, key=lambda m: (ranks[m], COMPLEXITY.get(m, 9)))[0]
    rec = {"selected_model": best, "criteria": "rank-sum on validation full scenes: mIoU, ice F1, boundary F1, |ice-area bias| (ties -> simpler)",
           "rank_sum": ranks.to_dict(), "validation_table": tab[[c for c, _ in crit] + ["iou_ice", "precision_ice", "recall_ice"]].astype(float).to_dict("index"),
           "beats_threshold_on_all": bool(all((tab.loc[best, c] - tab.loc["threshold", c]) * (-s) > 0 for c, s in crit)) if "threshold" in tab.index else None,
           "test_set_accessed_before_selection": False, "frozen_utc": pd.Timestamp.now(tz="UTC").isoformat()}
    _dump(rec, METRICS / "selection_record.json")
    return rec


def final_refit():
    rec = json.loads((METRICS / "selection_record.json").read_text())
    best = rec["selected_model"]
    meta = json.loads((CKPT / f"{best}.meta.json").read_text())
    cfg = load("training")
    version = f"aethentra-sar-seaice-{pd.Timestamp.now():%Y%m%d}-v1"
    if meta["kind"] == "unet":
        dw = 0.0 if meta["loss"] == "BCE" else cfg["unet"]["dice_weight"]
        m = train_unet("final_model", dw, splits=("train", "validation"), fixed_epochs=meta["best_epoch"], norm={k: tuple(v) for k, v in meta["norm"].items()})
    elif meta["kind"] == "threshold":
        s = _samples()
        m = ThresholdModel(name="final_model").fit(s[s.split.isin(["train", "validation"])].sample(400_000, random_state=cfg["seed"]))
    else:
        s = _samples()
        trva = s[s.split.isin(["train", "validation"])]
        m = TabularModel(meta["kind"], meta["params"], "final_model").fit(trva, None, n_estimators=int(round(1.1 * meta["best_iteration"])), seed=cfg["seed"])
    return save_model(m, FINAL, {"selected_from": best, "model_version": version, "train_splits": ["train", "validation"],
                                 "trained_utc": pd.Timestamp.now(tz="UTC").isoformat()})


def test_once():
    out = METRICS / "test_final" / "summary.json"
    if out.exists():
        raise RuntimeError("Test evaluation already exists; refusing to re-run.")
    sel = json.loads((METRICS / "selection_record.json").read_text())
    models = {"final_model": load_model(FINAL, "final_model")}
    models.update({n: load_model(CKPT, n) for n in COMPLEXITY if (CKPT / f"{n}.meta.json").exists()})
    res = evaluate(models, "test", "test_final", save_maps=["final_model"])
    res["selection_record_frozen_utc"] = sel["frozen_utc"]
    res["evaluated_utc"] = pd.Timestamp.now(tz="UTC").isoformat()
    _dump(res, out)
    return res
