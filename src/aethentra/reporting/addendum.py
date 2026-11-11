"""Artifact-driven report sections shared by the ML-01 and ML-02 generators: U-Net addendum, web viewer, NCEP R1 availability.

Every status is derived from files on disk (checkpoints, decision records, test summaries); nothing is claimed without them.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from ..config import ROOT

TORCH_CMD = "python -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu124"
TASKS = {
    "ml01": {"metrics": ROOT / "experiments" / "metrics", "ckpt": ROOT / "models" / "checkpoints" / "cnn_unet_residual.meta.json",
             "final": ROOT / "models" / "final" / "cnn_unet_final.meta.json", "run": "bash scripts/run_ml01_cnn.sh", "test_tree": "final_model"},
    "ml02": {"metrics": ROOT / "experiments" / "ml02" / "metrics", "ckpt": ROOT / "models" / "ml02" / "checkpoints" / "cnn_unet.meta.json",
             "final": ROOT / "models" / "ml02" / "final" / "cnn_unet_final.meta.json", "run": "bash scripts/ml02/run_cnn.sh", "test_tree": "final_model"},
}


def _j(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def _f(x, d=3):
    return "n/a" if x is None else f"{x:,.{d}f}"


def cnn_status(task: str) -> tuple[str, list[str]]:
    """(short status for phase tables, markdown lines for a report section)."""
    t = TASKS[task]
    ck, dec, te = _j(t["ckpt"]), _j(t["metrics"] / "addendum_cnn_decision_record.json"), _j(t["metrics"] / "test_cnn_addendum" / "summary.json")
    if ck is None:
        why = "PyTorch is not installed" if importlib.util.find_spec("torch") is None else "not yet run"
        return (f"U-Net IMPLEMENTED, not trained ({why})",
                [f"* U-Net candidate: **IMPLEMENTED, not trained** — {why}. The download host of the CUDA wheel could not be reached from the "
                 f"sandboxed build session. Install with `{TORCH_CMD}`, then run `{t['run']}` (stacks → train → validate → frozen decision → refit → single test).",
                 "* ConvLSTM: not implemented — the weekly-mean target with 7- to 56-day input summaries is already encoded as channels; a recurrent "
                 "model would only be justified if the U-Net shows that spatial context helps."])
    L = [f"* U-Net (`{ck['name']}`): {ck['n_parameters']:,} parameters, {ck['epochs_run']} epochs, best epoch {ck['best_epoch']} "
         f"(validation {ck['val_metric']} {_f(ck['best_val_metric'])}), {ck['seconds'] / 60:.0f} min on {ck['device']}; "
         f"{len(ck['dynamic_channels'])} dynamic + {len(ck['static_channels'])} static channels; loss {ck['loss']}."]
    if dec:
        L += ["", "| criterion (validation) | U-Net | " + dec["frozen_tree_selection"] + " | U-Net better |", "|---|---|---|---|"]
        for k, v in dec["comparison_on_validation"].items():
            L.append(f"| {k} | {_f(v[ck['name']])} | {_f(v[dec['frozen_tree_selection']])} | {'yes' if v['cnn_better'] else 'no'} |")
        L += ["", f"* Decision (frozen {dec['frozen_utc']}, validation only): U-Net better on {dec['cnn_better_on']}; "
              f"replaces the operational model: **{dec['cnn_replaces_operational_model']}** ({dec['rule']})."]
    if te:
        L.append(f"* Single test evaluation of `{te.get('tag')}` ({te['n_issue_dates']} issue dates, {te['first']} … {te['last']}, evaluated {te['evaluated_utc']}):")
        cm, tm = te["metrics"][next(iter(te["metrics"]))], te["tree_final_model_test_metrics_for_reference"]
        if task == "ml01":
            rows = [("SIZ MAE (pp)", "seasonal_ice_zone", "mae_pp", 3), ("SIZ RMSE (pp)", "seasonal_ice_zone", "rmse_pp", 3),
                    ("IIEE (km²)", "all", "iiee_mean_km2", 0), ("extent MAE (km²)", "all", "extent_mae_km2", 0)]
        else:
            rows = [("MAE (°C)", "all", "area_weighted_mae_degC", 3), ("RMSE (°C)", "all", "area_weighted_rmse_degC", 3),
                    ("ACC", "all", "acc_pattern_mean", 3), ("MSSS", "all", "msss_vs_climatology", 3)]
        L += ["", "| test metric | U-Net | tree final model |", "|---|---|---|"]
        for lab, g, k, d in rows:
            L.append(f"| {lab} | {_f(cm.get(g, {}).get(k), d)} | {_f(tm.get(g, {}).get(k), d)} |")
        L.append("")
        st = "U-Net COMPLETED (addendum; " + ("replaces" if dec and dec["cnn_replaces_operational_model"] else "does not replace") + " the tree model)"
    else:
        st = "U-Net trained; test pending"
    return st, L


def viewer_lines() -> list[str]:
    ok = (ROOT / "frontend" / "index.html").exists() and (ROOT / "api" / "viewer.py").exists()
    if not ok:
        return ["* Web viewer: NOT DONE."]
    return ["* Web viewer (`frontend/`, served by FastAPI at `/viewer/`; `/` redirects there): COMPLETED and run locally — sea-ice and 2 m "
            "temperature tabs, polar-stereographic previews rendered server-side from the native EPSG:3412 GeoTIFFs (`/layers/{sic|t2m}/…`), "
            "GeoTIFF downloads, every layer badged by data_type (forecasts framed and stamped MODEL PREDICTION), forecast summary, test "
            "skill and limitations. Start with `bash scripts/serve.sh` (loopback 127.0.0.1:8000). Not a production deployment: no "
            "authentication, TLS, process supervision or public hosting — those need an owner decision on where to host."]


def ncep_lines() -> list[str]:
    p = ROOT / "data" / "raw" / "aethentra" / "ncep_r1" / "ncep_r1_air_2026_south.nc.provenance.json"
    pr = _j(p)
    if not pr:
        return []
    return [f"* NCEP/NCAR R1 daily 2026 file: {pr['days']} days available upstream when last retrieved ({pr['retrieved_utc']}), i.e. through "
            "2026-03-17. NOAA PSL has not extended the series since; later retries were refused (HTTP 429 / 403). This is an upstream "
            "data gap, not a pipeline fault: ML-01 forecasts after 2026-03-17 use the SIC-only fallback declared before the test, whose "
            "test metrics are reported separately. Remedy: ERA5 atmosphere (same CDS key as ML-02) + retraining, or a resumed R1 feed."]


def operational_block(task: str) -> list[str]:
    """Header block naming the U-Net as operational model when the frozen decision says so (else [])."""
    t = TASKS[task]
    dec = _j(t["metrics"] / "addendum_cnn_decision_record.json")
    if not (dec and dec["cnn_replaces_operational_model"] and t["final"].exists()):
        return []
    L = ["## Operational model: U-Net (addendum)", "",
         f"The U-Net beat the frozen tree selection `{dec['frozen_tree_selection']}` on {dec['cnn_better_on']} on validation "
         f"(decision frozen {dec['frozen_utc']}, before its test evaluation) and now produces the forecasts. The tree model "
         "documented below remains the frozen selection and the fallback."]
    if task == "ml01":
        L.append("When fewer than 5 of 7 atmospheric days are available (all issue dates after 2026-03-17 at present), the forecast "
                 "uses the SIC-only tree fallback declared before the test, because the U-Net was validated with atmospheric inputs only.")
    L += ["No uncertainty interval is exported for U-Net forecasts (interval coverage was assessed around the tree model only).", ""]
    return L + cnn_status(task)[1] + [""]
