# Design reference analysis

Studied on 2026-11-20 by fetching each site. Where a site returned little readable content, this is stated rather than guessed.

| # | Reference | What was readable |
|---|---|---|
| 1 | animmasterlib.dev | Catalogue text only (≈ 300 paid components in 14 categories) |
| 2 | ui.aceternity.com (+ /labs) | Full component index |
| 3 | skiper-ui.com | Component list and pricing |
| 4 | lusion.co | Thin extract (headline, "scroll to explore", reel controls) |
| 5 | peachweb.io | JavaScript loading shell only |
| 6 | reactbits.dev | Category names only |
| 7 | uiverse.io/elements | **Not readable: HTTP 403 to automated access** |
| 8 | awwwards.com — PSP Production | Jury scores, tags, palette |

## 1. Animmaster Lib
1. **Distinctive:** a large catalogue of "pro-level" animated sections, grouped by category (scroll, WebGL shaders, page transitions, text, physics).
2. **Useful patterns:** scroll-linked reveals, text animation and hero transitions as categories.
3. **Components for AETHENTRA:** none adopted. The library is paid and names no individual components; its provenance note ("rebuilt from top-tier websites") argues against copying.
4. **Adaptation:** use only the category list as a checklist of motion types.
5. **Avoid:** physics effects, mouse-follow effects and full page transitions near the map. They compete with globe input.

## 2. Aceternity UI
1. **Distinctive:** dark marketing heroes, shader backgrounds and a 3D globe preview. Built on Motion + Tailwind.
2. **Useful patterns:** "Sticky Scroll Reveal", "Text Generate Effect", "Timeline", "Compare", "Spotlight".
3. **Components for AETHENTRA:** the *pattern* of Sticky Scroll Reveal (a pinned visual with text that changes) became the landing-page descent. The *pattern* of Compare became the ML-03 SAR slider. Both are re-implemented in our own code with GSAP, and no Aceternity code is copied.
4. **Adaptation:** a pinned CesiumJS globe instead of a pinned image, with sourced facts instead of marketing copy.
5. **Avoid:** Sparkles, Vortex, Meteors, Shooting Stars, Lamp, and scroll-jacking blocks (Macbook Scroll, Hero Parallax). They are decorative or block scrolling.

## 3. Skiper UI
1. **Distinctive:** an oversized lowercase display headline, minimal chrome, one-file shadcn components.
2. **Useful patterns:** "Dynamic island" status element, image reveal, tooltip.
3. **Components for AETHENTRA:** the status-bar idea informed the explorer's bottom coordinate bar. No code was used.
4. **Adaptation:** a monospaced, information-dense status bar (cursor position, camera, basemap) rather than a playful island.
5. **Avoid:** cursor-trail and drag-scroll components. They conflict with map pan.

## 4. Lusion
1. **Distinctive (from the readable extract):** 3D storytelling with a "continue to scroll" hero. Details of its techniques could not be confirmed from the fetch.
2. **Useful patterns:** a scroll-driven camera as the narrative device.
3. **Components for AETHENTRA:** the scroll-driven camera descent from Earth to the South Pole.
4. **Adaptation:** real NASA imagery and a real geodetic globe, not an art scene.
5. **Avoid:** full-screen video reels and heavy always-on 3D. Our globe renders on demand (`requestRenderMode`).

## 5. PeachWeb
1. **Distinctive:** a no-code WebGL scene builder. The fetch returned only its loading screen.
2. **Useful patterns:** pacing of scroll-triggered 3D scenes, as described in its marketing text.
3. **Components:** none.
4. **Adaptation:** one 3D scene per page, never several.
5. **Avoid:** long blocking preloaders. AETHENTRA shows content immediately and lets the globe stream in.

## 6. React Bits
1. **Readable:** category names only (text animations, backgrounds, micro-interactions).
2. **Useful patterns:** split-text reveals.
3. **Components:** none installed. A line-mask reveal (`SplitReveal`) was written in-house with GSAP.
4. **Adaptation:** line masks only, no per-character jitter on scientific text.
5. **Avoid:** animated shader backgrounds behind charts or the map (GPU cost, legibility).

## 7. Uiverse
Could not be studied: the site refuses automated access (HTTP 403). The micro-interactions used (button arrow nudge, focus rings, hover underline on navigation) were designed directly.

## 8. PSP Production (Awwwards)
1. **Distinctive:** a two-colour palette (#000 / #FF0063), GSAP, parallax and a preloader.
2. **Useful patterns:** a restrained palette with one accent; high Animations/Transitions score (8.6).
3. **Components:** none. The *one-accent* rule informed AETHENTRA's palette (cyan for interaction, orange-red only for anomalies and alerts).
4. **Adaptation:** colour carries meaning (data type, anomaly sign), not decoration.
5. **Avoid:** the jury rated **usability lowest (7.06)**. This supports keeping motion secondary on data pages: the explorer, dashboards and ML pages use almost no motion.

## Resulting AETHENTRA language
- Editorial typography (Space Grotesk display + Instrument Serif italic accents), mono metadata.
- Polar-black canvas, glacial text, cyan as the single interactive accent, orange-red reserved for anomalies.
- Motion: cinematic on the landing page only; calm and functional everywhere else.
- Every data element carries a data-type badge (observation, reanalysis, model prediction, statistical anomaly, evaluation, demo).
