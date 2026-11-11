# Model Card — AETHENTRA ML-03 Antarctic SAR sea-ice segmentation

| item | value |
|---|---|
| Version | `aethentra-sar-seaice-20261109-v1` |
| Model | unet_bce_dice (unet) refitted on train+validation |
| Input | one Sentinel-1 EW GRDM HH scene: σ⁰ (dB, noise-corrected), incidence angle; 400 m EPSG:3031 |
| Output | per-pixel ice probability; classes water / ice / uncertain (0.35–0.65) / invalid; weekly 2 km composites |
| Labels | USNIC Antarctic ice charts 2018–2026 (expert, chart-scale), boundary buffer as uncertain |
| Test (agreement with charts) | mIoU 0.867, F1 ice 0.926, boundary F1 0.022, ice-area bias -8.6 % (157 scenes, 2025–2026) |
| Intended use | research monitoring of Antarctic ice/water extent from SAR; AETHENTRA visualisation |
| Not intended for | navigation, operational ice services, safety decisions, ice-type or concentration retrieval |

## Limitations

* Labels are chart-scale and 0–3 days apart from the image; scores measure agreement with charts, not pixel truth.
* HH only; 400 m (overview) resolution — floes, leads and small polynyas below ~1 km are not resolved.
* Known SAR ambiguities: wind-roughened water vs ice, smooth new ice vs calm water, summer melt (see the error report).
* Probabilities are not calibrated confidences unless the reliability figure shows otherwise; the uncertain band is a convention, not a validated uncertainty.
* No expert review; not a production system.