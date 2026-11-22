# AETHENTRA web — Phase 1: Antarctic Scientific Intelligence

Next.js 15 · TypeScript · Tailwind CSS 4 · GSAP / ScrollTrigger · Lenis · CesiumJS 1.123 · Recharts.

## Setup
```bash
# 1. backend (repository root)
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000

# 2. frontend
cd web
npm install            # also copies Cesium assets to public/cesium (postinstall)
cp .env.example .env.local   # optional
npm run dev            # http://localhost:3000
```
Production: `npm run build && npm start`.

## Environment variables
| Variable | Where | Default | Purpose |
|---|---|---|---|
| `AETHENTRA_API_URL` | server only | `http://127.0.0.1:8000` | Target of the `/backend/*` proxy |
| `NEXT_PUBLIC_CESIUM_ION_TOKEN` | browser | empty | Optional Cesium World Terrain. Public token only, never a secret. |
| `NEXT_DIST_DIR` | build | `.next` | Build into another folder (e.g. while `dev` is running) |

## Regenerating presentation data
Run these from the repository root. They read only files already in the archive, except the GIBS fetch.
```bash
python scripts/web/build_climate_series.py   # climate_series.json + ERA5 anomaly images (~15 min)
python scripts/web/build_globe_products.py   # 24 time-enabled globe layers, drift + wind vectors, daily records,
                                             # ocean/drift series (~16 min; pass e.g. "c5 c7" to rebuild parts)
python scripts/web/build_sar_examples.py     # SAR / ML-03 comparison images
python scripts/web/fetch_gibs_imagery.py     # cache NASA GIBS polar imagery (network, public domain)
```

## Build & test report (2026-11-20, v2 upgrade)
| Check | Result |
|---|---|
| `tsc --noEmit` | Pass, 0 errors |
| `next lint` | 0 warnings, 0 errors |
| `next build` | Pass. 15 routes prerendered static. First-load JS 103–281 kB. Cesium loads at runtime only on globe pages. |
| Headless Chrome (puppeteer-core, SwiftShader WebGL), 1600×900 and 1440 wide | Home, explorer, Intelligence, ML-03 and Research checked: 0 console errors, 0 failed requests |
| Interaction test (`scripts/interact.mjs`) | Timeline play, pause (Space) and step (→); Ross Sea fly-to opens its region panel; search "Thwaites" flies there; layer toggle adds the layer to the legend list; mega menu opens and lists 5 links; Escape closes it. 0 errors. |
| Mobile 390×844 | Home hero and explorer (timeline, destinations) render. The layer button and panel were moved below the search bar. |
| Data files | `climate_series.json`, `daily_series.json`, `globe/catalog.json` parse as strict JSON (the builder now refuses NaN) |

Not yet tested: Safari / Firefox, real touch devices, Lighthouse scores, a full keyboard-only walkthrough.

## Known limitations
- **Terrain:** without an ion token the globe is a smooth ellipsoid (no relief). Imagery is still real.
- **Overlays:** globe layers are single equirectangular images per frame (0.1–0.3°), not tiled, so they soften when zoomed in close. The 2D maps on the ML pages are native resolution.
- **ML-02 / ML-04 currency:** driven by NCEP/NCAR R1, which ends in March 2026. ML-02's latest forecast is for 2026-01-01…07, and ML-04 multivariate output stops at 2026-02. No model was retrained on ERA5.
- **ERA5 daily:** on disk from 2014 (t2m, msl) to 31 Oct 2026, so the daily-temperature envelope uses a short 2014–2025 baseline. It is labelled as such.
- **Copernicus Marine record ends:** OSI SAF 2025-09; MULTIOBS 2025-05; ensemble spread 2025-12; GLORYS 2026-09; drift 2026-10; thickness 2026-10; DMI ASIP has 96 usable dates. Drift is absent in summer months and during the AMSR-E/AMSR2 gap (Oct 2011 – Jul 2012).
- **Region panel:** shows only the regional breakdowns each API provides. Some destinations (e.g. the Peninsula) have no ML-01 sector.
- **Search:** curated destinations, a 22-place gazetteer and coordinate entry. There is no global geocoder (it would need an external service).
- **Roadmap:** Phases 2–4 are shown as planned only. No content was invented for them.

## Documentation
`docs/` — design reference analysis, audit, design system, architecture, page structure, animation plan, API integration.
