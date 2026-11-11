# ML-03 — Weekly Compositing Methodology

Implemented in `src/aethentra/sar/inference.py` (`composite`, `export_weekly`); run with
`python scripts/ml03/generate_weekly_map.py --week-start YYYY-MM-DD`.

1. **Acquisitions**: every Sentinel-1 EW GRDM HH scene of the 7 days (centroid south of 55°S) is processed and classified by the
   final model; the acquisition-level products are kept (`outputs/ml03/segmentation/<scene>/`).
2. **Per acquisition → 2 km cell**: a 2 km EPSG:3031 cell (25 pixels of 400 m) is classified by that acquisition only if ≥ 13 of
   its pixels are classified water or ice (uncertain/invalid pixels excluded); its class is the majority of those pixels.
3. **Weekly layers per cell**:
   * `valid_acquisitions` = number of acquisitions that classified the cell,
   * `ice_detections` = number of those classifying it as ice,
   * `detection_frequency` = ice_detections / valid_acquisitions (fraction of valid looks that saw ice — **not** an ice
     concentration and not an average of binary masks over time without context),
   * `weekly_class` = ice if frequency ≥ 2/3, water if ≤ 1/3, otherwise *variable* (2); 255 = unobserved.
4. **Coverage**: cells with no valid acquisition are left unobserved; nothing is interpolated or filled from other weeks. The
   metadata reports the number of acquisitions and the observed area, so a weekly map never implies continuous observation.

Limitations: acquisitions within a week are taken at different times (ice drifts tens of km per week near the edge), so
*variable* cells near the ice edge are expected; the frequency is model-based and inherits the model's error characteristics.
