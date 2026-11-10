# Model Training Report — AETHENTRA ML Task 01

Generated from `models/**/meta.json`, `experiments/metrics/*` and table metadata.

## 1. Split configuration (by forecast issue date)

| Split | Issue dates from | to | Rule |
|---|---|---|---|
| train | 1979-01-01 | 2015-12-31 | full target window (t+1..t+7) inside the split; 7-day cadence |
| validation | 2016-01-01 | 2020-12-31 | full target window (t+1..t+7) inside the split; 7-day cadence |
| test | 2021-01-01 | 2025-12-31 | full target window (t+1..t+7) inside the split; 7-day cadence |

Climatology (SIC and atmosphere) for training/validation: fitted on 1979–2015 only. Final refit: 1979–2020. Test years never enter a fit.
All cells of one issue date stay in the same split (splits are by date, never by cell).

## 2. Training tables

| Table | Issue dates | Rows | Sample fraction | Seconds | Dates without rows |
|---|---|---|---|---|---|
| test_sample_fit1979-2020 | 260 | 508,363 | 0.05 | 33 | 0 |
| train_fit1979-2015 | 1929 | 3,012,256 | 0.04 | 217 | 12 |
| trainval_fit1979-2020 | 2190 | 3,433,423 | 0.04 | 520 | 12 |
| validation_fit1979-2015 | 260 | 1,511,821 | 0.15 | 45 | 0 |

## 3. Candidate models (trained on 1979–2015, early stopping on the 2016–2020 validation sample)

| Model | Family | Target | Features | Train rows | Best iteration | Fit time (s) | RSS after fit (GB) |
|---|---|---|---|---|---|---|---|
| LightGBM residual | lightgbm | residual | 40 | 3,012,256 | 959 | 165 | 1.6 |
| LightGBM absolute | lightgbm | absolute | 40 | 3,012,256 | 1349 | 242 | 1.7 |
| LightGBM residual, SIC-only | lightgbm | residual | 33 | 3,012,256 | 1055 | 137 | 1.6 |
| XGBoost residual | xgboost | residual | 40 | 3,012,256 | 2191 | 116 | 2.0 |
| Random forest residual | random_forest | residual | 40 | 600,000 | 200 | 240 | 2.1 |

Hyper-parameters as currently in `configs/training.yaml`. **The candidate table above (read from each checkpoint's `.meta.json`) is authoritative for what was actually trained**: the random-forest budget in the config (`n_estimators`, `max_train_rows`) and the Optuna budget were reduced after the candidates were trained to shorten re-runs; the trained RF used the values recorded in `models/checkpoints/rf_residual.meta.json`.

```yaml
{
  "lightgbm": {
    "objective": "regression_l1",
    "learning_rate": 0.05,
    "num_leaves": 127,
    "min_data_in_leaf": 200,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "n_estimators": 3000,
    "early_stopping_rounds": 100
  },
  "xgboost": {
    "objective": "reg:absoluteerror",
    "learning_rate": 0.05,
    "max_depth": 8,
    "min_child_weight": 50,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "n_estimators": 3000,
    "early_stopping_rounds": 100,
    "device": "cuda"
  },
  "random_forest": {
    "n_estimators": 100,
    "max_depth": 20,
    "min_samples_leaf": 50,
    "max_features": 0.5,
    "max_train_rows": 300000
  }
}
```

## 4. Hyper-parameter optimisation (Optuna TPE, validation only)

* Trials completed: 5 (budget 12 trials / 1500 s).
* Objective: MAE (pp) of residual on the validation sample (model domain cells).
* Untuned candidate: 2.805 pp; best trial: 2.795 pp (best iteration 960).
* Best parameters: `{"learning_rate": 0.0425378509573798, "num_leaves": 445, "min_data_in_leaf": 578, "feature_fraction": 0.759195090518222, "bagging_fraction": 0.5780093202212182, "lambda_l2": 0.004993515273965262}`

## 5. Model selection (frozen before any test access)

* Selected: **LightGBM residual (Optuna-tuned)** (lightgbm, target = residual, 40 features), at 2026-11-07T22:46:50+00:00.
* Criteria: rank-sum over validation SIZ MAE, SIZ RMSE, IIEE, extent MAE; ties -> simpler model.
* Best baseline on validation: Persistence (latest day); selected model beats it on all criteria: True.

| Method | SIZ MAE | SIZ RMSE | IIEE (10³ km²) | Extent MAE (10³ km²) | Rank sum |
|---|---|---|---|---|---|
| Anomaly persistence | 4.61 | 9.65 | 866 | 305 | baseline |
| Climatology (train) | 9.57 | 17.17 | 2,351 | 1,933 | baseline |
| LightGBM absolute | 3.09 | 7.20 | 588 | 107 | 13 |
| LightGBM residual | 3.07 | 7.15 | 586 | 118 | 10 |
| LightGBM residual, SIC-only | 3.10 | 7.24 | 593 | 122 | 21 |
| Linear 7-day trend | 4.68 | 10.52 | 723 | 345 | baseline |
| Persistence (latest day) | 3.81 | 8.77 | 705 | 393 | baseline |
| Persistence (7-day mean) | 4.83 | 11.03 | 967 | 624 | baseline |
| Random forest residual | 3.30 | 7.08 | 609 | 171 | 19 |
| XGBoost residual | 3.07 | 7.16 | 588 | 120 | 15 |
| LightGBM residual (Optuna-tuned) | 3.06 | 7.13 | 586 | 117 | 6 |

## 6. Final model

* Version: `aethentra-sic-weekly-20261108-v1`; file `models/final/final_model.lgb.txt`; trained 2026-11-07T23:02:24+00:00.
* Training period 1979-01-01 … 2020-12-31 (3,433,423 rows), 745 trees (1.1 x validation best_iteration), no early stopping (no held-out data remain).
* Climatology artifact: `models/artifacts/sic_climatology_1979_2020.npz` (copied to `models/final/sic_climatology.npz`).
* Fit time 340 s. Seed 42.
* Quantile companions `final_q10`, `final_q90` (LightGBM quantile loss, residual target) trained on the same data.

## 7. Overfitting monitoring

Loss curves: `models/checkpoints/*.history.json` and Figure `02_learning_curves`. Early stopping halts boosting when the validation loss stops improving for 100 rounds; the train–validation gap is shown in the figure.