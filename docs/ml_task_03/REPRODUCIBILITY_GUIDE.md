# ML-03 — Reproducibility Guide

No credentials are required. All commands from the repository root.

```bash
pip install -r requirements.txt            # + pystac-client planetary-computer scikit-image; torch (CUDA) for the U-Net
python scripts/ml03/download_data.py --land --charts --start 2018-01-01 --end 2026-11-09
python scripts/ml03/download_data.py --catalogue                       # 2 scenes per chart, seed 42
bash scripts/ml03/run_from_download.sh     # download scenes -> prepare -> samples -> baselines -> tiles -> unet -> validate -> select -> final -> test
python scripts/ml03/analyze.py             # error analysis, figures, docs
python scripts/ml03/generate_weekly_map.py --week-start 2026-10-26
python scripts/ml03/predict.py --scene-id <S1 EW GRDM HH id>
python -m pytest tests/test_ml03_sar.py
```

Seeds: 42 everywhere (scene sampling, pixel samples, models, tiles order). Configs: `configs/ml03/*.yaml`. The test stage refuses to run twice; the selection record is written before it.
Artifacts: raw `data/raw/sentinel1`, `data/raw/ice_charts`; interim scenes/labels `data/interim/ml03`; samples/tiles `data/processed/ml03`; models `models/ml03`; metrics `experiments/ml03/metrics`; products `outputs/ml03`.