# AETHENTRA design system

Source of truth: `src/app/globals.css` (tokens) and `src/components/ui/*` (primitives).

## Colour tokens (v2, 2026-11-20)
| Token | Value | Use |
|---|---|---|
| `--polar-black` | #05080D Polar Black | Page background |
| `--midnight` / `--navy` / `--navy-2` | #081321 Midnight Navy / #0B1F33 Deep Ocean / #12304D | Panels, surfaces, selected rows |
| `--glacial` | #EAF5FC Glacial White | Primary text |
| `--ice` / `--ice-dim` | #8DDCF4 Ice Blue / #7FA6C4 | Serif accents, reanalysis badge |
| `--cyan` | #48C8E8 Cyan Accent | The only interactive accent: links, focus, active state, best value |
| `--silver` / `--muted` | #8B9BAA Muted Steel / #6F8094 | Body text / metadata |
| `--warn` | #F4A261 restrained alert orange | Model-prediction labels and frames, second series |
| `--alert` | #E76F6A restrained warning red | Anomalies, warm anomalies, errors |
| `--ok` | #7ED3B2 | Observation badge |
| `--line` / `--line-strong` | rgba(141,220,244,.11 / .22) | Hairline borders |

Module accents: ML-01 #48C8E8, ML-02 #F4A261, ML-03 #C9E6F5, ML-04 #E76F6A.

### Surfaces and effects (restrained by rule)
| Class | Use |
|---|---|
| `.surface` | Gradient Deep Ocean → Midnight panel, 14 px radius — chart and comparison containers |
| `.glass` | 72 % Polar Black + 14 px blur — only for UI floating over the globe (explorer panels, hero fact cards) |
| `.atmo` | Two faint radial glows behind section intros |
| `.spotlight` (via `<Spotlight>`) | Pointer-following glow + border light on cards (modules, regions, globe layers) |
| `.earth-fallback` | CSS sphere shown while Cesium initialises |
| `.scroll-cue`, `.page-enter`, `.range`, `.kbd` | Scroll indicator, route enter fade, range sliders, key hints |

## Data-type language (mandatory on every value)
`DataBadge` maps `data_type` → label and colour: Observation (green), Reanalysis (ice), Model prediction (amber; maps also get a dashed amber frame and a "MODEL PREDICTION" stamp), Statistical anomaly (orange-red), Evaluation (silver), Demo data (orange-red, filled). No demo data is used anywhere in the current build.

## Typography
| Class | Font | Size |
|---|---|---|
| `.t-display` | Space Grotesk 500 | clamp(3.2rem, 9.5vw, 9.5rem), −0.035em. Hero headline: clamp(2.9rem, 6vw, 6.4rem) |
| `.t-h1` / `.t-h2` / `.t-h3` | Space Grotesk 500 | clamp 2.4→5 / 1.8→3 / 1.2→1.5 rem |
| `.t-serif` | Instrument Serif italic | Accent words inside headings |
| `.t-lead` / `.t-body` | Inter | 1.05→1.25 rem / 0.975 rem, line-height 1.6 |
| `.t-meta` | JetBrains Mono | 0.72 rem, uppercase, 0.12em tracking |
| `.t-num` | Space Grotesk, tabular numerals | Statistics |

## Spacing & layout
- Container `--container` 1240 px, side gutter clamp(16px, 4vw, 40px) (`.container-x`).
- Section rhythm: `py-32 md:py-44` on the landing page, `py-20 md:py-28` on content pages, `space-y-24` between ML sections.
- Radius `--radius` 6 px. Pills only for buttons and filter chips.
- Grids are separated by 1 px hairlines (`gap-px` on a `bg-line` parent) instead of card shadows.

## Motion tokens
`--ease-out` cubic-bezier(.16,1,.3,1). Reveals take 1.0–1.15 s with "expo.out" / "power3.out", stagger 0.08–0.12 s. Reduced motion disables all of it (see the animation plan).

## Breakpoints
Tailwind defaults: `md` 768, `lg` 1024, `xl` 1280. Desktop is the presentation target. Explorer side panels collapse below `lg`.

## Primitives (`components/ui`)
`SplitReveal`, `Reveal`, `CountUp`, `DataBadge`, `Eyebrow`, `Stat`, `Panel`, `KV`, `Legend`, `Loading`, `ErrorState`, `Empty`, `ButtonLink`. ML: `ModuleShell`, `MapViewer`, `MetricsTable`, `CompareSlider`. Charts: `TimeSeries` (Recharts).

## Interaction components (`components/ui/interactive.tsx`, no new dependencies)
- `Spotlight` — card wrapper; JS sets `--mx/--my`, CSS draws the glow.
- `Magnetic` — primary CTAs drift toward the pointer; off for touch and reduced motion.
- `Starfield` — one 2D canvas, ≤ 520 points, paused off-screen and in hidden tabs, static under reduced motion.
- Mega menu (Nav) — ML modules; hover, click or keyboard; Escape and outside click close it.
