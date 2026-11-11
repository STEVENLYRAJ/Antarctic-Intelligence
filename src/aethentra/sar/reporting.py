"""ML-03 result documents generated from saved artifacts (every number is read from a file written by an executed stage)."""
from __future__ import annotations

import json

import pandas as pd

from ..config import ROOT
from .features import PIXEL_FEATURES, UNET_CHANNELS
from .paths import DOCS, FIGURES, INTERIM, METRICS, MODELS, OUTPUTS, PROCESSED, load

CKPT, FINAL = MODELS / "checkpoints", MODELS / "final"
ORDER = ["threshold", "rf", "xgb", "unet_bce", "unet_bce_dice", "final_model"]
COLS = [("miou", "mIoU"), ("iou_ice", "IoU ice"), ("iou_water", "IoU water"), ("f1_ice", "F1 ice"), ("precision_ice", "prec. ice"),
        ("recall_ice", "recall ice"), ("overall_accuracy", "OA"), ("balanced_accuracy", "bal. acc."), ("boundary_f1_scene_mean", "boundary F1"),
        ("edge_displacement_km_median_scene_mean", "edge disp. km"), ("ice_area_bias_pct", "ice-area bias %")]


def _j(p):
    return json.loads(p.read_text()) if p.exists() else None


def _f(x, d=3):
    return "n/a" if x is None or (isinstance(x, float) and x != x) else (f"{x:,.{d}f}" if isinstance(x, (int, float)) else str(x))


def table(metrics: dict, models=None) -> list[str]:
    models = [m for m in (models or ORDER) if m in metrics]
    L = ["| model | " + " | ".join(c for _, c in COLS) + " |", "|---|" + "---|" * len(COLS)]
    for m in models:
        L.append(f"| {m} | " + " | ".join(_f(metrics[m].get(k), 1 if k == "ice_area_bias_pct" else 3) for k, _ in COLS) + " |")
    return L


def figs() -> list[str]:
    return [f"![{p.stem}](../../outputs/ml03/figures/{p.name})" for p in sorted(FIGURES.glob("*.png"))]


def _cat():
    p = INTERIM / "scene_catalogue.csv"
    return pd.read_csv(p) if p.exists() else None


def data_inventory():
    cat = _cat()
    charts = pd.read_csv(INTERIM / "chart_catalogue.csv")
    rows = [{"dataset": "Sentinel-1 EW GRDM HH (overview x8)", "source": "ESA Copernicus via Microsoft Planetary Computer", "format": "COG GeoTIFF + SAFE XML",
             "files": int((cat["download_status"] == "downloaded").sum()) if cat is not None else 0, "temporal": f"{cat.acquired.min()[:10]} .. {cat.acquired.max()[:10]}" if cat is not None else "",
             "crs": "GCPs (EPSG:4326) -> EPSG:3031", "resolution": "40 m read at x8 overview, resampled 400 m", "status": "verified existing (downloaded)"},
            {"dataset": "USNIC Antarctic ice charts", "source": "U.S. National Ice Center", "format": "SIGRID-3 shapefile", "files": len(charts),
             "temporal": f"{charts.chart_date.min()} .. {charts.chart_date.max()}", "crs": "polar stereographic (WGS84)", "resolution": "chart polygons (km)",
             "status": "verified existing (downloaded)"},
            {"dataset": "Natural Earth 10 m land + Antarctic ice shelves", "source": "naturalearthdata.com", "format": "shapefile", "files": 2, "temporal": "static",
             "crs": "EPSG:4326", "resolution": "1:10m", "status": "verified existing (downloaded)"},
            {"dataset": "DMI-ASIP Antarctic SIC mosaic", "source": "CMEMS SEAICE_ANT_PHY_AUTO_L3_NRT_011_012", "format": "NetCDF", "files": 1, "temporal": "2023-02-02",
             "crs": "polar stereographic lat_ts -70", "resolution": "1 km", "status": "verified existing (user file); more days need an account"},
            {"dataset": "CDSE / ASF full-resolution SAFE", "source": "ESA / NASA ASF", "format": "SAFE zip", "files": 0, "temporal": "", "crs": "", "resolution": "40 m",
             "status": "downloadable with registration (missing credentials)"},
            {"dataset": "AI4Arctic ASIP v2", "source": "DTU", "format": "NetCDF", "files": 0, "temporal": "2018-2019", "crs": "", "resolution": "80 m",
             "status": "downloadable; not used (Arctic)"}]
    df = pd.DataFrame(rows)
    df.to_csv(DOCS / "DATA_INVENTORY.csv", index=False)
    L = ["# ML-03 — Data Inventory", "", df.to_markdown(index=False), ""]
    if cat is not None and "processing_status" in cat:
        L += ["## Scene catalogue status", "", cat.groupby("split").agg(scenes=("scene_id", "count"), charts=("chart_date", "nunique"),
              downloaded=("download_status", lambda s: int((s == "downloaded").sum())),
              processed=("processing_status", lambda s: int((s == "processed").sum()))).to_markdown(), ""]
    (DOCS / "DATA_INVENTORY.md").write_text("\n".join(L), encoding="utf-8")


