# ML-03 — Label Generation Report

Labels are rasterised USNIC Antarctic chart polygons on each scene's 400 m EPSG:3031 grid (`src/aethentra/sar/labels.py`).

* Mapping (SIGRID-3 total concentration CT): water = ['00', '01', '02']; sea ice = lower bound ≥ 70 % (incl. 91/92); 10–70 % → uncertain; undetermined codes → invalid.
* Boundary buffer: water/ice pixels within 4 km of another class → uncertain (chart scale and the 0–3 day chart/scene time mismatch).
* Chart pairing: scene acquired 0–3 days before the chart valid date; the 80 acquisitions closest to the chart date are searched and 2 per chart drawn, stratified by sector.
* Invalid: land/ice shelf (Natural Earth + 2 km), no SAR, incidence outside 18–48°, outside chart polygons.
* Usability rule (fixed before training): ≥ 2,000 chart water+ice pixels in the scene.

Scenes processed: 774 / 774; usable: 747 ({'test': 157, 'train': 484, 'validation': 106}).

## Labelled pixels per split (400 m pixels)

| split      |       n_water |         n_ice |   n_uncertain |   water_fraction_of_labelled |
|:-----------|--------------:|--------------:|--------------:|-----------------------------:|
| test       |  56336250.000 |  57516509.000 |  12656393.000 |                        0.495 |
| train      | 150483015.000 | 199009681.000 |  47199283.000 |                        0.431 |
| validation |  28799442.000 |  47654692.000 |  10203694.000 |                        0.377 |

## Validation checks

* Spatial alignment: chart and scene share the same transform (rasterised on the scene grid); visual check of coastal polynyas.
* Date alignment: chart valid date 0–3 days after acquisition (recorded per scene).
* Duplicates: one label file per scene id; a scene belongs to exactly one chart and split (tested).
* Mean chart coverage of valid SAR pixels: 0.963.
* No human or expert review of individual pixels was done (ANNOTATION_GUIDELINES.md).

**These labels are expert chart analyses at chart scale, independent of the model but not pixel-perfect truth.**