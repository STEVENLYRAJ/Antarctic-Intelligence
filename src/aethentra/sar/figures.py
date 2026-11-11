"""ML-03 figures from saved evaluation artifacts (no recomputation of metrics)."""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402

from .labels import ICE, UNCERTAIN, WATER, load_labels  # noqa: E402
from .paths import FIGURES, METRICS, OUTPUTS  # noqa: E402
from .preprocessing import load_scene  # noqa: E402

CLS = ListedColormap(["#1d4f91", "#f2f2f2", "#e8a33d"])           # water, ice, uncertain
ERR = ListedColormap(["#d7301f", "#2b8cbe"])                      # false ice, missed ice


def _save(fig, name):
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{name}.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return f"outputs/ml03/figures/{name}.png"


def scene_panels(n: int = 3) -> list[str]:
    df = pd.read_csv(METRICS / "test_final" / "per_scene.csv").query("model == 'final_model'")
    df = df[(df.tp + df.fn > 5000) & (df.tn + df.fp > 5000)]               # scenes with both classes
    if df.empty:
        return []
    df = df.assign(iou=df.tp / (df.tp + df.fp + df.fn))
    pick = df.sort_values("iou").iloc[np.linspace(0, len(df) - 1, min(n, len(df))).astype(int)]
    out = []
    for r in pick.itertuples():
        scene, meta = load_scene(r.scene_id)
        lab = load_labels(r.scene_id)
        prob = np.load(METRICS / "test_final" / "maps" / f"{r.scene_id}__final_model.npz")["prob"].astype(np.float32)
        pred = np.where(np.isfinite(prob), (prob >= 0.5).astype(float), np.nan)
        fig, ax = plt.subplots(1, 5, figsize=(22, 4.6))
        ax[0].imshow(scene["s0_db"], cmap="gray", vmin=-28, vmax=-3); ax[0].set_title("Sentinel-1 EW HH σ⁰ (dB) — observation")
        ax[1].imshow(np.where(lab == 255, np.nan, lab.astype(float)), cmap=CLS, vmin=0, vmax=2); ax[1].set_title("USNIC chart label (reference)")
        ax[2].imshow(prob, cmap="Blues_r", vmin=0, vmax=1); ax[2].set_title("Model ice probability (prediction)")
        ax[3].imshow(scene["s0_db"], cmap="gray", vmin=-28, vmax=-3); ax[3].imshow(np.where(pred == 1, 1.0, np.nan), cmap=ListedColormap(["#4fc3f7"]), alpha=0.45)
        ax[3].set_title("Overlay: predicted ice")
        m = np.isin(lab, (WATER, ICE)) & np.isfinite(prob)
        e = np.full(lab.shape, np.nan)
        e[m & (pred == 1) & (lab == WATER)] = 0
        e[m & (pred == 0) & (lab == ICE)] = 1
        ax[4].imshow(scene["s0_db"], cmap="gray", vmin=-28, vmax=-3, alpha=0.5); ax[4].imshow(e, cmap=ERR, vmin=0, vmax=1)
        ax[4].set_title("Errors: red false ice, blue missed ice")
        for a in ax:
            a.set_xticks([]); a.set_yticks([])
        fig.suptitle(f"{r.scene_id[:33]}…  chart {r.chart_date}  sector {r.sector}  scene IoU(ice) {r.iou:.2f}", fontsize=10)
        out.append(_save(fig, f"scene_{r.scene_id[17:32]}"))
    return out


