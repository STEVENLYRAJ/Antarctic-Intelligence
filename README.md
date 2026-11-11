# AETHENTRA — Scientific Intelligence Platform

Antarctic climate & cryosphere data and models. Repository layout:

| Path | Content |
|---|---|
| `DATAS/` | User-collected raw Antarctic datasets (read-only) |
| `EXTERNAL APIs/` | Copernicus CDS ERA5 request scripts (`API.py`, `PRESSUREAPI.py`) |
| `data/src/preprocessing/antarctic/` | Stage 1: inventory / validation / preprocessing of `DATAS/` (`python -m data.src.preprocessing.antarctic.run_pipeline`) |
| `src/aethentra/` | **ML Task 01**: weekly Antarctic sea-ice concentration forecasting (data, preprocessing, features, baselines, models, training, evaluation, inference, visualization, reporting) |
| `configs/` | YAML configuration for Task 01 (data sources, preprocessing, features, training, evaluation) |
| `scripts/` | CLI entry points (download, preprocess, validate, train, analyze, figures, predict, docs) |
| `api/` | FastAPI forecast service |
| `models/` | `checkpoints/` (candidates), `final/` (frozen final model bundle), `artifacts/` (climatologies) |
| `experiments/` | logs and metrics (validation, tuning, selection record, single test evaluation) |
| `outputs/` | figures, data-validation reports, forecasts + frontend layers |
| `docs/ml_task_01/` | Task 01 documentation (start with `AETHENTRA_ML_TASK_01_FINAL_REPORT.md`) |
| `src/aethentra/temperature/` | **ML Task 02**: weekly Antarctic 2 m temperature & anomaly forecasting (configs `configs/ml02/`, scripts `scripts/ml02/`, API router `/temperature`) |
| `docs/ml_task_02/` | Task 02 documentation (start with `AETHENTRA_ML_TASK_02_FINAL_REPORT.md`) |
| `notebooks/` | `01_temperature_exploration.ipynb` (ML-02) |
| `metadata/`, `reports/` | Stage 1 manifests and Word report |

## ML Task 01 quick start

```bash
pip install -r requirements.txt
python scripts/download_data.py --all       # public data only, MD5-verified, resumable
python scripts/preprocess.py
python scripts/validate_data.py
python scripts/train.py tables && python scripts/train.py candidates
python scripts/analyze.py features
python scripts/train.py tune && python scripts/train.py select && python scripts/train.py final
python scripts/train.py test                # single evaluation on 2021-2025
python scripts/analyze.py final && python scripts/make_figures.py
python scripts/predict.py                   # latest weekly forecast -> outputs/forecasts/
python scripts/build_docs.py
python -m pytest tests/
uvicorn api.main:app --port 8000
```

Full details: `docs/ml_task_01/REPRODUCIBILITY_GUIDE.md`. No credentials are required; see `.env.example` for optional ERA5 /
Copernicus Marine / Earthdata extensions. Never commit `.env`.

## ML Task 02 quick start (weekly 2 m temperature / anomaly)

```bash
python scripts/ml02/download_data.py --stations --ncep-interim   # anonymous; --era5 needs %USERPROFILE%\.cdsapirc
python scripts/ml02/preprocess.py --source ncep_r1
python scripts/ml02/validate_data.py --source ncep_r1
bash scripts/ml02/run_all.sh ncep_r1        # tables -> models -> Optuna -> select -> final -> single test -> analysis -> figures -> forecast
python scripts/ml02/build_docs.py
python -m pytest tests/test_ml02_temperature.py
```

ML-02 currently uses **NCEP/NCAR R1 as an interim substitute for ERA5** (no CDS key was available); see
`docs/ml_task_02/TEMPERATURE_DATA_SOURCES.md` for the switch to ERA5.

## Web viewer and local API

```bash
bash scripts/serve.sh                       # API + viewer on http://127.0.0.1:8000/  (loopback only)
```

`/viewer/` shows the latest sea-ice and 2 m temperature forecasts as polar-stereographic maps rendered from the native
EPSG:3412 GeoTIFFs, with every layer labelled as observation / reanalysis / model prediction / evaluation. API documentation
is at `/docs`. This is a local service, not a production deployment (no authentication, TLS or public hosting).

## Spatial deep-learning addendum (U-Net, both tasks)

```bash
python -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu124   # CUDA build, ~2.5 GB
bash scripts/ml02/run_cnn.sh ncep_r1        # stacks -> train -> validate -> frozen decision -> refit -> single test
bash scripts/run_ml01_cnn.sh
```

The U-Net runs after the tree-model selection and test were frozen. It replaces a tree model only if it is better on every
validation selection metric; that decision is written to `addendum_cnn_decision_record.json` before its single test evaluation.

## ML Task 03 quick start (Sentinel-1 SAR sea-ice detection)

```bash
pip install -r requirements.txt                                   # + torch (CUDA) for the U-Net
python scripts/ml03/download_data.py --land --charts --start 2018-01-01 --end 2026-11-09   # USNIC charts, anonymous
python scripts/ml03/download_data.py --catalogue --scenes         # Sentinel-1 EW HH via Planetary Computer, anonymous
python scripts/ml03/run_all.py                                    # prepare -> samples -> baselines -> tiles -> U-Nets -> validate -> select -> final -> test -> analysis/docs
python scripts/ml03/generate_weekly_map.py --week-start 2026-11-02
python scripts/ml03/predict.py --scene-id <S1 EW GRDM HH id>
python -m pytest tests/test_ml03_sar.py
```

Labels are USNIC Antarctic ice charts (expert, chart-scale), so every ML-03 metric is *agreement with the charts*, not pixel truth.
Results and limitations: `docs/ml_task_03/AETHENTRA_ML_TASK_03_FINAL_REPORT.md`. API under `/seaice-detection`; weekly layers in
the viewer's "SAR sea-ice detection" tab.

## ML Task 04 quick start (Antarctic climate anomaly detection)

Public data only (NCEP/NCAR R1 daily via NOAA PSL OPeNDAP, NOAA/NSIDC SIC CDR v6); no credentials needed.

```bash
python scripts/ml04/run_all.py                 # download -> preprocess -> baselines -> features -> fit -> validate (frozen)
                                               # -> test (once) -> score -> products -> export -> store
python scripts/ml04/run_all.py --from score    # rebuild products from the saved detectors
python scripts/ml04/update_pipeline.py --check # are newer source data available?
python -m pytest tests/test_ml04_anomaly.py
```

API under `/api/ml04` (health, model-info, detect, latest, anomalies, monthly-summary, seasonal-summary, spatial-data, metrics,
data-coverage, events, compound, sea-ice-extent); dashboard at `/viewer/#anom`. Documentation: `docs/ml_task_04/`
(progress tracker, audit, data inventory and documentation, model card, scientific limitations, test report).
Note: NOAA PSL's NCEP R1 daily record ends 2026-03-17, so multivariate anomalies stop at February 2026.
