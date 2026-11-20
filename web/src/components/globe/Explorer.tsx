"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Compass, Expand, Globe2, Grid3x3, Layers, Minus, Navigation, Plus, Search, Shrink, Snowflake, X } from "lucide-react";
import type { CameraState, GlobeHandle, Overlay } from "./CesiumGlobe";
import { apiGet, apiUrl, staticGet } from "@/lib/api/client";
import type { GlobeImage, Layer, LayerManifest } from "@/lib/api/types";
import { PLACES, VIEWS } from "@/lib/cesium/places";
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
  url: string;
  bounds: Overlay["bounds"];
  colors: string[];
  vmin: number | null;
  vmax: number | null;
  source: string;
}

const PRODUCTS: { id: LayerManifest["product"]; group: string }[] = [
  { id: "sic", group: "ML-01 · Sea ice" },
  { id: "t2m", group: "ML-02 · Temperature" },
  { id: "sar", group: "ML-03 · SAR detection" },
  { id: "anom", group: "ML-04 · Anomalies" },
];

const yesterday = () => {
  const d = new Date(Date.now() - 2 * 86400_000);
  return d.toISOString().slice(0, 10);
};

function periodText(p: Layer["period"]): string {
  return Array.isArray(p) ? `${p[0]} → ${p[1]}` : String(p);
}

