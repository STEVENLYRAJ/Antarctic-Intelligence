# Next Steps — after AETHENTRA ML Task 01

Ordered by expected scientific value per unit of effort.

1. **Replace the interim atmosphere with ERA5** (needs a CDS token): daily-mean 2 m temperature, 10 m winds, MSLP and SST south of 35°S,
   1979–present. Use `data/src/preprocessing/antarctic/era5_api.py` (Antarctic-restricted, split by year) or adapt
   `src/aethentra/data/acquisition.py`. Re-run `train.py tables → … → test` with a **new** test protocol (the 2021–2025 test set has now
   been seen once; any new architecture should be compared on validation, and a fresh hold-out (e.g. 2026) reserved).
2. **Add forecast weather of the target week** (ECMWF/GFS ensemble means) — the largest missing physical driver at one-week lead;
   requires a reforecast archive for training to avoid train/inference mismatch.
3. **Independent gridded verification** against OSI SAF SIC CDR (CMEMS 011_009) to separate model error from product-algorithm error.
4. **Spatial deep learning** (U-Net on stacked SIC/atmosphere maps, IceNet-style) once PyTorch can be installed; compare on the same
   validation protocol and the same metrics. Use the tree model as the bar to beat.
5. **Sea-ice drift and thickness** (CMEMS 011_018 drift, CS2SMOS/PIOMAS-like thickness) as predictors near the ice edge.
6. **Probabilistic output**: recalibrate the quantile models (conformal calibration on validation) if coverage deviates; evaluate CRPS.
7. **Operationalise**: nightly job (download latest ICDR day → preprocess incrementally → predict → publish layers), monitoring of
   input coverage and of rolling forecast error against incoming observations; containerise the FastAPI service.
8. **Domain-expert review** of failure cases (summer melt, coastal polynyas, record-low 2023) before public communication.
9. **Repository hygiene**: move large raw data out of Git history (GLIMS shapefiles committed in `eb03a93`) using Git LFS or external storage.
