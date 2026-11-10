# Reproducibility Guide — AETHENTRA ML Task 01

Everything below runs from the repository root with public data only (no credentials).
Tested environment: Windows 11, Python 3.11.9, 16 logical cores, 23.7 GB RAM, RTX 4060 8 GB (XGBoost uses CUDA; LightGBM/RF CPU).

## 1. Environment
```bash
python -m pip install -r requirements.txt
cp .env.example .env        # optional; only for ERA5 / Copernicus Marine / Earthdata extensions
```
Key versions used: numpy 2.4, pandas 3.0, xarray 2026.9, netCDF4 1.7.4, scikit-learn 1.9.1, lightgbm 4.7.0, xgboost 3.2.0,
optuna 5.0.0, scipy 1.17.1, fastapi 0.135, pydantic 2.12.

## 2. Full workflow (in order)
| Step | Command | Output | Time (this machine) |
|---|---|---|---|
| Acquire SIC CDR (≈3.3 GB, MD5-verified, resumable) | `python scripts/download_data.py --cdr` | `data/raw/aethentra/nsidc_g02202_v6/` + `.provenance.json` | ≈1.5–2 h at 0.5 MB/s |
| Acquire NCEP R1 atmosphere (OPeNDAP subset) | `python scripts/download_data.py --ncep` | `data/raw/aethentra/ncep_r1/` | ≈20 min |
| Preprocess (native-grid cube, masks, areas, QA) | `python scripts/preprocess.py` | `data/interim/aethentra/` | minutes |
| Validate data | `python scripts/validate_data.py` | `outputs/reports/data_validation/`, `outputs/figures/data_quality/` | minutes |
| Training tables | `python scripts/train.py tables` | `data/processed/aethentra/tables/` | |
| Candidates + validation | `python scripts/train.py candidates` | `models/checkpoints/`, `experiments/metrics/validation_candidates/` | |
| Feature analysis (validation) | `python scripts/analyze.py features` | `experiments/metrics/analysis/` | |
| Hyper-parameter tuning | `python scripts/train.py tune` | `experiments/metrics/optuna_lightgbm.json` | ≤ 1 h |
| Freeze selection (before test) | `python scripts/train.py select` | `experiments/metrics/selection_record.json` | |
| Final refit 1979–2020 | `python scripts/train.py final` | `models/final/` | |
| **Single** test evaluation | `python scripts/train.py test` | `experiments/metrics/test_final/` (refuses to rerun) | |
| Interpretation + plausibility | `python scripts/analyze.py final` | `experiments/metrics/analysis/` | |
| Figures | `python scripts/make_figures.py` | `outputs/figures/ml_task_01/` | |
| Forecast + frontend layers | `python scripts/predict.py [--issue-date YYYY-MM-DD]` | `outputs/forecasts/<forecast_id>/` | seconds |
| Reports | `python scripts/build_docs.py` | `docs/ml_task_01/*.md` (numbers read from artifacts) | |
| Tests | `python -m pytest tests/test_aethentra_seaice.py` | | |
| API | `uvicorn api.main:app --port 8000` | http://localhost:8000/docs | |

Each training stage is idempotent: existing checkpoints/tables are reused; delete them to retrain. The test stage refuses to run twice.

## 3. Determinism
* Seed 42 for table sampling, LightGBM, XGBoost, RandomForest and Optuna's TPE sampler (`configs/training.yaml`).
* GPU XGBoost histogram building can differ in the last digits between runs/drivers; LightGBM (CPU, fixed threads) is deterministic
  for a fixed thread count.
* All inputs are pinned by MD5 (`*.provenance.json`). The CDR's near-real-time year (2026) is updated by NSIDC; rerunning acquisition
  later fetches a newer partial-year file (the cube's input signature then changes and the cube is rebuilt).

## 4. Configuration files
`configs/data_sources.yaml`, `preprocessing.yaml`, `features.yaml`, `training.yaml`, `evaluation.yaml` — every threshold, split date,
window, model hyper-parameter and seed used by the code is read from these files.

## 5. Logs and experiment metadata
`experiments/logs/*.log` (one per command), `models/**/**.meta.json` (features, parameters, best iteration, rows, fit time, memory),
`models/**/**.history.json` (loss curves), `experiments/metrics/**/summary.json` (all metrics, physical checks).
