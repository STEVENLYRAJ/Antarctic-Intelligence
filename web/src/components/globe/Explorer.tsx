"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  Compass,
  Expand,
  Globe2,
  Grid3x3,
  Info,
  Layers,
  MapPin,
  Minus,
  Navigation,
  Pause,
  Play,
  Plus,
  Search,
  Shrink,
  SkipBack,
  SkipForward,
  Snowflake,
  X,
} from "lucide-react";
import type { CameraState, GlobeHandle, Overlay, VectorSet } from "./CesiumGlobe";
import { RegionCard } from "./RegionCard";
import { apiGet, apiUrl, staticGet } from "@/lib/api/client";
import type { CatalogFrame, GlobeCatalog, GlobeImage, Layer, LayerManifest } from "@/lib/api/types";
import { PLACES } from "@/lib/cesium/places";
import { REGIONS, regionById, type Region } from "@/config/regions";
import { DataBadge, Legend } from "@/components/ui/primitives";
import { cn, fmt } from "@/lib/utils";

const CesiumGlobe = dynamic(() => import("./CesiumGlobe").then((m) => m.CesiumGlobe), { ssr: false });

interface LayerEntry {
  key: string;
  group: string;
  title: string;
  dataType: string;
  units: string;
  period: string;
  bounds: Overlay["bounds"];
  colors: string[];
  vmin: number | null;
  vmax: number | null;
  source: string;
  method?: string;
  /** single image, or a time series of frames */
  frames: CatalogFrame[];
  defaultFrame: number;
}

const PRODUCTS: { id: LayerManifest["product"]; group: string; method: string }[] = [
  { id: "sic", group: "ML-01 · Sea-ice forecast", method: "U-Net / gradient-boosting weekly-mean SIC forecast on the NSIDC 25 km grid; see the ML-01 page for evaluation." },
  { id: "t2m", group: "ML-02 · Temperature forecast", method: "Weekly-mean 2 m temperature and anomaly forecast from NCEP/NCAR R1 inputs; see the ML-02 page." },
  { id: "sar", group: "ML-03 · SAR detection", method: "Sentinel-1 SAR ice / open-water segmentation, weekly composite; see the ML-03 page." },
  { id: "anom", group: "ML-04 · Anomaly detection", method: "Unsupervised multivariate monthly anomaly detection; statistical unusualness only. See the ML-04 page." },
];
const GROUP_ORDER = [
  ...PRODUCTS.map((p) => p.group),
  "Sea ice · observations",
  "Sea ice · reanalysis",
  "Ocean · observations",
  "Atmosphere · reanalysis",
  "ERA5 · Reanalysis anomalies",
];

const yesterday = () => new Date(Date.now() - 2 * 86400_000).toISOString().slice(0, 10);
const periodText = (p: Layer["period"]) => (Array.isArray(p) ? `${p[0]} → ${p[1]}` : p == null ? "—" : String(p));
const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

function flyRegion(g: GlobeHandle | null, r: Region) {
  if (!g) return;
  if ("rect" in r.view) g.flyToRect(...r.view.rect);
  else g.flyTo(r.view.lat, r.view.lon, r.view.height);
}

