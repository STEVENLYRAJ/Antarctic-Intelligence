# Animation plan

Engine: **GSAP 3.13 + ScrollTrigger** (primary), **Lenis 1.1** (smooth scroll, driven by the GSAP ticker), **Motion** installed for future micro-transitions (currently unused). Plain CSS handles hovers.

| Where | Technique | Implementation |
|---|---|---|
| Landing hero | Line-masked headline reveal on mount; giant outlined wordmark drifts down and fades; starfield parallax; live camera telemetry (lat / lon / altitude) | `SplitReveal trigger="mount"`, GSAP scrub on `.hero-wordmark` / `.hero-stars`, direct DOM text update (no re-render) |
| Globe loading | CSS sphere with breathing glow until Cesium is ready, then cross-fade | `.earth-fallback` |
| Landing hero → Antarctica | **Pinned globe, scroll-scrubbed camera** (lat −12° → −90°, 19,500 km → 10,200 km, eased), hero copy fades out, 4 fact cards cross-fade, graticule + Antarctic Circle appear at 45 % | `HeroDescent`, a 520 vh section with a sticky viewport and `ScrollTrigger.create({scrub:0.6})` |
| Section headings | Line-mask reveal when 85 % in view, `once` | `SplitReveal` |
| Card grids | Staggered fade-rise | `Reveal` + `[data-reveal]` |
| Architecture diagram | Timeline: columns rise, connectors draw (scaleX), items stagger | `ArchitectureDiagram` |
| Counters | Count-up on view | `CountUp` |
| Module cards | Accent line draws on hover, arrow nudges | CSS transitions |
| Navigation | Transparent → solid on scroll; active underline | `Nav` |
| Explorer | Arrival: global view → fly to Antarctica (or `?region=`). Region fly-to by box or point (quintic in-out). Timeline playback with frame preloading and flicker-free layer swap (new image added before the old one is removed) | Cesium `flyTo`, `flyToRect`, `CesiumGlobe` overlay effect |
| Chapter rail | Active chapter line grows, label fades in | `ChapterRail` (scroll position, no observers needed) |
| Cards | Pointer spotlight + border light; magnetic primary CTAs | `Spotlight`, `Magnetic` |
| Routes | 0.7 s fade-rise on navigation | `app/template.tsx` + `.page-enter` |
| Nav | Hides on fast downward scroll on long pages, reappears on any upward scroll (never on explorer or module pages); ML mega menu | `Nav` |

## Rules applied
- No scroll hijacking: native scrolling everywhere. The pinned hero uses `position: sticky`, not wheel capture.
- Lenis is **disabled on `/explore`**, where the globe owns the wheel. Scrollable panels use `data-lenis-prevent`.
- `prefers-reduced-motion`: Lenis is off, ScrollTrigger reveals are skipped (content is visible immediately), the hero camera jumps without scrub, and CSS animations are capped at 0.01 ms.
- All timelines are created inside `gsap.context()` and reverted on unmount. Cesium listeners are removed by `viewer.destroy()`.
- Data pages (ML, intelligence, data, research) use only one-shot reveals, nothing continuous.
- Mobile: same sequence with lighter layout. A darkening overlay keeps hero text legible over the globe.
