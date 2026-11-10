"""ML-02 evaluation figures (outputs/ml02/figures/evaluation/). Every number plotted comes from saved evaluation artefacts."""
from __future__ import annotations

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ...visualization.style import DIVERGING, INK2, OTHER, SERIES, apply_style  # noqa: E402
from ..evaluation.metrics import CAT_NAMES  # noqa: E402
from ..paths import FIGURES, METRICS, MODELS  # noqa: E402
from ..preprocessing.cube import Cube  # noqa: E402

TEMP_DIV = DIVERGING.reversed()
OUT = FIGURES / "evaluation"
ORDER = ["final_model", "lgbm_tuned", "lgbm", "xgb", "rf", "lgbm_temperature_only", "damped_persistence", "persistence_week",
         "persistence", "recent_trend", "climatology"]
REGIONS = ["all", "antarctica_land", "southern_ocean", "antarctic_peninsula", "west_antarctica", "east_antarctica", "coastal_land", "inland"]


def _j(p):
    return json.loads(p.read_text()) if p.exists() else None


COLORS = {"final_model": SERIES[0], "lgbm_tuned": SERIES[6], "lgbm": SERIES[2], "xgb": SERIES[3], "rf": SERIES[4],
          "lgbm_temperature_only": SERIES[5], "damped_persistence": INK2, "persistence": SERIES[1], "persistence_week": SERIES[7],
          "recent_trend": "#b0aea8", "climatology": OTHER}


def _color(m):
    return COLORS.get(m, OTHER)


