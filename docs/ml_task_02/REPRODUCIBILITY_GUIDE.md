# AETHENTRA ML-02 — Reproducibility Guide

Environment: Python 3.11, `pip install -r requirements.txt` (ML-02 adds `cdsapi`, `nbformat`). Seed 42 everywhere
(`configs/ml02/training.yaml`). Hardware used: 8-core CPU, 25 GB RAM, RTX 4060 8 GB (XGBoost `device: cuda`; falls back to CPU).

```bash
# 1. data (anonymous sources; ERA5 additionally needs %USERPROFILE%\.cdsapirc)
python scripts/ml02/download_data.py --stations --ncep-interim
# 2. preprocessing + validation (Phase 2/3)
python scripts/ml02/preprocess.py --source ncep_r1
python scripts/ml02/validate_data.py --source ncep_r1
# 3. everything after preprocessing, fail-fast (tables -> candidates -> features analysis -> Optuna -> select -> final -> TEST ONCE
#    -> interpretation -> stations -> figures -> forecast with layers)
bash scripts/ml02/run_all.sh ncep_r1
# 4. documents from artefacts, tests, API
python scripts/ml02/build_docs.py
python -m pytest tests/test_ml02_temperature.py
uvicorn api.main:app --port 8000        # ML-02 under /temperature
```

Each stage is cached (tables, checkpoints, climatology); delete the corresponding artefact to recompute it. The test stage
refuses to run twice (`experiments/ml02/metrics/test_final/summary.json`). Logs: `experiments/logs/ml02_*.log`.

| Artefact | Path |
|---|---|
| Raw data + provenance | `data/raw/ncep_r1_2m/`, `data/raw/aethentra/ncep_r1/`, `data/raw/station_observations/`, (`data/raw/era5/`) |
| Daily cube | `data/interim/ml02/<source>/` |
| Tables | `data/processed/ml02/tables/` |
| Climatology, σ, damped-persistence α | `models/ml02/artifacts/` and `models/ml02/final/` |
| Candidate checkpoints / final bundle | `models/ml02/checkpoints/`, `models/ml02/final/` |
| Metrics, selection record, test | `experiments/ml02/metrics/` |
| Figures, reports | `outputs/ml02/figures/`, `outputs/ml02/reports/` |
| Forecasts + layers | `outputs/ml02/forecasts/<forecast_id>/` |

Determinism: LightGBM/XGBoost/RF are seeded; LightGBM multithreading can produce last-digit differences; XGBoost on GPU vs CPU
differs slightly. Table sampling is seeded per split.