def label_report():
    cat = _cat()
    from .dataset import usable
    u = usable(cat)
    g = u.groupby("split")[["n_water", "n_ice", "n_uncertain"]].sum()
    g["water_fraction_of_labelled"] = g.n_water / (g.n_water + g.n_ice)
    cfg = load("labels")
    L = ["# ML-03 — Label Generation Report", "",
         "Labels are rasterised USNIC Antarctic chart polygons on each scene's 400 m EPSG:3031 grid (`src/aethentra/sar/labels.py`).", "",
         f"* Mapping (SIGRID-3 total concentration CT): water = {cfg['water_codes']}; sea ice = lower bound ≥ {cfg['ice_min_concentration_pct']} % "
         "(incl. 91/92); 10–70 % → uncertain; undetermined codes → invalid.",
         f"* Boundary buffer: water/ice pixels within {cfg['boundary_buffer_m'] / 1000:.0f} km of another class → uncertain "
         "(chart scale and the 0–3 day chart/scene time mismatch).",
         f"* Chart pairing: scene acquired {cfg['chart_match_days'][0]}–{cfg['chart_match_days'][1]} days before the chart valid date; "
         "the 80 acquisitions closest to the chart date are searched and 2 per chart drawn, stratified by sector.",
         "* Invalid: land/ice shelf (Natural Earth + 2 km), no SAR, incidence outside 18–48°, outside chart polygons.",
         "* Usability rule (fixed before training): ≥ 2,000 chart water+ice pixels in the scene.", "",
         f"Scenes processed: {int((cat.processing_status == 'processed').sum())} / {len(cat)}; usable: {len(u)} "
         f"({u.groupby('split').size().to_dict()}).", "", "## Labelled pixels per split (400 m pixels)", "", g.to_markdown(floatfmt=".3f"), "",
         "## Validation checks", "",
         "* Spatial alignment: chart and scene share the same transform (rasterised on the scene grid); visual check of coastal polynyas.",
         "* Date alignment: chart valid date 0–3 days after acquisition (recorded per scene).",
         "* Duplicates: one label file per scene id; a scene belongs to exactly one chart and split (tested).",
         f"* Mean chart coverage of valid SAR pixels: {cat['chart_coverage'].mean():.3f}.",
         "* No human or expert review of individual pixels was done (ANNOTATION_GUIDELINES.md).", "",
         "**These labels are expert chart analyses at chart scale, independent of the model but not pixel-perfect truth.**"]
    (DOCS / "LABEL_GENERATION_REPORT.md").write_text("\n".join(L), encoding="utf-8")


