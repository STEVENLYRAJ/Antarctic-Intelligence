# Frontend architecture

```
web/
├── next.config.ts            /backend/* → AETHENTRA_API_URL proxy; distDir override for side-by-side builds
├── scripts/copy-cesium.mjs   postinstall: copies Cesium Build (JS, Workers, Assets, Widgets) to public/cesium
├── scripts/shoot.mjs         dev-only visual check with puppeteer-core + installed Chrome
├── public/data/              pre-computed presentation products (see FRONTEND_AUDIT.md)
└── src/
    ├── app/                  routes (App Router, all statically prerendered)
    ├── components/
    │   ├── layout/           Nav, Footer, SmoothScroll (Lenis ↔ GSAP ticker)
    │   ├── ui/               design-system primitives
    │   ├── scrolly/          HeroDescent (pinned globe + scroll camera)
    │   ├── globe/            CesiumGlobe (engine), Explorer (UI)
    │   ├── home/             ModuleCards, ClimateTeaser, ArchitectureDiagram
    │   ├── dashboard/        ClimateExplorer, DatasetCatalogue
    │   ├── ml/               ModuleShell, MapViewer, MetricsTable, CompareSlider, Ml0xLive
    │   ├── research/         Insights
    │   └── charts/           TimeSeries
    ├── config/               site.ts (nav, models), datasets.ts (verified catalogue)
    ├── hooks/                useApi, useReducedMotion
    └── lib/                  api/ (client, types), cesium/ (loader, places), animations/ (gsap), utils
```

## Key decisions
| Decision | Why |
|---|---|
| **CesiumJS loaded from its prebuilt bundle** (`/cesium/Cesium.js`), typed via `import type` | Bundling Cesium 1.123 source with Next 15 fails (`@zip.js` export map). Runtime loading also keeps 5 MB out of every page bundle and compiles faster. |
| One `Viewer` per page (`CesiumGlobe`), dynamic import with `ssr:false` | Prevents duplicate WebGL contexts and hydration mismatch. Destroyed on unmount. |
| `requestRenderMode` + explicit `requestRender` | No continuous GPU load while idle. Tile-load events and the first 8 s request frames. |
| NASA GIBS Blue Marble over Natural Earth II | Real, public-domain imagery without a token. Natural Earth (bundled) is the offline fallback. GIBS needs a custom tiling scheme (288° level-0 tiles, 512 px), implemented in `gibsScheme`. |
| Data separate from the engine | `CesiumGlobe` only knows `{url, bounds, alpha}` overlays. `Explorer` builds the layer catalogue from API manifests and static products. |
| Server-side proxy instead of CORS | No backend change, no hard-coded URL in the browser, and the same code works in deployment. |
| GSAP ScrollTrigger as the only scroll engine | Lenis drives smooth scrolling through the GSAP ticker. Motion is installed but reserved for small transitions; nothing conflicts. |
| Static presentation JSON for long climate series | 47 years × 11 variables would be slow to compute per request. ≈ 0.5 MB static, cacheable. |

## Data flow
```
NetCDF / GeoTIFF archive ──► FastAPI (api/) ──► /backend proxy ──► useApi() ──► components
        │                                                     
        └─► scripts/web/*.py ──► public/data/*.json|png ──► staticGet()/useApi(path, true)
```

## Failure behaviour
- API offline: every API-driven block renders `ErrorState` with the failing path. Static pages still work.
- WebGL unavailable: `CesiumGlobe` renders a text fallback that points to the 2D maps on the ML pages.
- GIBS unreachable: Natural Earth II stays visible underneath.
- A layer image fails: the explorer keeps the remaining layers. The 2D viewer shows "could not be rendered".
