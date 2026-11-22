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
```bash
python scripts/web/build_climate_series.py   # climate_series.json + ERA5 anomaly globe images (~15 min)
python scripts/web/build_sar_examples.py     # SAR / ML-03 comparison images
```

## Build & test report (2026-11-20)
| Check | Result |
|---|---|
| `tsc --noEmit` | Pass, 0 errors |
| `next build` | Pass. 15 routes prerendered static. First-load JS 103–276 kB. Cesium (5 MB) loads at runtime only on globe pages. |
| ESLint (during build) | 0 errors. One `exhaustive-deps` warning fixed afterwards. |
| Headless Chrome (puppeteer-core, SwiftShader WebGL), desktop 1600×900 and 1440 wide | All 12 pages load with **0 console errors and 0 failed requests**. Globe renders Blue Marble + ML-01 overlay. Scroll descent verified at two depths. |
| Mobile 390×844 | Home and explorer render. Hero overlay and collapsed layer panel fixed after the first check. |
| API integration | All endpoints in `docs/FRONTEND_API_INTEGRATION.md` returned data in the rendered pages |

Not yet tested: Safari / Firefox, real touch devices, Lighthouse scores, keyboard-only walkthrough of the explorer.

## Known limitations
- **Terrain:** without an ion token the globe is a smooth ellipsoid (no relief). Imagery is still real.
- **Overlays:** globe overlays are single 0.1° images (3600 × 500), not tiled, so they soften when zoomed in close. The 2D maps on the ML pages are native resolution.
- **ML-02 / ML-04 currency:** driven by NCEP/NCAR R1, which ends in March 2026. ML-02's latest forecast is for 2026-01-01…07, and ML-04 multivariate output stops at 2026-02.
- **ERA5 globe anomalies and Climate Explorer:** cover the latest *monthly* ERA5 (Oct 2026). Daily ERA5 is still downloading and is not yet used.
- **Copernicus Marine:** C3–C7 are catalogued but not yet visualised (only C1 extent and C2 thickness are in the explorer).
- **Search:** a curated Antarctic gazetteer plus coordinate entry. There is no global geocoder (it would need an external service).
- **Roadmap:** Phases 2–4 are shown as planned only. No content was invented for them.

## Documentation
`docs/` — design reference analysis, audit, design system, architecture, page structure, animation plan, API integration.