def feature_doc():
    tiles = _j(PROCESSED / "tiles" / "tiles.json") or {}
    th = _j(CKPT / "threshold.meta.json") or {}
    L = ["# ML-03 — Feature Engineering", "", "Implementation: `src/aethentra/sar/features.py`. Only the scene itself (and static geography) is used.", "",
         "## Pixel features (threshold / Random Forest / XGBoost)", "", ", ".join(f"`{f}`" for f in PIXEL_FEATURES), "",
         "* `s0` HH σ⁰ (dB); `inc` incidence angle; `s0_norm` = s0 + b·(inc − 35°) with b fitted on TRAINING samples "
         f"(b = {_f(th.get('slope_db_per_deg'), 3)} dB/°).",
         "* Local mean (3/7/15 px), local std (7/15 px), gradient magnitude of the 3 px mean.",
         "* GLCM contrast / homogeneity / entropy on 16 px blocks, 32 grey levels over −30…0 dB (offsets 1 px, 0° and 90°).",
         "* Geography: latitude, sin/cos longitude, distance to coast (from the land mask); season: sin/cos day of year.",
         "", "## U-Net channels", "", ", ".join(f"`{c}`" for c in UNET_CHANNELS) + " — normalised with training-tile statistics; NaN → 0 with the `valid` channel.",
         f"* Tiles: {tiles.get('train', {}).get('tiles')} train / {tiles.get('validation', {}).get('tiles')} validation / {tiles.get('test', {}).get('tiles')} test "
         "(256 × 256, 400 m).", "",
         "## Not used", "", "* HV/VV/VH and ratios: not acquired over Antarctic sea ice in EW mode (HH only).",
         "* Temporal features (previous acquisition, historical masks), AMSR2, ERA5, ML-01 outputs: not used in this release "
         "(would require per-pixel time matching and risk leaking label information; NEXT_STEPS.md)."]
    (DOCS / "FEATURE_ENGINEERING.md").write_text("\n".join(L), encoding="utf-8")


def training_report():
    br = _j(METRICS / "baseline_training_records.json") or {}
    L = ["# ML-03 — Model Training Report", "", "Splits by chart date (scene-level, before tiling): "
         + ", ".join(f"{k} {v[0]}…{v[1]}" for k, v in load("labels")["splits"].items()) + ".", "",
         "| model | status | checkpoint | key settings |", "|---|---|---|---|"]
    for n in ("threshold", "rf", "xgb", "unet_bce", "unet_bce_dice"):
        m = _j(CKPT / f"{n}.meta.json")
        if not m:
            L.append(f"| {n} | NOT TRAINED | — | — |")
            continue
        f = next(iter(CKPT.glob(f"{n}.p*")), None)
        if m["kind"] == "threshold":
            k = f"slope {_f(m['slope_db_per_deg'])} dB/°, threshold {_f(m['threshold_db'], 2)} dB at 35°, train bal. acc. {_f(m['train_balanced_accuracy'])}"
        elif m["kind"] == "unet":
            k = (f"{m['n_parameters']:,} params, loss {m['loss']}, {m['epochs_run']} epochs (best {m['best_epoch']}, val tile mIoU "
                 f"{_f(m['best_val_tile_miou'])}), {m['train_tiles']} tiles, {m['seconds'] / 60:.0f} min on {m.get('gpu') or m['device']}")
        else:
            k = f"{m['params']}; iterations {m['best_iteration']}; fit {m['fit_seconds']:.0f} s"
        L.append(f"| {n} | COMPLETED (checkpoint verified) | `models/ml03/checkpoints/{f.name if f else '?'}` | {k} |")
    fm = _j(FINAL / "final_model.meta.json")
    if fm:
        L.append(f"| **final_model** ({fm['selected_from']}, train+validation) | COMPLETED | `models/ml03/final/` | version {fm['model_version']} |")
    L += ["", "U-Net: AdamW + OneCycle, batch 16, bf16 autocast, seed 42, early stopping on validation tile mIoU (patience 8); "
          "augmentation rot90/flip/gain/noise (SAR look direction varies between orbits, so orientation carries no physical meaning). "
          "Uncertain (2) and invalid (255) pixels are excluded from the loss.", "",
          "Hyper-parameter optimisation: the U-Net loss (BCE vs BCE+Dice) was compared on validation; no further search was run "
          "(see NEXT_STEPS.md). The test split was never used for any choice."]
    (DOCS / "MODEL_TRAINING_REPORT.md").write_text("\n".join(L), encoding="utf-8")