export function Explorer() {
  const globe = useRef<GlobeHandle>(null);
  const shell = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [ready, setReady] = useState(false);
  const [cam, setCam] = useState<CameraState | null>(null);
  const [ptr, setPtr] = useState<{ lat: number; lon: number } | null>(null);
  const [catalog, setCatalog] = useState<LayerEntry[]>([]);
  const [loadErr, setLoadErr] = useState<string[]>([]);
  const [active, setActive] = useState<string[]>([]);
  const [frame, setFrame] = useState<Record<string, number>>({});
  const [focus, setFocus] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [alpha, setAlpha] = useState<Record<string, number>>({});
  const [info, setInfo] = useState<string | null>(null);
  const [arrows, setArrows] = useState(true);
  const [grid, setGrid] = useState(true);
  const [tcDate, setTcDate] = useState<string | null>(null);
  const [panel, setPanel] = useState(true);
  const [region, setRegion] = useState<Region | null>(null);
  const [q, setQ] = useState("");
  const [full, setFull] = useState(false);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  /* ---------- layer catalogue: model layers (API) + pre-rendered observation / reanalysis layers (static) ---------- */
  useEffect(() => {
    let alive = true;
    (async () => {
      const entries: LayerEntry[] = [];
      const errs: string[] = [];
      await Promise.all(
        PRODUCTS.map(async (p) => {
          try {
            const m = await apiGet<LayerManifest>(`/layers/${p.id}/latest`);
            for (const l of m.layers) {
              if (!l.globe_png_url || !l.globe_bounds) continue;
              entries.push({
                key: `${p.id}:${l.id}`,
                group: p.group,
                title: cap(l.title),
                dataType: l.data_type,
                units: l.units,
                period: periodText(l.period),
                bounds: l.globe_bounds,
                colors: l.style.colors,
                vmin: l.style.vmin,
                vmax: l.style.vmax,
                source: `${m.forecast_id}${m.model_version ? ` · ${m.model_version}` : ""}`,
                method: p.method,
                frames: [{ t: periodText(l.period), url: apiUrl(l.globe_png_url) }],
                defaultFrame: 0,
              });
            }
          } catch (e) {
            errs.push(`${p.group}: ${(e as Error).message}`);
          }
        }),
      );
      let haveEra5Series = false;
      try {
        const c = await staticGet<GlobeCatalog>("/data/globe/catalog.json");
        for (const l of c.layers) {
          if (!l.frames.length) continue;
          if (l.id.startsWith("era5_") && l.id.endsWith("_anom_series")) haveEra5Series = true;
          const di = l.default ? l.frames.findIndex((f) => f.t === l.default) : -1;
          entries.push({
            key: `cat:${l.id}`,
            group: l.group,
            title: l.title,
            dataType: l.data_type,
            units: l.units,
            period: l.coverage,
            bounds: l.bounds,
            colors: l.colors,
            vmin: l.vmin,
            vmax: l.vmax,
            source: l.source,
            method: l.method,
            frames: l.frames,
            defaultFrame: di >= 0 ? di : l.frames.length - 1,
          });
        }
      } catch (e) {
        errs.push(`Observation layers: ${(e as Error).message}`);
      }
      if (!haveEra5Series) {
        try {
          const g = await staticGet<GlobeImage[]>("/data/globe/index.json");
          for (const l of g)
            entries.push({
              key: `era5:${l.id}`,
              group: "ERA5 · Reanalysis anomalies",
              title: l.title,
              dataType: l.data_type,
              units: l.units,
              period: l.month,
              bounds: l.bounds,
              colors: l.colors,
              vmin: l.vmin,
              vmax: l.vmax,
              source: l.source,
              frames: [{ t: l.month, url: l.url }],
              defaultFrame: 0,
            });
        } catch {
          /* optional */
        }
      }
      if (!alive) return;
      entries.sort((a, b) => GROUP_ORDER.indexOf(a.group) - GROUP_ORDER.indexOf(b.group));
      setCatalog(entries);
      setLoadErr(errs);
      setFrame(Object.fromEntries(entries.map((e) => [e.key, e.defaultFrame])));
      const params = new URLSearchParams(window.location.search);
      const want = params.get("layer");
      const first = entries.find((e) => e.key === want || e.key === `cat:${want}`) ?? entries.find((e) => e.key === "cat:osisaf_sic") ?? entries.find((e) => e.key === "sic:forecast_7day_mean") ?? entries[0];
      if (first) {
        setActive([first.key]);
        setFocus(first.frames.length > 1 ? first.key : null);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  /* ---------- cinematic arrival: global view, then fly to the requested region (or Antarctica) ---------- */
  useEffect(() => {
    if (!ready) return;
    const id = new URLSearchParams(window.location.search).get("region");
    const r = regionById(id) ?? regionById("antarctica")!;
    const t = window.setTimeout(() => {
      flyRegion(globe.current, r);
      if (id && regionById(id)) setRegion(r);
    }, 700);
    return () => window.clearTimeout(t);
  }, [ready]);

  const byKey = useMemo(() => new Map(catalog.map((c) => [c.key, c])), [catalog]);
  const frameOf = useCallback((c: LayerEntry) => c.frames[Math.min(frame[c.key] ?? c.defaultFrame, c.frames.length - 1)], [frame]);

  const overlays: Overlay[] = useMemo(
    () =>
      active
        .map((k) => byKey.get(k))
        .filter((c): c is LayerEntry => !!c)
        .map((c) => ({ id: c.key, url: frameOf(c).url, bounds: c.bounds, alpha: alpha[c.key] ?? 0.85 })),
    [active, byKey, alpha, frameOf],
  );
  const vectors: VectorSet[] = useMemo(
    () =>
      arrows
        ? active
            .map((k) => byKey.get(k))
            .filter((c): c is LayerEntry => !!c && !!frameOf(c).vectors)
            .map((c) => ({ id: c.key, url: frameOf(c).vectors!, color: "#eaf5fc" }))
        : [],
    [active, byKey, frameOf, arrows],
  );

  const toggle = (k: string) => {
    const on = active.includes(k);
    setActive((a) => (on ? a.filter((x) => x !== k) : [...a, k]));
    const c = byKey.get(k);
    if (!on && c && c.frames.length > 1) setFocus(k);
    if (on && focus === k) {
      const next = active.filter((x) => x !== k).reverse().find((x) => (byKey.get(x)?.frames.length ?? 0) > 1);
      setFocus(next ?? null);
      setPlaying(false);
    }
  };

  /* ---------- timeline playback ---------- */
  const focusEntry = focus ? byKey.get(focus) : undefined;
  const fIdx = focusEntry ? Math.min(frame[focusEntry.key] ?? focusEntry.defaultFrame, focusEntry.frames.length - 1) : 0;
  const setF = useCallback((k: string, i: number) => setFrame((f) => ({ ...f, [k]: i })), []);
  useEffect(() => {
    if (!playing || !focusEntry) return;
    const n = focusEntry.frames.length;
    const t = window.setInterval(() => {
      setFrame((f) => {
        const i = ((f[focusEntry.key] ?? 0) + 1) % n;
        // preload the next two frames so playback does not stutter
        [1, 2].forEach((d) => {
          const img = new Image();
          img.src = focusEntry.frames[(i + d) % n].url;
        });
        return { ...f, [focusEntry.key]: i };
      });
    }, n > 200 ? 260 : 650);
    return () => window.clearInterval(t);
  }, [playing, focusEntry]);

  const goRegion = (r: Region) => {
    flyRegion(globe.current, r);
    setRegion(r.id === "global" ? null : r);
    const u = new URL(window.location.href);
    u.searchParams.set("region", r.id);
    window.history.replaceState(null, "", u);
  };

  const goSearch = (text: string) => {
    const m = text.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
    if (m) {
      const lat = Math.max(-90, Math.min(90, parseFloat(m[1])));
      const lon = ((parseFloat(m[2]) + 540) % 360) - 180;
      globe.current?.flyTo(lat, lon, 1_500_000);
      setQ("");
      return;
    }
    const r = REGIONS.find((x) => x.name.toLowerCase().includes(text.toLowerCase()));
    if (r) return (goRegion(r), setQ(""));
    const p = PLACES.find((x) => x.name.toLowerCase().includes(text.toLowerCase()));
    if (p) {
      globe.current?.flyTo(p.lat, p.lon, p.height);
      setQ("");
    }
  };
  const suggestions =
    q.length >= 2
      ? [
          ...REGIONS.filter((r) => r.name.toLowerCase().includes(q.toLowerCase())).map((r) => ({ name: r.name, kind: "destination", lat: r.centre[0], lon: r.centre[1], go: () => goRegion(r) })),
          ...PLACES.filter((p) => p.name.toLowerCase().includes(q.toLowerCase())).map((p) => ({ name: p.name, kind: p.kind, lat: p.lat, lon: p.lon, go: () => globe.current?.flyTo(p.lat, p.lon, p.height) })),
        ].slice(0, 8)
      : [];

  useEffect(() => {
    if (window.innerWidth < 1024) setPanel(false);
  }, []);
  useEffect(() => {
    const on = () => setFull(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", on);
    return () => document.removeEventListener("fullscreenchange", on);
  }, []);
  const toggleFull = useCallback(() => (document.fullscreenElement ? document.exitFullscreen() : shell.current?.requestFullscreen()), []);

  /* ---------- keyboard: / search · L layers · F full screen · space play · ←/→ step ---------- */
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "/") {
        e.preventDefault();
        searchRef.current?.focus();
      } else if (e.key === "l" || e.key === "L") setPanel((p) => !p);
      else if (e.key === "f" || e.key === "F") toggleFull();
      else if (focusEntry && e.key === " ") {
        e.preventDefault();
        setPlaying((p) => !p);
      } else if (focusEntry && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
        const n = focusEntry.frames.length;
        setF(focusEntry.key, (fIdx + (e.key === "ArrowRight" ? 1 : n - 1)) % n);
      }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [focusEntry, fIdx, setF, toggleFull]);

  const groups = useMemo(() => [...new Set(catalog.map((c) => c.group))], [catalog]);
  const activeEntries = active.map((k) => byKey.get(k)).filter((c): c is LayerEntry => !!c);
  const timeLayers = activeEntries.filter((c) => c.frames.length > 1);

  return (
    <div ref={shell} className="relative h-dvh w-full overflow-hidden bg-polar pt-16">
      <div className="absolute inset-0 top-16">
        <CesiumGlobe
          ref={globe}
          className="absolute inset-0"
          overlays={overlays}
          vectors={vectors}
          showGraticule={grid}
          trueColorDate={tcDate}
          initial={{ lat: -25, lon: 30, height: 26_000_000 }}
          onCamera={setCam}
          onPointer={setPtr}
          onReady={() => setReady(true)}
        />
      </div>

      {/* Search + destinations */}
      <div className="absolute left-1/2 top-20 z-20 w-[min(560px,calc(100%-32px))] -translate-x-1/2">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            goSearch(q);
          }}
          className="glass flex items-center gap-2 rounded-full px-4 py-2.5"
          role="search"
        >
          <Search size={15} className="text-muted" />
          <input
            ref={searchRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search Antarctic places, or enter lat, lon"
            aria-label="Search places or coordinates"
            className="w-full bg-transparent text-sm text-glacial placeholder:text-muted focus:outline-none"
          />
          {q ? (
            <button type="button" aria-label="Clear search" onClick={() => setQ("")} className="text-muted hover:text-glacial">
              <X size={14} />
            </button>
          ) : (
            <span className="kbd hidden sm:inline">/</span>
          )}
        </form>
        {suggestions.length > 0 && (
          <ul className="glass mt-2 overflow-hidden rounded-[var(--radius)]">
            {suggestions.map((p) => (
              <li key={p.name}>
                <button
                  onClick={() => {
                    p.go();
                    setQ("");
                  }}
                  className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm text-silver hover:bg-navy hover:text-glacial"
                >
                  {p.name}
                  <span className="font-mono text-[0.625rem] uppercase text-muted">
                    {p.kind} · {fmt(p.lat, 1)}°, {fmt(p.lon, 1)}°
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-2.5 flex gap-1.5 overflow-x-auto pb-1 [mask-image:linear-gradient(90deg,#000_88%,transparent)] [scrollbar-width:none]" role="toolbar" aria-label="Camera destinations">
          {REGIONS.map((r) => (
            <button
              key={r.id}
              onClick={() => goRegion(r)}
              aria-pressed={region?.id === r.id}
              className={cn(
                "shrink-0 rounded-full border px-3 py-1 text-[0.7188rem] backdrop-blur-md transition-colors",
                region?.id === r.id ? "border-cyan bg-cyan/15 text-glacial" : "border-line bg-polar/70 text-silver hover:border-line-strong hover:text-glacial",
              )}
            >
              {r.name}
            </button>
          ))}
        </div>
      </div>

      {/* Layer panel */}
      <aside
        className={cn(
          "glass absolute bottom-[7.5rem] left-4 top-[9.75rem] z-20 flex w-[21.875rem] lg:bottom-14 lg:top-20 lg:z-10 max-w-[calc(100%-32px)] flex-col overflow-hidden rounded-[var(--radius-lg)] transition-transform duration-500",
          panel ? "translate-x-0" : "-translate-x-[110%]",
        )}
        aria-label="Map layers"
        aria-hidden={!panel}
      >
        <header className="flex items-center justify-between border-b border-line px-4 py-3">
          <p className="flex items-center gap-2 font-display text-sm">
            <Layers size={15} className="text-cyan" /> Scientific layers
            <span className="font-mono text-[0.625rem] text-muted">{catalog.length}</span>
          </p>
          <button aria-label="Hide layer panel" onClick={() => setPanel(false)} className="text-muted hover:text-glacial">
            <X size={15} />
          </button>
        </header>
        <div className="flex-1 space-y-4 overflow-y-auto px-3 py-3" data-lenis-prevent>
          {catalog.length === 0 && !loadErr.length && <p className="px-1 font-mono text-[0.6875rem] uppercase tracking-[0.16em] text-muted">Loading layer catalogue…</p>}
          {groups.map((g) => (
            <section key={g}>
              <button
                onClick={() => setCollapsed((c) => ({ ...c, [g]: !c[g] }))}
                className="t-meta mb-1 flex w-full items-center justify-between px-1 py-1 hover:text-silver"
                aria-expanded={!collapsed[g]}
              >
                {g}
                <ChevronDown size={12} className={cn("transition-transform", collapsed[g] && "-rotate-90")} />
              </button>
              {!collapsed[g] && (
                <ul className="space-y-0.5">
                  {catalog
                    .filter((c) => c.group === g)
                    .map((c) => {
                      const on = active.includes(c.key);
                      return (
                        <li key={c.key}>
                          <label className={cn("flex cursor-pointer items-start gap-3 rounded-md px-2 py-2 text-[0.7813rem] leading-snug transition-colors", on ? "bg-navy-2/60 text-glacial" : "text-silver hover:bg-navy/60")}>
                            <input type="checkbox" checked={on} onChange={() => toggle(c.key)} className="mt-0.5 accent-[var(--cyan)]" />
                            <span className="flex-1">
                              {c.title}
                              <span className="mt-1 flex flex-wrap items-center gap-2">
                                <DataBadge type={c.dataType} />
                                <span className="font-mono text-[0.625rem] text-muted">
                                  {c.frames.length > 1 ? `${c.frames.length} frames · ${c.period}` : c.period}
                                </span>
                              </span>
                            </span>
                          </label>
                        </li>
                      );
                    })}
                </ul>
              )}
            </section>
          ))}
          <section>
            <p className="t-meta mb-1 px-1 py-1">Satellite imagery & reference</p>
            <label className="flex items-start gap-3 rounded-md px-2 py-2 text-[0.7813rem] text-silver hover:bg-navy/60">
              <input type="checkbox" checked={!!tcDate} onChange={(e) => setTcDate(e.target.checked ? yesterday() : null)} className="mt-0.5 accent-[var(--cyan)]" />
              <span className="flex-1">
                MODIS Terra true colour (NASA GIBS, daily)
                <span className="mt-1 flex items-center gap-2">
                  <DataBadge type="observation" />
                  {tcDate && (
                    <input
                      type="date"
                      value={tcDate}
                      max={yesterday()}
                      min="2000-03-01"
                      onChange={(e) => e.target.value && setTcDate(e.target.value)}
                      className="rounded border border-line bg-navy px-1.5 py-0.5 font-mono text-[0.625rem] text-glacial"
                      aria-label="Imagery date"
                    />
                  )}
                </span>
                <span className="mt-1 block text-[0.6875rem] text-muted">Optical: no data during polar night or under cloud.</span>
              </span>
            </label>
            <label className="flex items-center gap-3 rounded-md px-2 py-2 text-[0.7813rem] text-silver hover:bg-navy/60">
              <input type="checkbox" checked={grid} onChange={(e) => setGrid(e.target.checked)} className="accent-[var(--cyan)]" />
              Graticule & Antarctic Circle (66.56° S)
            </label>
          </section>
          {loadErr.length > 0 && (
            <div className="rounded border border-alert/30 bg-alert/5 p-3 text-[0.6875rem] text-silver">
              <p className="text-glacial">Some layers are unavailable</p>
              {loadErr.map((e) => (
                <p key={e} className="mt-1 font-mono text-muted">
                  {e}
                </p>
              ))}
            </div>
          )}
        </div>
        {activeEntries.length > 0 && (
          <footer className="max-h-[46%] space-y-4 overflow-y-auto border-t border-line px-4 py-4" data-lenis-prevent>
            {activeEntries.map((c) => (
              <div key={c.key}>
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-[0.75rem] text-glacial" title={c.title}>
                    {c.title}
                  </p>
                  <div className="flex shrink-0 items-center gap-2">
                    <button aria-label={`About ${c.title}`} aria-expanded={info === c.key} onClick={() => setInfo((i) => (i === c.key ? null : c.key))} className={cn("hover:text-glacial", info === c.key ? "text-cyan" : "text-muted")}>
                      <Info size={13} />
                    </button>
                    <input
                      type="range"
                      min={0.2}
                      max={1}
                      step={0.05}
                      value={alpha[c.key] ?? 0.85}
                      onChange={(e) => setAlpha((a) => ({ ...a, [c.key]: parseFloat(e.target.value) }))}
                      aria-label={`Opacity of ${c.title}`}
                      className="range w-16"
                    />
                  </div>
                </div>
                <Legend className="mt-2" colors={c.colors} vmin={c.vmin} vmax={c.vmax} units={c.units} />
                <p className="mt-1 flex justify-between gap-2 font-mono text-[0.5938rem] text-muted">
                  <span className="truncate" title={c.source}>
                    {c.source}
                  </span>
                  <span className="shrink-0 text-ice-dim">{frameOf(c).t}</span>
                </p>
                {info === c.key && (
                  <div className="mt-2 space-y-1.5 rounded-md border border-line bg-navy/50 p-2.5 text-[0.6875rem] leading-relaxed text-silver">
                    <p>
                      <span className="text-muted">Units · </span>
                      {c.units}
                    </p>
                    <p>
                      <span className="text-muted">Coverage · </span>
                      {c.period}
                    </p>
                    <p>
                      <span className="text-muted">Source · </span>
                      {c.source}
                    </p>
                    {c.method && (
                      <p>
                        <span className="text-muted">Method · </span>
                        {c.method}
                      </p>
                    )}
                    {c.frames.some((f) => f.vectors) && (
                      <label className="flex items-center gap-2 pt-1">
                        <input type="checkbox" checked={arrows} onChange={(e) => setArrows(e.target.checked)} className="accent-[var(--cyan)]" /> Show drift arrows
                      </label>
                    )}
                  </div>
                )}
              </div>
            ))}
          </footer>
        )}
      </aside>
      {!panel && (
        <button onClick={() => setPanel(true)} className="glass absolute left-4 top-[9.75rem] z-10 flex items-center gap-2 rounded-full px-4 py-2.5 text-[0.8125rem] hover:border-cyan lg:top-20">
          <Layers size={15} className="text-cyan" /> Layers ({active.length})
        </button>
      )}

      {/* Region intelligence */}
      {region && (
        <aside className="glass absolute right-4 top-[9.5rem] z-10 hidden max-h-[calc(100%-9.5rem-10.5rem)] min-h-[16.25rem] w-[20rem] overflow-hidden rounded-[var(--radius-lg)] md:block" aria-label={`${region.name} details`}>
          <RegionCard region={region} onClose={() => setRegion(null)} />
        </aside>
      )}

      {/* Timeline */}
      {focusEntry && (
        <div className={cn("absolute bottom-12 z-10 transition-[left] duration-500", panel ? "left-4 right-4 lg:left-[374px]" : "left-4 right-4")}>
          <div className="glass mx-auto flex max-w-[51.25rem] items-center gap-3 rounded-full px-3 py-2">
            <button onClick={() => setF(focusEntry.key, (fIdx + focusEntry.frames.length - 1) % focusEntry.frames.length)} aria-label="Previous frame" className="p-1 text-silver hover:text-glacial">
              <SkipBack size={14} />
            </button>
            <button
              onClick={() => setPlaying((p) => !p)}
              aria-label={playing ? "Pause" : "Play"}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-glacial text-polar transition-colors hover:bg-cyan"
            >
              {playing ? <Pause size={14} /> : <Play size={14} className="translate-x-px" />}
            </button>
            <button onClick={() => setF(focusEntry.key, (fIdx + 1) % focusEntry.frames.length)} aria-label="Next frame" className="p-1 text-silver hover:text-glacial">
              <SkipForward size={14} />
            </button>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-2">
                {timeLayers.length > 1 ? (
                  <select
                    value={focusEntry.key}
                    onChange={(e) => {
                      setFocus(e.target.value);
                      setPlaying(false);
                    }}
                    className="max-w-[60%] truncate bg-transparent text-[0.6875rem] text-silver focus:outline-none"
                    aria-label="Layer controlled by the timeline"
                  >
                    {timeLayers.map((t) => (
                      <option key={t.key} value={t.key} className="bg-navy">
                        {t.title}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="truncate text-[0.6875rem] text-silver">{focusEntry.title}</span>
                )}
                <span className="t-num shrink-0 text-[0.9375rem] text-glacial">{focusEntry.frames[fIdx].t}</span>
              </div>
              <input
                type="range"
                min={0}
                max={focusEntry.frames.length - 1}
                value={fIdx}
                onChange={(e) => {
                  setPlaying(false);
                  setF(focusEntry.key, parseInt(e.target.value, 10));
                }}
                aria-label={`Time: ${focusEntry.frames[fIdx].t}`}
                className="range mt-1.5 w-full"
              />
              <div className="mt-0.5 flex justify-between font-mono text-[0.5625rem] text-muted">
                <span>{focusEntry.frames[0].t}</span>
                <span>
                  {fIdx + 1} / {focusEntry.frames.length}
                </span>
                <span>{focusEntry.frames[focusEntry.frames.length - 1].t}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Navigation controls */}
      <div className="glass absolute bottom-[7.25rem] right-4 z-10 flex flex-col overflow-hidden rounded-[var(--radius)] md:flex-row">
        {[
          { l: "Fly to Antarctica", i: <Snowflake size={16} />, f: () => goRegion(regionById("antarctica")!) },
          { l: "Global view", i: <Globe2 size={16} />, f: () => goRegion(regionById("global")!) },
          { l: "Zoom in", i: <Plus size={16} />, f: () => globe.current?.zoom(1.6) },
          { l: "Zoom out", i: <Minus size={16} />, f: () => globe.current?.zoom(1 / 1.6) },
          { l: "Look straight down, north up", i: <Compass size={16} />, f: () => globe.current?.resetNorth() },
          { l: "Toggle graticule", i: <Grid3x3 size={16} />, f: () => setGrid((g) => !g) },
          { l: full ? "Exit full screen (F)" : "Full screen (F)", i: full ? <Shrink size={16} /> : <Expand size={16} />, f: toggleFull },
        ].map((b) => (
          <button key={b.l} onClick={b.f} title={b.l} aria-label={b.l} className="border-b border-line p-2.5 text-silver last:border-0 hover:bg-navy hover:text-cyan md:border-b-0 md:border-r">
            {b.i}
          </button>
        ))}
      </div>

      {/* Status bar */}
      <div className="absolute inset-x-0 bottom-0 z-10 flex h-10 items-center justify-between gap-4 overflow-x-auto border-t border-line bg-polar/90 px-4 font-mono text-[0.6563rem] text-muted backdrop-blur-md">
        <span className="flex shrink-0 items-center gap-2">
          <Navigation size={12} className="text-cyan" />
          {ptr ? `Cursor ${fmt(Math.abs(ptr.lat), 3)}° ${ptr.lat < 0 ? "S" : "N"}, ${fmt(Math.abs(ptr.lon), 3)}° ${ptr.lon < 0 ? "W" : "E"}` : "Cursor off globe"}
        </span>
        {region && (
          <span className="flex shrink-0 items-center gap-1.5 text-ice-dim">
            <MapPin size={11} /> {region.name}
          </span>
        )}
        {cam && (
          <span className="shrink-0">
            Camera {fmt(cam.lat, 2)}°, {fmt(cam.lon, 2)}° · alt {fmt(cam.height / 1000, 0)} km · heading {fmt(cam.heading, 0)}° · pitch {fmt(cam.pitch, 0)}°
          </span>
        )}
        <span className="hidden shrink-0 xl:inline">
          <span className="kbd">/</span> search · <span className="kbd">L</span> layers · <span className="kbd">Space</span> play · <span className="kbd">←→</span> step · <span className="kbd">F</span> full screen
        </span>
        <span className="hidden shrink-0 2xl:inline">Basemap: NASA Blue Marble (GIBS) · {process.env.NEXT_PUBLIC_CESIUM_ION_TOKEN ? "Cesium World Terrain" : "ellipsoid"}</span>
      </div>
    </div>
  );
}
