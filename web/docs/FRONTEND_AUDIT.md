# Frontend audit (Phase A) — 2026-11-20

## What existed
| Item | Finding | Decision |
|---|---|---|
| `frontend/` (index.html, app.js, anomaly.js, style.css; 392 lines) | Vanilla JS viewer served by FastAPI at `/viewer/`. It has four product tabs with polar PNG layers, metrics and limitations. | **Kept unchanged** as a lightweight fallback viewer. Not extended. |
| Framework / build | None (static files) | **Replaced** by a new Next.js app in `web/` |
| Map implementation | `<img>` of polar-stereographic PNG rendered by `/layers/{product}/{id}/{layer}.png` | **Reused** for 2D maps on the ML pages. The 3D globe needed a new reprojected endpoint (below). |
| Animations | None | **Created** (GSAP + ScrollTrigger + Lenis) |
| Backend | FastAPI `api.main:app`, 45 routes: ML-01 `/forecast/*`, ML-02 `/temperature/*`, ML-03 `/seaice-detection/*`, ML-04 `/api/ml04/*`, layers `/layers/*` | **Reused** through a typed client. One endpoint was added (see below). |
| CORS | None configured | Not needed: Next.js proxies `/backend/*` to the API server-side |
| Environment variables | None for the frontend | Created `web/.env.example` |
| Supabase | No Supabase configuration in the repository | Not integrated. The API is the single data source. |
| Deployment | Local only (uvicorn on 127.0.0.1:8000) | Local dev / `next start`. No deployment target defined. |
| `EXTERNAL APIs/` | Two CDS request scripts, no credentials | Not used by the frontend |

## Backend change made for the frontend
`GET /globe/{product}/{forecast_id}/{layer}.png` (`api/viewer.py`). It reprojects any existing layer GeoTIFF (EPSG:3412 / 3031) to an EPSG:4326 PNG covering lon −180…180, lat −90…−40 at 0.1°, with transparent no-data, so CesiumJS can drape it. Layer manifests now include `globe_png_url` and `globe_bounds`. No existing route changed behaviour.

## New presentation products (pre-computed, served as static files)
| Script | Output | Content |
|---|---|---|
| `scripts/web/build_climate_series.py` | `web/public/data/climate_series.json` (≈ 0.5 MB) | Monthly area-weighted series from ERA5, MERRA-2, OSI SAF CDR (C1) and GLORYS12 (C2), with 1991–2020 anomalies and NSIDC sectors |
| same | `web/public/data/globe/*.png` + `index.json` | ERA5 t2m / MSL / SST anomaly images for the latest month (Oct 2026) |
| `scripts/web/build_sar_examples.py` | `web/public/data/sar/*` | Four real Sentinel-1 σ⁰ / ML-03 class / probability image triples on the identical grid |

The browser never touches the ≈ 105 GB archive. It receives ≈ 2 MB of presentation products plus API responses.

## Data-quality issue found and fixed during the audit
OSI SAF ICDR files contain fully missing days. The first build counted them as zero ice and produced a false −4 million km² anomaly in September 2024. Days with missing data beyond the land mask are now excluded (`osisaf_daily_extent`).
