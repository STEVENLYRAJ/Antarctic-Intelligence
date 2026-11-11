# ML-03 — Sentinel-1 SAR Preprocessing

Implemented in `src/aethentra/sar/preprocessing.py` (`process_scene`); identical code path for training, evaluation and inference.
Configuration: `configs/ml03/sar_preprocessing.yaml`.

| step | applied | how / why |
|---|---|---|
| Product ingestion | yes | GRDM HH COG at the ×8 overview + GCPs; calibration and noise annotation XMLs; md5 + provenance |
| Metadata inspection | yes | mode, polarisation, orbit, looks, full/overview size; scenes not HH are rejected at inference |
| Precise orbit | not separately | GCPs of the GRD product (computed by ESA with the restituted/precise orbit, `s1:orbit_source`) are used directly; sub-pixel at 400 m |
| Thermal noise removal | yes | σ⁰ = (DN² − N)/A_σ², N = noiseRangeLut × noiseAzimuthLut (IPF ≥ 2.9); range-only for older products; floor −35 dB |
| Radiometric calibration | yes | σ⁰ from the product's own `sigmaNought` LUT |
| Speckle filtering | no | 6×2-look GRDM averaged ×64 in the overview (≈ 700 looks) — residual speckle is negligible at 400 m |
| Terrain correction | no | sea ice is at sea level; land and ice shelves are masked (2 km buffered Natural Earth coast + ice shelves) |
| Incidence angle | yes | sin θ = A_β²/A_σ² from the same LUT (exact identity σ⁰ = β⁰ sin θ); used as a channel and for normalisation |
| Reprojection / co-registration | yes | GCP warp (EPSG:4326 GCPs) to EPSG:3031, 400 m, bilinear on linear σ⁰, then dB |
| Polarisation alignment | n/a | HH only |
| Resolution standardisation | yes | every scene on the same 400 m EPSG:3031 lattice (grids snapped to multiples of 400 m) |
| Invalid pixels | yes | DN = 0, outside 18–48° incidence, outside the footprint, land/ice shelf → invalid |
| Image–label alignment | yes | chart polygons rasterised on the scene's own grid (same transform) |
| Tiling | yes | 256 × 256 tiles (102 km), stride 256, kept if ≥ 20 % chart-labelled water/ice; tiles inherit the scene's split |

Known limitation: the COG overview averages DN rather than DN², which biases overview σ⁰ low by a small, near-constant amount
(identical for every scene, so it does not affect relative contrasts or the trained models; absolute σ⁰ values should not be compared
with full-resolution literature values without this caveat).

Validation on the first processed scene (S1A EW 2023-02-02, Weddell Sea): incidence 18.3–45.2°, σ⁰ 5/50/95 % = −17.9/−9.8/−3.4 dB,
land mask aligned with the bright ice-sheet edge, coastal polynya visible as a dark band (`docs/ml_task_03` figures).
