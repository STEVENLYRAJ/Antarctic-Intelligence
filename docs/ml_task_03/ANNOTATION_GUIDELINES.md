# ML-03 — Annotation Guidelines (expert review of chart-derived labels)

No human annotation was performed in this release; all labels are chart-derived. This protocol defines how reviewers should
correct or confirm labels so that an expert-confirmed evaluation set can be built.

## Classes

| value | class | rule |
|---|---|---|
| 0 | open water | visibly ice-free water (dark, or wind-roughened bright water with wave texture); ≤ 10 % ice |
| 1 | sea ice | consolidated / close pack, fast ice, new ice sheets, ≥ 70 % concentration |
| 2 | uncertain / mixed | 10–70 % concentration, marginal ice zone, ambiguous texture, melt-affected ice, wind-roughened water you cannot rule out as ice |
| 255 | invalid | land, ice shelves, icebergs larger than ~1 km, no data, image artefacts (noise stripes, RFI) |

Never force mixed pixels into 0 or 1. When unsure, use 2.

## Workflow (QGIS)

1. Open the scene's `sea_ice_probability.tif` / σ⁰ preview and the chart-derived label (`data/interim/ml03/labels/<scene>.npz`,
   export with `scripts/ml03/export_review_tiles.py`, planned) in EPSG:3031.
2. Edit the label raster with the *Serval* plugin (or polygonise, edit, re-rasterise at 400 m).
3. Record reviewer, date, time spent, confidence (high / medium / low) and the reference imagery used in the scene's review JSON.
4. Two reviewers per scene for 10 % of scenes; report Cohen's κ.

## Hard cases

Wind-roughened open water (bright, wave streaks) · grease/nilas (dark ice) · melt ponds and wet snow in summer · coastal polynyas
· fast ice vs ice shelf (use the ice-shelf mask, mark doubtful fronts 255) · icebergs and berg-dense water (255) · incidence-angle
gradient across the EW swath (near range bright).

CVAT or Label Studio can be used instead of QGIS for tile-based review; keep georeferencing by exporting tiles with their
geotransform.