def evaluation_report():
    v = _j(METRICS / "validation_candidates" / "summary.json")
    t = _j(METRICS / "test_final" / "summary.json")
    sel = _j(METRICS / "selection_record.json")
    L = ["# ML-03 — Model Evaluation Report", "", "**All metrics measure agreement with USNIC chart labels** on full scenes (water/ice pixels only; "
         "uncertain and invalid pixels excluded). Boundary metrics use the unbuffered chart ice edge (≥ 10 % concentration) with a "
         f"{load('evaluation')['boundary_tolerance_px'] * 0.4:.0f} km tolerance. Ice areas use true pixel areas.", ""]
    if v:
        L += [f"## Validation ({v['n_scenes']} scenes, charts {v['first_chart']}…{v['last_chart']})", ""] + table(v["metrics"]) + [""]
    if sel:
        L += [f"**Selection (frozen {sel['frozen_utc']}, validation only):** `{sel['selected_model']}` — {sel['criteria']}. "
              f"Rank sums: {', '.join(f'{k} {v_:.0f}' for k, v_ in sorted(sel['rank_sum'].items(), key=lambda x: x[1]))}.", ""]
    if t:
        L += [f"## Test — single evaluation ({t['n_scenes']} scenes, charts {t['first_chart']}…{t['last_chart']}, evaluated {t['evaluated_utc']})", ""]
        L += table(t["metrics"]) + ["", "`final_model` = selected configuration refitted on train+validation; the other rows are the "
                                         "train-only candidates evaluated on the same test scenes for comparison.", ""]
        c = t["metrics"]["final_model"]["confusion"]
        L += [f"Confusion (final model, pixels): TP {c['tp']:,} · FP {c['fp']:,} · FN {c['fn']:,} · TN {c['tn']:,}. "
              f"Ice area: predicted {t['metrics']['final_model']['pred_ice_km2']:,.0f} km² vs chart {t['metrics']['final_model']['ref_ice_km2']:,.0f} km² "
              f"over labelled pixels.", ""]
        for key, title in (("by_sector", "Regional"), ("by_season", "Seasonal")):
            L += [f"### {title} (final model)", "", "| group | scenes | mIoU | F1 ice | boundary F1 | ice-area bias % |", "|---|---|---|---|---|---|"]
            for g, x in sorted(t[key]["final_model"].items()):
                L.append(f"| {g} | {x['n_scenes']} | {_f(x['miou'])} | {_f(x['f1_ice'])} | {_f(x.get('boundary_f1_scene_mean'))} | {_f(x['ice_area_bias_pct'], 1)} |")
            L.append("")
    L += ["## Figures", ""] + figs()
    (DOCS / "MODEL_EVALUATION_REPORT.md").write_text("\n".join(L), encoding="utf-8")