def summary_plots() -> list[str]:
    t = json.loads((METRICS / "test_final" / "summary.json").read_text())
    out = []
    c = t["metrics"]["final_model"]["confusion"]
    cm = np.array([[c["tn"], c["fp"]], [c["fn"], c["tp"]]], float)
    fig, ax = plt.subplots(figsize=(4.2, 3.8))
    ax.imshow(cm / cm.sum(1, keepdims=True), cmap="Blues", vmin=0, vmax=1)
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{cm[i, j] / cm[i].sum():.3f}\n({int(cm[i, j]):,})", ha="center", va="center", fontsize=9)
    ax.set_xticks([0, 1], ["pred water", "pred ice"]); ax.set_yticks([0, 1], ["chart water", "chart ice"])
    ax.set_title("Final model, test scenes (row-normalised)")
    out.append(_save(fig, "confusion_matrix_test"))
    models = [m for m in ("threshold", "rf", "xgb", "unet_bce", "unet_bce_dice", "final_model") if m in t["metrics"]]
    for key, title in (("by_sector", "regional"), ("by_season", "seasonal")):
        groups = sorted(t[key]["final_model"])
        fig, ax = plt.subplots(figsize=(9, 3.8))
        w = 0.8 / len(models)
        for k, m in enumerate(models):
            ax.bar(np.arange(len(groups)) + k * w, [t[key][m].get(g, {}).get("miou", np.nan) for g in groups], w, label=m)
        ax.set_xticks(np.arange(len(groups)) + 0.4 - w / 2, groups, rotation=15); ax.set_ylabel("mIoU vs chart"); ax.set_ylim(0, 1)
        ax.legend(fontsize=7, ncol=3); ax.set_title(f"Test {title} performance (agreement with USNIC charts)")
        out.append(_save(fig, f"{title}_miou_test"))
    rel = t.get("reliability", {}).get("final_model")
    if rel:
        w_, i_ = np.array(rel["water_counts"]), np.array(rel["ice_counts"])
        frac = i_ / np.maximum(w_ + i_, 1)
        ctr = (np.array(rel["bins"][:-1]) + np.array(rel["bins"][1:])) / 2
        fig, ax = plt.subplots(figsize=(4.2, 4))
        ax.plot([0, 1], [0, 1], "k:", lw=1); ax.plot(ctr, frac, "o-")
        ax.set_xlabel("predicted ice probability"); ax.set_ylabel("observed chart-ice fraction"); ax.set_title("Reliability (test)")
        out.append(_save(fig, "reliability_test"))
    ea = METRICS / "error_analysis_test.json"
    if ea.exists():
        e = json.loads(ea.read_text())
        fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
        b = e["by_incidence_deg"]; ax[0].plot([np.mean(x["bin"]) for x in b], [x["error_rate"] for x in b], "o-"); ax[0].set_xlabel("incidence angle (°)")
        b = e["water_false_ice_rate_by_sigma0_db"]; ax[1].plot([np.mean(x["bin"]) for x in b], [x["error_rate"] for x in b], "o-", color="#d7301f")
        ax[1].set_xlabel("HH σ⁰ of chart-water pixels (dB)"); ax[0].set_ylabel("error rate"); ax[1].set_ylabel("false-ice rate")
        ax[0].set_title("Incidence-angle sensitivity"); ax[1].set_title("Bright (wind-roughened) water")
        out.append(_save(fig, "error_analysis_test"))
    return out


def weekly_figure() -> list[str]:
    import rasterio
    weeks = sorted((OUTPUTS / "weekly_maps").glob("week_*/metadata.json"))
    if not weeks:
        return []
    d = weeks[-1].parent
    md = json.loads(weeks[-1].read_text())
    with rasterio.open(d / "layers" / "detection_frequency.tif") as r:
        f = r.read(1)
    with rasterio.open(d / "layers" / "valid_acquisitions.tif") as r:
        n = r.read(1)
    sl = slice(500, 3500)
    fig, ax = plt.subplots(1, 2, figsize=(12, 5.6))
    im = ax[0].imshow(np.where(f < 0, np.nan, f)[sl, sl], cmap="Blues_r", vmin=0, vmax=1); fig.colorbar(im, ax=ax[0], shrink=0.7)
    ax[0].set_title(f"Weekly ice detection frequency, week of {md['week_start']}")
    im = ax[1].imshow(np.where(n == 0, np.nan, n)[sl, sl], cmap="viridis"); fig.colorbar(im, ax=ax[1], shrink=0.7)
    ax[1].set_title(f"Valid acquisitions per 2 km cell ({md['n_acquisitions']} scenes)")
    for a in ax:
        a.set_xticks([]); a.set_yticks([]); a.set_facecolor("#cccccc")
    return [_save(fig, f"weekly_{md['week_start']}")]


def make_all() -> list[str]:
    return scene_panels() + summary_plots() + weekly_figure()