def _map(ax, cube, v, cmap, vmin, vmax, title):
    g = cube.to_grid(v)
    r0, r1 = cube.grid["rows"].min(), cube.grid["rows"].max() + 1
    c0, c1 = cube.grid["cols"].min(), cube.grid["cols"].max() + 1
    im = ax.imshow(g[r0:r1, c0:c1], cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
    ax.contour(np.nan_to_num(cube.to_grid(cube.grid["land"].astype(float))[r0:r1, c0:c1]), levels=[0.5], colors="#0b0b0b", linewidths=0.5)
    ax.set_title(title, fontsize=10); ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    return im


def make_all() -> list[str]:
    apply_style()
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    cube = Cube()
    val = _j(METRICS / "validation_candidates" / "summary.json")
    te = _j(METRICS / "test_final" / "summary.json")

    def save(fig, name):
        fig.savefig(OUT / name, dpi=140, bbox_inches="tight"); plt.close(fig); made.append(name)

    # 1-2 regional RMSE comparison (validation candidates; test final vs baselines)
    for tag, res in (("validation", val), ("test", te)):
        if not res:
            continue
        mets = [m for m in ORDER if m in res["metrics"]]
        fig, ax = plt.subplots(figsize=(12, 4))
        w = 0.8 / len(mets)
        for i, m in enumerate(mets):
            vals = [res["metrics"][m][r]["area_weighted_rmse_degC"] for r in REGIONS]
            ax.bar(np.arange(len(REGIONS)) + i * w, vals, w, color=_color(m), label=m)
        ax.set_xticks(np.arange(len(REGIONS)) + 0.4 - w / 2, [r.replace("_", "\n") for r in REGIONS])
        ax.set_ylabel("area-weighted RMSE (°C)"); ax.legend(ncol=4, fontsize=8)
        ax.set_title(f"Weekly-mean T2m anomaly RMSE by region — {tag} ({res['first']}..{res['last']}, {res['n_issue_dates']} issue dates)")
        save(fig, f"01_regional_rmse_{tag}.png")
    if not te:
        return made
    # 3 seasonal performance (test)
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.8))
    for ax, met, lab in zip(axs, ("area_weighted_rmse_degC", "acc_pattern_mean"), ("RMSE (°C)", "anomaly pattern correlation")):
        for m in ("final_model", "damped_persistence", "persistence", "climatology"):
            if m in te["metrics"]:
                bs = te["metrics"][m]["all"]["by_season"]
                ax.plot(["DJF", "MAM", "JJA", "SON"], [bs[s][met] if bs[s].get(met) is not None else np.nan for s in ["DJF", "MAM", "JJA", "SON"]],
                        marker="o", color=_color(m), label=m)
        ax.set_ylabel(lab); ax.set_title(f"Test {lab} by target season")
    axs[0].legend()
    save(fig, "02_seasonal_performance_test.png")
    # 4 observed vs predicted (hexbin) + residual distribution (test fields)
    fz = np.load(METRICS / "test_final" / "fields.npz")
    o, p, pe = fz["obs_anom"].ravel(), fz["final_model"].ravel(), fz["persistence"].ravel()
    ok = np.isfinite(o) & np.isfinite(p)
    sub = np.random.default_rng(0).choice(np.flatnonzero(ok), min(2_000_000, ok.sum()), replace=False)
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.4))
    hb = axs[0].hexbin(o[sub], p[sub], gridsize=80, bins="log", cmap="Blues", extent=(-25, 25, -25, 25))
    axs[0].plot([-25, 25], [-25, 25], color=INK2, lw=0.8); axs[0].set_xlabel("reanalysis weekly anomaly (°C)"); axs[0].set_ylabel("forecast anomaly (°C)")
    axs[0].set_title("Test: forecast vs reanalysis weekly anomaly"); fig.colorbar(hb, ax=axs[0], label="log10 count")
    bins = np.linspace(-15, 15, 121)
    axs[1].hist((p - o)[sub], bins=bins, density=True, color=SERIES[0], alpha=0.7, label="final model")
    axs[1].hist((pe - o)[sub], bins=bins, density=True, color=SERIES[1], alpha=0.45, label="persistence")
    axs[1].hist((0 - o)[sub], bins=bins, density=True, histtype="step", color=OTHER, label="climatology (A=0)")
    axs[1].set_xlabel("error (°C)"); axs[1].set_title("Test residual distribution"); axs[1].legend()
    save(fig, "03_obs_vs_pred_and_residuals_test.png")
    # 5 spatial error maps and skill map (test)
    em = np.load(METRICS / "test_final" / "error_maps.npz")
    fig, axs = plt.subplots(1, 4, figsize=(17, 4.4))
    for ax, k, ttl in zip(axs[:2], ("final_model", "persistence"), ("Final model", "Persistence")):
        im = _map(ax, cube, em[f"{k}__rmse"], "magma_r", 0, 8, f"{ttl}: RMSE (°C)")
    fig.colorbar(im, ax=axs[:2], fraction=0.02)
    im = _map(axs[2], cube, em["final_model__bias"], TEMP_DIV, -2, 2, "Final model: mean bias (°C)")
    fig.colorbar(im, ax=axs[2], fraction=0.04)
    skill = 1 - em["final_model__rmse"] ** 2 / em["climatology__rmse"] ** 2
    im = _map(axs[3], cube, skill, TEMP_DIV, -0.6, 0.6, "MSE skill vs climatology")
    fig.colorbar(im, ax=axs[3], fraction=0.04)
    save(fig, "04_spatial_error_maps_test.png")
    # 6 example anomaly maps: largest observed domain anomaly week in test
    dom = np.nanmean(np.abs(fz["obs_anom"]), axis=1)
    i = int(np.nanargmax(dom))
    d = pd.Timestamp(str(fz["dates"][i]))
    fig, axs = plt.subplots(1, 3, figsize=(14, 4.6))
    for ax, k, ttl in zip(axs, ("obs_anom", "final_model", "persistence"), ("Reanalysis (verifying)", "Final model forecast", "Persistence")):
        im = _map(ax, cube, fz[k][i], TEMP_DIV, -15, 15, f"{ttl}")
    fig.colorbar(im, ax=axs, fraction=0.015, label="weekly anomaly (°C)")
    fig.suptitle(f"Weekly T2m anomaly, target week {(d + pd.Timedelta(days=1)).date()}..{(d + pd.Timedelta(days=7)).date()} (largest |anomaly| test week)")
    save(fig, "05_example_anomaly_maps_test.png")
    # 7 confusion matrix
    cm = np.array(te["metrics"]["final_model"]["all"]["categories"]["confusion_matrix_obs_rows_pred_cols"], float)
    fig, ax = plt.subplots(figsize=(5.6, 4.6))
    rn = cm / cm.sum(1, keepdims=True)
    im = ax.imshow(rn, cmap="Blues", vmin=0, vmax=1); ax.grid(False)
    ax.set_xticks(range(5), CAT_NAMES, rotation=35); ax.set_yticks(range(5), CAT_NAMES)
    for a in range(5):
        for b in range(5):
            ax.text(b, a, f"{rn[a, b]:.2f}", ha="center", va="center", fontsize=8, color="white" if rn[a, b] > 0.5 else INK2)
    ax.set_xlabel("forecast category"); ax.set_ylabel("observed (reanalysis) category"); ax.set_title("Test anomaly categories (row-normalised)")
    fig.colorbar(im, ax=ax, fraction=0.04)
    save(fig, "06_category_confusion_test.png")
    # 8 time series of domain/land area-mean anomaly: obs vs forecast
    area = cube.grid["area_km2"]; land = cube.grid["land"]
    am = lambda F: (np.nan_to_num(F[:, land]) * area[land]).sum(1) / area[land].sum()  # noqa: E731
    dts = pd.to_datetime(fz["dates"]) + pd.Timedelta(days=4)
    fig, ax = plt.subplots(figsize=(12, 3.6))
    ax.plot(dts, am(fz["obs_anom"]), color=INK2, lw=1.2, label="reanalysis (verifying)")
    ax.plot(dts, am(fz["final_model"]), color=SERIES[0], lw=1.2, label="final model")
    ax.plot(dts, am(fz["persistence"]), color=SERIES[1], lw=0.8, alpha=0.7, label="persistence")
    ax.axhline(0, color=OTHER, lw=0.6); ax.set_ylabel("°C"); ax.legend(ncol=3)
    ax.set_title("Antarctic land area-mean weekly T2m anomaly — test period")
    save(fig, "07_land_mean_anomaly_timeseries_test.png")
    # 9 learning curves of candidates
    hs = {}
    for m in ("lgbm", "xgb", "lgbm_temperature_only"):
        p_ = MODELS / "checkpoints" / f"{m}.history.json"
        if p_.exists():
            hs[m] = json.loads(p_.read_text())
    if hs:
        fig, ax = plt.subplots(figsize=(8, 3.6))
        for i, (m, h) in enumerate(hs.items()):
            for split, ls in (("train", "--"), ("valid", "-")):
                if split in h:
                    k = list(h[split])[0]
                    ax.plot(h[split][k], ls, color=SERIES[i], lw=1, label=f"{m} {split} ({k})")
        ax.set_xlabel("boosting iteration"); ax.set_ylabel("loss"); ax.set_title("Training / validation curves"); ax.legend(fontsize=7)
        save(fig, "08_learning_curves.png")
    # 10 station comparison
    st = _j(METRICS / "station_evaluation_test.json")
    if st:
        df = pd.DataFrame(st["stations"]).sort_values("final_model_anom_rmse")
        fig, ax = plt.subplots(figsize=(12, 4))
        x = np.arange(len(df))
        for j, (k, c) in enumerate((("reanalysis", INK2), ("final_model", SERIES[0]), ("persistence", SERIES[1]), ("climatology", OTHER))):
            ax.bar(x + j * 0.2, df[f"{k}_anom_rmse"], 0.2, color=c, label=k)
        ax.set_xticks(x + 0.3, [s.split(":")[1][:14] for s in df["station"]] if df["name"].isna().all() else [str(n)[:14] for n in df["name"]], rotation=70, fontsize=7)
        ax.set_ylabel("weekly anomaly RMSE vs station (°C)"); ax.legend(ncol=4)
        ax.set_title(f"Independent station check (test period, {st['n_stations']} stations, {st['n_station_weeks']} station-weeks)")
        save(fig, "09_station_comparison_test.png")
    (OUT / "figures_manifest.json").write_text(json.dumps({"figures": made}, indent=1))
    return made