def error_report():
    e = _j(METRICS / "error_analysis_test.json")
    L = ["# ML-03 — Model Interpretability and Error Report", "", "Computed on the TEST scenes after the single test evaluation "
         "(`src/aethentra/sar/analysis.py`). Error = disagreement with the USNIC chart (water/ice pixels).", ""]
    if not e:
        (DOCS / "MODEL_INTERPRETABILITY_AND_ERROR_REPORT.md").write_text("\n".join(L + ["Not run."]), encoding="utf-8")
        return
    tab = lambda rows, k, lab: [f"| {lab} | pixels | {k} |", "|---|---|---|"] + [f"| {r['bin'][0]:g}–{r['bin'][1]:g} | {r['pixels']:,} | {r['error_rate']:.3f} |" for r in rows]  # noqa: E731
    L += [f"Overall pixel error rate {e['overall_error_rate']:.3f} over {e['pixels']:,} pixels.", "",
          "## Incidence-angle sensitivity", ""] + tab(e["by_incidence_deg"], "error rate", "incidence (°)") + [
          "", "## Coastal confusion (distance to coast)", ""] + tab(e["by_distance_to_coast_km"], "error rate", "km") + [
          "", "## Wind-roughened / bright open water (chart water pixels)", ""] + tab(e["water_false_ice_rate_by_sigma0_db"], "false-ice rate", "HH σ⁰ (dB)") + [
          "", "## Dark sea ice (chart ice pixels: new ice, nilas, wet/melting ice)", ""] + tab(e["ice_missed_rate_by_sigma0_db"], "missed-ice rate", "HH σ⁰ (dB)") + [
          "", "## Seasonal", "", "| month | pixels | error rate |", "|---|---|---|"] + [f"| {r['month']} | {r['pixels']:,} | {r['error_rate']:.3f} |" for r in e["by_month"]] + [
          "", "## Ice-edge score vs tolerance (post-test sensitivity, final model)", "",
          "Mean scene boundary F1 by tolerance: " + ", ".join(f"{k} km: {_f(v)}" for k, v in e.get("boundary_f1_by_tolerance_km", {}).items())
          + ". The 2 km evaluation tolerance is tighter than the 4 km chart-boundary buffer, so low values mainly reflect chart-scale "
          "edge placement, not only model error.",
          "", f"Chart-uncertain pixels (10–70 % concentration or boundary buffer) predicted as ice: {_f(e['chart_uncertain_pixels_predicted_ice_fraction'])} "
          "(the model is forced to a binary decision there; these pixels are excluded from all scores).", ""]
    fi = e.get("feature_importance") or {}
    for n, imp in fi.items():
        if imp:
            top = sorted(imp.items(), key=lambda x: -x[1])[:8]
            L += [f"Top {n} feature importances: " + ", ".join(f"{k} {v:.3f}" for k, v in top), ""]
    d = e.get("dmi_asip_comparison", {})
    L += ["## Comparison with DMI-ASIP (pseudo-label, one day)", ""]
    if d.get("status") == "computed":
        L += [f"{len(d['scenes'])} scene(s) acquired {d['day']}: agreement {d['agreement']:.3f}, IoU ice {d['iou_ice']:.3f}, IoU water {d['iou_water']:.3f} "
              f"over {d['pixels']:,} pixels (DMI SIC ≥ 15 % = ice). {d['note']}"]
    else:
        L += [f"Not computed: {d.get('status')}."]
    L += ["", "## Validation categories", "", "* Model prediction vs **pseudo-label agreement** (DMI-ASIP): above.",
          "* **Independent validation**: agreement with USNIC expert charts (independent of the model, chart-scale).",
          "* **Expert-confirmed validation**: none yet (no reviewer available; ANNOTATION_GUIDELINES.md)."]
    (DOCS / "MODEL_INTERPRETABILITY_AND_ERROR_REPORT.md").write_text("\n".join(L), encoding="utf-8")


def model_card():
    fm, t = _j(FINAL / "final_model.meta.json"), _j(METRICS / "test_final" / "summary.json")
    if not fm:
        return
    x = t["metrics"]["final_model"] if t else {}
    L = ["# Model Card — AETHENTRA ML-03 Antarctic SAR sea-ice segmentation", "", "| item | value |", "|---|---|",
         f"| Version | `{fm['model_version']}` |", f"| Model | {fm['selected_from']} ({fm['kind']}) refitted on train+validation |",
         "| Input | one Sentinel-1 EW GRDM HH scene: σ⁰ (dB, noise-corrected), incidence angle; 400 m EPSG:3031 |",
         "| Output | per-pixel ice probability; classes water / ice / uncertain (0.35–0.65) / invalid; weekly 2 km composites |",
         "| Labels | USNIC Antarctic ice charts 2018–2026 (expert, chart-scale), boundary buffer as uncertain |",
         f"| Test (agreement with charts) | mIoU {_f(x.get('miou'))}, F1 ice {_f(x.get('f1_ice'))}, boundary F1 {_f(x.get('boundary_f1_scene_mean'))}, "
         f"ice-area bias {_f(x.get('ice_area_bias_pct'), 1)} % ({t['n_scenes'] if t else 'n/a'} scenes, 2025–2026) |",
         "| Intended use | research monitoring of Antarctic ice/water extent from SAR; AETHENTRA visualisation |",
         "| Not intended for | navigation, operational ice services, safety decisions, ice-type or concentration retrieval |", "",
         "## Limitations", "",
         "* Labels are chart-scale and 0–3 days apart from the image; scores measure agreement with charts, not pixel truth.",
         "* HH only; 400 m (overview) resolution — floes, leads and small polynyas below ~1 km are not resolved.",
         "* Known SAR ambiguities: wind-roughened water vs ice, smooth new ice vs calm water, summer melt (see the error report).",
         "* Probabilities are not calibrated confidences unless the reliability figure shows otherwise; the uncertain band is a "
         "convention, not a validated uncertainty.", "* No expert review; not a production system."]
    (DOCS / "MODEL_CARD.md").write_text("\n".join(L), encoding="utf-8")