export function Explorer() {
  const globe = useRef<GlobeHandle>(null);
  const shell = useRef<HTMLDivElement>(null);
  const [cam, setCam] = useState<CameraState | null>(null);
  const [ptr, setPtr] = useState<{ lat: number; lon: number } | null>(null);
  const [catalog, setCatalog] = useState<LayerEntry[]>([]);
  const [loadErr, setLoadErr] = useState<string[]>([]);
  const [active, setActive] = useState<string[]>([]);
  const [alpha, setAlpha] = useState<Record<string, number>>({});
  const [grid, setGrid] = useState(true);
  const [tcDate, setTcDate] = useState<string | null>(null);
  const [panel, setPanel] = useState(true);
  const [q, setQ] = useState("");
  const [full, setFull] = useState(false);

  /* layer catalogue: AETHENTRA model layers (API) + ERA5 anomaly images (static) */
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
                title: l.title,
                dataType: l.data_type,
                units: l.units,
                period: periodText(l.period),
                url: apiUrl(l.globe_png_url),
                bounds: l.globe_bounds,
                colors: l.style.colors,
                vmin: l.style.vmin,
                vmax: l.style.vmax,
                source: `${m.forecast_id}${m.model_version ? ` · ${m.model_version}` : ""}`,
              });
            }
          } catch (e) {
            errs.push(`${p.group}: ${(e as Error).message}`);
          }
        }),
      );
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
            url: l.url,
            bounds: l.bounds,
            colors: l.colors,
            vmin: l.vmin,
            vmax: l.vmax,
            source: l.source,
          });
      } catch (e) {
        errs.push(`ERA5 anomalies: ${(e as Error).message}`);
      }
      if (!alive) return;
      const order = [...PRODUCTS.map((p) => p.group), "ERA5 · Reanalysis anomalies"];
      entries.sort((a, b) => order.indexOf(a.group) - order.indexOf(b.group));
      setCatalog(entries);
      setLoadErr(errs);
      const first = entries.find((e) => e.key === "sic:forecast_7day_mean") ?? entries[0];
      if (first) setActive([first.key]);
    })();
    return () => {
      alive = false;
    };
  }, []);

  const overlays: Overlay[] = useMemo(
    () =>
      active
        .map((k) => catalog.find((c) => c.key === k))
        .filter((c): c is LayerEntry => !!c)
        .map((c) => ({ id: c.key, url: c.url, bounds: c.bounds, alpha: alpha[c.key] ?? 0.85 })),
    [active, catalog, alpha],
  );

  const toggle = (k: string) => setActive((a) => (a.includes(k) ? a.filter((x) => x !== k) : [...a, k]));

  const flyAntarctica = useCallback(() => globe.current?.flyTo(VIEWS.antarctica.lat, VIEWS.antarctica.lon, VIEWS.antarctica.height), []);

  const goSearch = (text: string) => {
    const m = text.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
    if (m) {
      const lat = Math.max(-90, Math.min(90, parseFloat(m[1])));
      const lon = ((parseFloat(m[2]) + 540) % 360) - 180;
      globe.current?.flyTo(lat, lon, 1_500_000);
      setQ("");
      return;
    }
    const p = PLACES.find((x) => x.name.toLowerCase().includes(text.toLowerCase()));
    if (p) {
      globe.current?.flyTo(p.lat, p.lon, p.height);
      setQ("");
    }
  };
  const suggestions = q.length >= 2 ? PLACES.filter((p) => p.name.toLowerCase().includes(q.toLowerCase())).slice(0, 7) : [];

  // Collapse the layer panel by default on narrow screens so the globe stays visible.
  useEffect(() => {
    if (window.innerWidth < 1024) setPanel(false);
  }, []);

  useEffect(() => {
    const on = () => setFull(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", on);
    return () => document.removeEventListener("fullscreenchange", on);
  }, []);
  const toggleFull = () => (document.fullscreenElement ? document.exitFullscreen() : shell.current?.requestFullscreen());

  const groups = useMemo(() => [...new Set(catalog.map((c) => c.group))], [catalog]);
  const activeEntries = active.map((k) => catalog.find((c) => c.key === k)).filter((c): c is LayerEntry => !!c);

  return (
    <div ref={shell} className="relative h-dvh w-full overflow-hidden bg-polar pt-16">
      <div className="absolute inset-0 top-16">
        <CesiumGlobe
          ref={globe}
          className="absolute inset-0"
          overlays={overlays}
          showGraticule={grid}
          trueColorDate={tcDate}
          initial={{ lat: -89.99, lon: 0, height: 11_500_000 }}
          onCamera={setCam}
          onPointer={setPtr}
        />
      </div>

      {/* Search */}
      <div className="absolute left-1/2 top-20 z-20 w-[min(460px,calc(100%-32px))] -translate-x-1/2">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            goSearch(q);
          }}
          className="flex items-center gap-2 rounded-full border border-line-strong bg-polar/85 px-4 py-2.5 backdrop-blur-md"
          role="search"
        >
          <Search size={15} className="text-muted" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search Antarctic places, or enter lat, lon"
            aria-label="Search places or coordinates"
            className="w-full bg-transparent text-sm text-glacial placeholder:text-muted focus:outline-none"
          />
          {q && (
            <button type="button" aria-label="Clear search" onClick={() => setQ("")} className="text-muted hover:text-glacial">
              <X size={14} />
            </button>
          )}
        </form>
        {suggestions.length > 0 && (
          <ul className="mt-2 overflow-hidden rounded-[var(--radius)] border border-line-strong bg-polar/95 backdrop-blur-md">
            {suggestions.map((p) => (
              <li key={p.name}>
                <button
                  onClick={() => {
                    globe.current?.flyTo(p.lat, p.lon, p.height);
                    setQ("");
                  }}
                  className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm text-silver hover:bg-navy hover:text-glacial"
                >
                  {p.name}
                  <span className="font-mono text-[10px] uppercase text-muted">
                    {p.kind} · {fmt(p.lat, 1)}°, {fmt(p.lon, 1)}°
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Layer panel */}
      <aside
        className={cn(
          "absolute bottom-14 left-4 top-20 z-10 flex w-[340px] max-w-[calc(100%-32px)] flex-col overflow-hidden rounded-[var(--radius)] border border-line-strong bg-polar/88 backdrop-blur-md transition-transform duration-500",
          panel ? "translate-x-0" : "-translate-x-[110%]",
        )}
        aria-label="Map layers"
      >
        <header className="flex items-center justify-between border-b border-line px-4 py-3">
          <p className="flex items-center gap-2 font-display text-sm">
            <Layers size={15} className="text-cyan" /> Scientific layers
          </p>
          <button aria-label="Hide layer panel" onClick={() => setPanel(false)} className="text-muted hover:text-glacial">
            <X size={15} />
          </button>
        </header>
        <div className="flex-1 space-y-5 overflow-y-auto px-4 py-4" data-lenis-prevent>
          {catalog.length === 0 && !loadErr.length && <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted">Loading layer catalogue…</p>}
          {groups.map((g) => (
            <section key={g}>
              <p className="t-meta mb-2">{g}</p>
              <ul className="space-y-1">
                {catalog
                  .filter((c) => c.group === g)
                  .map((c) => {
                    const on = active.includes(c.key);
                    return (
                      <li key={c.key}>
                        <label className={cn("flex cursor-pointer items-start gap-3 rounded px-2 py-2 text-[13px] leading-snug transition-colors", on ? "bg-navy-2/70 text-glacial" : "text-silver hover:bg-navy/70")}>
                          <input type="checkbox" checked={on} onChange={() => toggle(c.key)} className="mt-0.5 accent-[var(--cyan)]" />
                          <span className="flex-1">
                            {c.title}
                            <span className="mt-1 flex flex-wrap items-center gap-2">
                              <DataBadge type={c.dataType} />
                              <span className="font-mono text-[10px] text-muted">{c.period}</span>
                            </span>
                          </span>
                        </label>
                      </li>
                    );
                  })}
              </ul>
            </section>
          ))}
          <section>
            <p className="t-meta mb-2">Satellite imagery</p>
            <label className="flex items-start gap-3 px-2 py-2 text-[13px] text-silver">
              <input type="checkbox" checked={!!tcDate} onChange={(e) => setTcDate(e.target.checked ? yesterday() : null)} className="mt-0.5 accent-[var(--cyan)]" />
              <span className="flex-1">
                MODIS Terra true colour (NASA GIBS)
                <span className="mt-1 flex items-center gap-2">
                  <DataBadge type="observation" />
                  {tcDate && (
                    <input
                      type="date"
                      value={tcDate}
                      max={yesterday()}
                      min="2000-03-01"
                      onChange={(e) => e.target.value && setTcDate(e.target.value)}
                      className="rounded border border-line bg-navy px-1.5 py-0.5 font-mono text-[10px] text-glacial"
                      aria-label="Imagery date"
                    />
                  )}
                </span>
                <span className="mt-1 block text-[11px] text-muted">Optical: no data during polar night or under cloud.</span>
              </span>
            </label>
            <label className="flex items-center gap-3 px-2 py-2 text-[13px] text-silver">
              <input type="checkbox" checked={grid} onChange={(e) => setGrid(e.target.checked)} className="accent-[var(--cyan)]" />
              Graticule & Antarctic Circle
            </label>
          </section>
          {loadErr.length > 0 && (
            <div className="rounded border border-alert/30 bg-alert/5 p-3 text-[11px] text-silver">
              <p className="text-glacial">Some layers could not be loaded</p>
              {loadErr.map((e) => (
                <p key={e} className="mt-1 font-mono text-muted">
                  {e}
                </p>
              ))}
            </div>
          )}
        </div>
        {activeEntries.length > 0 && (
          <footer className="max-h-[42%] space-y-4 overflow-y-auto border-t border-line px-4 py-4" data-lenis-prevent>
            {activeEntries.map((c) => (
              <div key={c.key}>
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-[12px] text-glacial">{c.title}</p>
                  <input
                    type="range"
                    min={0.2}
                    max={1}
                    step={0.05}
                    value={alpha[c.key] ?? 0.85}
                    onChange={(e) => setAlpha((a) => ({ ...a, [c.key]: parseFloat(e.target.value) }))}
                    aria-label={`Opacity of ${c.title}`}
                    className="w-20 accent-[var(--cyan)]"
                  />
                </div>
                <Legend className="mt-2" colors={c.colors} vmin={c.vmin} vmax={c.vmax} units={c.units} />
                <p className="mt-1 truncate font-mono text-[9.5px] text-muted" title={c.source}>
                  {c.source}
                </p>
              </div>
            ))}
          </footer>
        )}
      </aside>
      {!panel && (
        <button onClick={() => setPanel(true)} className="absolute left-4 top-20 z-10 flex items-center gap-2 rounded-full border border-line-strong bg-polar/85 px-4 py-2.5 text-[13px] backdrop-blur-md hover:border-cyan">
          <Layers size={15} className="text-cyan" /> Layers ({active.length})
        </button>
      )}

      {/* Region chips */}
      <div className="absolute right-4 top-20 z-10 hidden max-w-[220px] flex-col gap-1.5 xl:flex">
        <p className="t-meta mb-1 text-right">Regions</p>
        {["Antarctic Peninsula", "Weddell Sea", "Ross Sea", "Amundsen Sea", "East Antarctic Plateau (Dome C)", "Amery Ice Shelf / Prydz Bay"].map((n) => {
          const p = PLACES.find((x) => x.name === n)!;
          return (
            <button key={n} onClick={() => globe.current?.flyTo(p.lat, p.lon, p.height)} className="rounded-full border border-line bg-polar/80 px-3 py-1.5 text-right text-[12px] text-silver backdrop-blur-md transition-colors hover:border-cyan hover:text-glacial">
              {n}
            </button>
          );
        })}
      </div>

      {/* Navigation controls */}
      <div className="absolute bottom-14 right-4 z-10 flex flex-col overflow-hidden rounded-[var(--radius)] border border-line-strong bg-polar/85 backdrop-blur-md">
        {[
          { l: "Fly to Antarctica", i: <Snowflake size={16} />, f: flyAntarctica },
          { l: "Global view", i: <Globe2 size={16} />, f: () => globe.current?.flyTo(VIEWS.global.lat, VIEWS.global.lon, VIEWS.global.height) },
          { l: "Zoom in", i: <Plus size={16} />, f: () => globe.current?.zoom(1.6) },
          { l: "Zoom out", i: <Minus size={16} />, f: () => globe.current?.zoom(1 / 1.6) },
          { l: "Look straight down", i: <Compass size={16} />, f: () => globe.current?.resetNorth() },
          { l: "Toggle graticule", i: <Grid3x3 size={16} />, f: () => setGrid((g) => !g) },
          { l: full ? "Exit full screen" : "Full screen", i: full ? <Shrink size={16} /> : <Expand size={16} />, f: toggleFull },
        ].map((b) => (
          <button key={b.l} onClick={b.f} title={b.l} aria-label={b.l} className="border-b border-line p-2.5 text-silver last:border-0 hover:bg-navy hover:text-cyan">
            {b.i}
          </button>
        ))}
      </div>

      {/* Status bar */}
      <div className="absolute inset-x-0 bottom-0 z-10 flex h-10 items-center justify-between gap-4 overflow-x-auto border-t border-line bg-polar/90 px-4 font-mono text-[10.5px] text-muted backdrop-blur-md">
        <span className="flex shrink-0 items-center gap-2">
          <Navigation size={12} className="text-cyan" />
          {ptr ? `Cursor ${fmt(Math.abs(ptr.lat), 3)}° ${ptr.lat < 0 ? "S" : "N"}, ${fmt(Math.abs(ptr.lon), 3)}° ${ptr.lon < 0 ? "W" : "E"}` : "Cursor off globe"}
        </span>
        {cam && (
          <span className="shrink-0">
            Camera {fmt(cam.lat, 2)}°, {fmt(cam.lon, 2)}° · alt {fmt(cam.height / 1000, 0)} km · heading {fmt(cam.heading, 0)}° · pitch {fmt(cam.pitch, 0)}°
          </span>
        )}
        <span className="hidden shrink-0 lg:inline">Basemap: NASA Blue Marble (GIBS) · Natural Earth II fallback · {process.env.NEXT_PUBLIC_CESIUM_ION_TOKEN ? "Cesium World Terrain" : "ellipsoid (no terrain token)"}</span>
      </div>
    </div>
  );
}
