# ML-03 — Model Training Report

Splits by chart date (scene-level, before tiling): train 2018-01-01…2022-12-31, validation 2023-01-01…2024-12-31, test 2025-01-01…2026-12-31.

| model | status | checkpoint | key settings |
|---|---|---|---|
| threshold | COMPLETED (checkpoint verified) | `models/ml03/checkpoints/threshold.pkl` | slope 0.020 dB/°, threshold -16.40 dB at 35°, train bal. acc. 0.695 |
| rf | COMPLETED (checkpoint verified) | `models/ml03/checkpoints/rf.pkl` | {'n_estimators': 300, 'max_depth': 18, 'min_samples_leaf': 20, 'class_weight': 'balanced', 'n_jobs': 8}; iterations 300; fit 119 s |
| xgb | COMPLETED (checkpoint verified) | `models/ml03/checkpoints/xgb.pkl` | {'n_estimators': 2000, 'learning_rate': 0.05, 'max_depth': 8, 'subsample': 0.8, 'colsample_bytree': 0.8, 'reg_lambda': 1.0, 'early_stopping_rounds': 100, 'device': 'cuda', 'eval_metric': 'logloss'}; iterations 85; fit 6 s |
| unet_bce | COMPLETED (checkpoint verified) | `models/ml03/checkpoints/unet_bce.pt` | 7,763,329 params, loss BCE, 27 epochs (best 19, val tile mIoU 0.934), 6387 tiles, 45 min on NVIDIA GeForce RTX 4060 Laptop GPU |
| unet_bce_dice | COMPLETED (checkpoint verified) | `models/ml03/checkpoints/unet_bce_dice.pt` | 7,763,329 params, loss (1-0.5)*BCE + 0.5*Dice, 26 epochs (best 18, val tile mIoU 0.935), 6387 tiles, 44 min on NVIDIA GeForce RTX 4060 Laptop GPU |
| **final_model** (unet_bce_dice, train+validation) | COMPLETED | `models/ml03/final/` | version aethentra-sar-seaice-20261109-v1 |

U-Net: AdamW + OneCycle, batch 16, bf16 autocast, seed 42, early stopping on validation tile mIoU (patience 8); augmentation rot90/flip/gain/noise (SAR look direction varies between orbits, so orientation carries no physical meaning). Uncertain (2) and invalid (255) pixels are excluded from the loss.

Hyper-parameter optimisation: the U-Net loss (BCE vs BCE+Dice) was compared on validation; no further search was run (see NEXT_STEPS.md). The test split was never used for any choice.