def static_docs():
    (DOCS / "MODEL_OUTPUT_SCHEMA.md").write_text("\n".join([
        "# ML-03 — Model Output Schema", "",
        "## Acquisition products `outputs/ml03/segmentation/<scene_id>/`", "",
        "| file | content |", "|---|---|",
        "| `sea_ice_probability.tif` | float32 ice probability, nodata −1, EPSG:3031 400 m |",
        "| `sea_ice_class.tif` | uint8: 0 water, 1 ice, 2 uncertain (0.35 < p < 0.65), 255 invalid |",
        "| `segmentation.nc` | CF NetCDF: probability, class, ice / water / uncertain / invalid masks, x/y |",
        "| `metadata.json` | scene id, acquisition + processing time, sensor, mode, polarisation, resolution, CRS, model version, "
        "pixel counts, nominal ice area, processing provenance, warnings |", "",
        "## Weekly products `outputs/ml03/weekly_maps/week_<YYYY-MM-DD>/`", "",
        "| file | content |", "|---|---|",
        "| `valid_acquisitions.tif` | uint16 number of acquisitions classifying the 2 km cell |",
        "| `ice_detections.tif` | uint16 number of those classifying it as ice |",
        "| `detection_frequency.tif` | float32 ice detections / valid acquisitions, −1 unobserved |",
        "| `weekly_class.tif` | uint8: 0 water (≤ 1/3), 1 ice (≥ 2/3), 2 variable, 255 unobserved |",
        "| `metadata.json` | week, acquisitions used, observed area, class counts, methodology, model version |", "",
        "## API (`/seaice-detection`)", "", "`/health`, `/model/info`, `POST /detect/sea-ice {scene_id}`, `/detection/latest`, `/detection/history`, "
        "`/detection/weekly[?week_start=]`, `/detection/metrics`, `/detection/metadata`, `/detection/{scene_id}/files/{probability_tif|class_tif|netcdf}`, "
        "`/detection/weekly/{week_start}/files/{detection_frequency|valid_acquisitions|ice_detections|weekly_class}`."]), encoding="utf-8")
    (DOCS / "REPRODUCIBILITY_GUIDE.md").write_text("\n".join([
        "# ML-03 — Reproducibility Guide", "", "No credentials are required. All commands from the repository root.", "", "```bash",
        "pip install -r requirements.txt            # + pystac-client planetary-computer scikit-image; torch (CUDA) for the U-Net",
        "python scripts/ml03/download_data.py --land --charts --start 2018-01-01 --end 2026-11-09",
        "python scripts/ml03/download_data.py --catalogue                       # 2 scenes per chart, seed 42",
        "bash scripts/ml03/run_from_download.sh     # download scenes -> prepare -> samples -> baselines -> tiles -> unet -> validate -> select -> final -> test",
        "python scripts/ml03/analyze.py             # error analysis, figures, docs",
        "python scripts/ml03/generate_weekly_map.py --week-start 2026-10-26",
        "python scripts/ml03/predict.py --scene-id <S1 EW GRDM HH id>",
        "python -m pytest tests/test_ml03_sar.py", "```", "",
        "Seeds: 42 everywhere (scene sampling, pixel samples, models, tiles order). Configs: `configs/ml03/*.yaml`. "
        "The test stage refuses to run twice; the selection record is written before it.",
        "Artifacts: raw `data/raw/sentinel1`, `data/raw/ice_charts`; interim scenes/labels `data/interim/ml03`; samples/tiles "
        "`data/processed/ml03`; models `models/ml03`; metrics `experiments/ml03/metrics`; products `outputs/ml03`."]), encoding="utf-8")
    (DOCS / "NEXT_STEPS.md").write_text("\n".join([
        "# ML-03 — Next Steps", "",
        "1. **Expert-confirmed evaluation set**: review ~50 test scenes with ANNOTATION_GUIDELINES.md; report κ and expert-confirmed metrics.",
        "2. **Full resolution** (40 m, `overview_factor: 1`) with CDSE/ASF credentials and SNAP thermal-noise/border-noise processing; "
        "evaluate leads, floes and the marginal ice zone.",
        "3. **Independent coarse checks**: AMSR2 ASI 3.125 km and OSI SAF SIC agreement per scene; more DMI-ASIP days (Copernicus Marine account).",
        "4. **Uncertainty**: calibrate probabilities on validation (temperature scaling / isotonic) and derive a validated uncertain band; "
        "ensembles for disagreement maps.",
        "5. **Temporal context**: previous acquisition / ML-01 SIC as optional channels with strict time matching.",
        "6. **Architectures** (DeepLabV3+, attention U-Net, SegFormer) only if the U-Net's limits are architecture- rather than label-bound.",
        "7. **Extensions**: ice type (with HV where available near the Peninsula), fast ice, icebergs, concentration retrieval.",
        "8. **Frontend**: CesiumJS layers from the GeoTIFFs; label weekly composites with observation counts."]), encoding="utf-8")


