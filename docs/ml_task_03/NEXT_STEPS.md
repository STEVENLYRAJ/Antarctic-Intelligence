# ML-03 — Next Steps

1. **Expert-confirmed evaluation set**: review ~50 test scenes with ANNOTATION_GUIDELINES.md; report κ and expert-confirmed metrics.
2. **Full resolution** (40 m, `overview_factor: 1`) with CDSE/ASF credentials and SNAP thermal-noise/border-noise processing; evaluate leads, floes and the marginal ice zone.
3. **Independent coarse checks**: AMSR2 ASI 3.125 km and OSI SAF SIC agreement per scene; more DMI-ASIP days (Copernicus Marine account).
4. **Uncertainty**: calibrate probabilities on validation (temperature scaling / isotonic) and derive a validated uncertain band; ensembles for disagreement maps.
5. **Temporal context**: previous acquisition / ML-01 SIC as optional channels with strict time matching.
6. **Architectures** (DeepLabV3+, attention U-Net, SegFormer) only if the U-Net's limits are architecture- rather than label-bound.
7. **Extensions**: ice type (with HV where available near the Peninsula), fast ice, icebergs, concentration retrieval.
8. **Frontend**: CesiumJS layers from the GeoTIFFs; label weekly composites with observation counts.