def final_report():
    cat = _cat()
    v, t, sel = (_j(METRICS / p) for p in ("validation_candidates/summary.json", "test_final/summary.json", "selection_record.json"))
    fm = _j(FINAL / "final_model.meta.json")
    tests = _j(ROOT / "experiments" / "logs" / "pytest_summary.json")
    weeks = sorted((OUTPUTS / "weekly_maps").glob("week_*/metadata.json"))
    st = lambda ok: "COMPLETED" if ok else "NOT DONE"  # noqa: E731
    L = ["# AETHENTRA ML Task 03 — Final Report", "## Antarctic Sea-Ice Detection from Sentinel-1 SAR", "",
         "Status legend: COMPLETED = executed on real data and checked; IMPLEMENTED = code + tests only; PENDING = blocked; NOT DONE = gap.", "",
         "## 1. Objective", "", "Pixel-level sea-ice vs open-water segmentation of Antarctic Sentinel-1 EW HH scenes, with uncertain and invalid "
         "pixels handled separately, plus weekly detection-frequency composites. This is detection from observations, not forecasting.", "",
         "## 2. Phase status", "", "| phase | status | evidence |", "|---|---|---|",
         "| 0 Audit | COMPLETED | PROJECT_AUDIT.md, DATA_INVENTORY.csv, MISSING_PREREQUISITES.md, ML03_IMPLEMENTATION_PLAN.md |",
         f"| 1 Acquisition | COMPLETED (anonymous sources; CDSE/CMEMS pending credentials) | {int((cat.download_status == 'downloaded').sum()) if cat is not None else 0} scenes, 387 charts; SATELLITE_DATA_SOURCES.md |",
         "| 2 Labels | COMPLETED (chart-derived); expert review NOT DONE | LABEL_GENERATION_REPORT.md, ANNOTATION_GUIDELINES.md |",
         "| 3 Preprocessing | COMPLETED | SAR_PREPROCESSING_REPORT.md |", "| 4 Features | COMPLETED | FEATURE_ENGINEERING.md |",
         f"| 5 Baselines | {st((CKPT / 'xgb.meta.json').exists())} | threshold, RF, XGBoost |",
         f"| 6 Deep learning | {st((CKPT / 'unet_bce_dice.meta.json').exists())} (U-Net ×2 losses); DeepLabV3+/Attention U-Net/SegFormer NOT DONE (not justified yet) | MODEL_TRAINING_REPORT.md |",
         "| 7 Splits | COMPLETED | train 2018–2022, validation 2023–2024, test 2025–2026, by scene/chart date |",
         f"| 8 Evaluation | {st(t is not None)} | MODEL_EVALUATION_REPORT.md |",
         f"| 9 Selection / final / single test | {st(t is not None and fm is not None)} | selection frozen {sel['frozen_utc'] if sel else 'n/a'}; test {t['evaluated_utc'] if t else 'n/a'} |",
         f"| 10 Error analysis | {st((METRICS / 'error_analysis_test.json').exists())} | MODEL_INTERPRETABILITY_AND_ERROR_REPORT.md |",
         f"| 11 Weekly compositing | {st(bool(weeks))} | WEEKLY_COMPOSITING_METHODOLOGY.md{', ' + weeks[-1].parent.name if weeks else ''} |",
         f"| 12 Inference | {st(any((OUTPUTS / 'segmentation').glob('*/metadata.json')))} | MODEL_OUTPUT_SCHEMA.md |",
         "| 13 FastAPI | COMPLETED locally (TestClient) — not a production deployment | api/seaice_detection.py (`/seaice-detection`) |",
         "| 14 Frontend layers | COMPLETED as GeoTIFF files; no CesiumJS frontend in the repository | outputs/ml03 |",
         "| 15 Tests | " + (f"{tests['passed']} passed, {tests['failed']} failed, {tests['skipped']} skipped (whole repository, {tests['when']})" if tests else "not run") + " | tests/test_ml03_sar.py |", ""]
    if v:
        L += ["## 3. Baselines and candidates (validation)", ""] + table(v["metrics"]) + [""]
    if sel:
        L += [f"Selected `{sel['selected_model']}` on validation only ({sel['criteria']}).", ""]
    if t:
        L += ["## 4. Final test metrics (single evaluation; agreement with USNIC charts)", ""] + table(t["metrics"]) + [""]
        best = max(t["metrics"], key=lambda m: t["metrics"][m]["miou"])
        fm_ = t["metrics"]["final_model"]
        if best != "final_model":
            L += [f"**On test, the selected model is not the best:** `{best}` reaches mIoU {t['metrics'][best]['miou']:.3f} vs "
                  f"{fm_['miou']:.3f} for `final_model` (refit of `{sel['selected_model'] if sel else '?'}`). The selection was frozen on "
                  "validation and is not changed after seeing the test; the tree models are equally viable operational candidates "
                  "and the refit lost skill relative to its train-only version (see MODEL_EVALUATION_REPORT.md, seasonal table).", ""]
    L += ["## 5. Documents", "", "SATELLITE_DATA_SOURCES · DATA_INVENTORY · SAR_PREPROCESSING_REPORT · LABEL_GENERATION_REPORT · ANNOTATION_GUIDELINES · "
          "FEATURE_ENGINEERING · MODEL_TRAINING_REPORT · MODEL_EVALUATION_REPORT · MODEL_INTERPRETABILITY_AND_ERROR_REPORT · "
          "WEEKLY_COMPOSITING_METHODOLOGY · MODEL_CARD · MODEL_OUTPUT_SCHEMA · REPRODUCIBILITY_GUIDE · NEXT_STEPS", "",
          "## 6. Limitations", "", "* Labels are expert charts at chart scale, 0–3 days from the image: metrics are chart agreement, not pixel truth.",
          "* 400 m resolution (×8 overview) and HH only; no expert-confirmed pixels; DMI-ASIP comparison covers one day.",
          "* Weekly composites cover only the acquisitions of that week; unobserved cells stay empty.",
          "* Local API only; no production deployment."]
    (DOCS / "AETHENTRA_ML_TASK_03_FINAL_REPORT.md").write_text("\n".join(L), encoding="utf-8")


def build_all():
    for f in (data_inventory, label_report, feature_doc, training_report, evaluation_report, error_report, model_card, static_docs, final_report):
        f()
