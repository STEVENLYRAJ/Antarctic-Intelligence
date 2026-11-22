"use client";
import { useEffect, useMemo, useState } from "react";
import { useApi } from "@/hooks/useApi";
import type { GlobeCatalog } from "@/lib/api/types";
import { CompareSlider } from "@/components/ml/CompareSlider";
import { DataBadge, ErrorState, Legend, Loading } from "@/components/ui/primitives";

const SIZE = 720;
const HALF_M = 4_000_000; // must match the cached Blue Marble image (EPSG:3031, ±4,000 km)
const R = 6_371_007;
const TC = Math.tan(Math.PI / 4 - (71 * Math.PI) / 180 / 2);
const MC = Math.cos((71 * Math.PI) / 180);

function loadImg(src: string) {
  return new Promise<HTMLImageElement>((res, rej) => {
    const i = new Image();
    i.crossOrigin = "anonymous";
    i.onload = () => res(i);
    i.onerror = () => rej(new Error(`image ${src}`));
    i.src = src;
  });
}

/**
 * Reprojects an equirectangular OSI SAF frame (lon -180..180, lat south..north) to south-polar stereographic
 * (EPSG:3031, spherical approximation) and composites it over the NASA Blue Marble polar basemap.
 */
async function polarFrame(frameUrl: string, bounds: { west: number; east: number; south: number; north: number }, base: HTMLImageElement) {
  const src = await loadImg(frameUrl);
  const sc = document.createElement("canvas");
  sc.width = src.width;
  sc.height = src.height;
  const sx = sc.getContext("2d", { willReadFrequently: true })!;
  sx.drawImage(src, 0, 0);
  const sd = sx.getImageData(0, 0, src.width, src.height).data;

  const out = document.createElement("canvas");
  out.width = SIZE;
  out.height = SIZE;
  const ox = out.getContext("2d")!;
  ox.drawImage(base, 0, 0, SIZE, SIZE);
  ox.fillStyle = "rgba(5,8,13,0.35)";
  ox.fillRect(0, 0, SIZE, SIZE);
  const od = ox.getImageData(0, 0, SIZE, SIZE);
  const d = od.data;
  const lonSpan = bounds.east - bounds.west;
  const latSpan = bounds.north - bounds.south;
  for (let py = 0; py < SIZE; py++) {
    const y = HALF_M - ((py + 0.5) / SIZE) * 2 * HALF_M;
    for (let px = 0; px < SIZE; px++) {
      const x = -HALF_M + ((px + 0.5) / SIZE) * 2 * HALF_M;
      const rho = Math.hypot(x, y);
      const lat = -(90 - (2 * Math.atan((rho * TC) / (R * MC)) * 180) / Math.PI);
      if (lat > bounds.north) continue;
      const lon = (Math.atan2(x, y) * 180) / Math.PI;
      const ix = Math.floor(((lon - bounds.west) / lonSpan) * src.width);
      const iy = Math.floor(((bounds.north - lat) / latSpan) * src.height);
      if (ix < 0 || ix >= src.width || iy < 0 || iy >= src.height) continue;
      const si = (iy * src.width + ix) * 4;
      const a = sd[si + 3] / 255;
      if (a === 0) continue;
      const oi = (py * SIZE + px) * 4;
      d[oi] = sd[si] * a + d[oi] * (1 - a);
      d[oi + 1] = sd[si + 1] * a + d[oi + 1] * (1 - a);
      d[oi + 2] = sd[si + 2] * a + d[oi + 2] * (1 - a);
    }
  }
  ox.putImageData(od, 0, 0);
  // circular vignette + Antarctic Circle reference
  ox.strokeStyle = "rgba(72,200,232,0.55)";
  ox.setLineDash([4, 5]);
  const rc = (R * MC * Math.tan(Math.PI / 4 - ((66.5633 * Math.PI) / 180) / 2)) / TC;
  ox.beginPath();
  ox.arc(SIZE / 2, SIZE / 2, (rc / (2 * HALF_M)) * SIZE, 0, Math.PI * 2);
  ox.stroke();
  return out.toDataURL("image/jpeg", 0.9);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function PolarCompare() {
  const { data, error, loading } = useApi<GlobeCatalog>("/data/globe/catalog.json", true);
  const layer = data?.layers.find((l) => l.id === "osisaf_sic");
  const years = useMemo(() => (layer ? [...new Set(layer.frames.map((f) => f.t.slice(0, 4)))] : []), [layer]);
  const [month, setMonth] = useState("09");
  const [ya, setYa] = useState("1980");
  const [yb, setYb] = useState("2024");
  const [imgs, setImgs] = useState<{ a: string; b: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!layer) return;
    const fa = layer.frames.find((f) => f.t === `${ya}-${month}`);
    const fb = layer.frames.find((f) => f.t === `${yb}-${month}`);
    if (!fa || !fb) {
      setErr(`No OSI SAF monthly mean for ${!fa ? `${ya}-${month}` : `${yb}-${month}`} (missing or incomplete month).`);
      setImgs(null);
      return;
    }
    let alive = true;
    setErr(null);
    (async () => {
      try {
        const base = await loadImg("/data/imagery/continent_bluemarble.jpg");
        const [a, b] = await Promise.all([polarFrame(fa.url, layer.bounds, base), polarFrame(fb.url, layer.bounds, base)]);
        if (alive) setImgs({ a, b });
      } catch (e) {
        if (alive) setErr((e as Error).message);
      }
    })();
    return () => {
      alive = false;
    };
  }, [layer, ya, yb, month]);

  if (loading) return <Loading label="Loading sea-ice record" />;
  if (error || !data) return <ErrorState error={error} what="the sea-ice map catalogue" />;
  if (!layer) return <p className="text-sm text-muted">The OSI SAF monthly map series has not been generated yet (run scripts/web/build_globe_products.py c1).</p>;

  const sel = "rounded border border-line bg-navy px-2 py-1.5 font-mono text-[0.75rem] text-glacial";
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_17.5rem]">
      <div className="mx-auto w-full max-w-[40rem]">
        {imgs ? (
          <CompareSlider before={imgs.a} after={imgs.b} beforeLabel={`${MONTHS[+month - 1]} ${ya}`} afterLabel={`${MONTHS[+month - 1]} ${yb}`} aspect={1} />
        ) : err ? (
          <p className="rounded border border-alert/30 bg-alert/5 p-4 text-sm text-silver">{err}</p>
        ) : (
          <Loading label="Reprojecting maps" />
        )}
      </div>
      <aside className="space-y-5">
        <DataBadge type="observation" />
        <div className="grid grid-cols-2 gap-3">
          <label className="text-[0.75rem] text-muted">
            Left year
            <select value={ya} onChange={(e) => setYa(e.target.value)} className={`${sel} mt-1 w-full`}>
              {years.map((y) => (
                <option key={y}>{y}</option>
              ))}
            </select>
          </label>
          <label className="text-[0.75rem] text-muted">
            Right year
            <select value={yb} onChange={(e) => setYb(e.target.value)} className={`${sel} mt-1 w-full`}>
              {years.map((y) => (
                <option key={y}>{y}</option>
              ))}
            </select>
          </label>
        </div>
        <label className="block text-[0.75rem] text-muted">
          Month
          <select value={month} onChange={(e) => setMonth(e.target.value)} className={`${sel} mt-1 w-full`}>
            {MONTHS.map((m, i) => (
              <option key={m} value={String(i + 1).padStart(2, "0")}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap gap-2">
          {[
            ["Sep 1980 vs 2024", "1980", "2024", "09"],
            ["Feb 1990 vs 2023", "1990", "2023", "02"],
            ["Sep 2014 vs 2023", "2014", "2023", "09"],
          ].map(([l, a, b, m]) => (
            <button
              key={l}
              onClick={() => {
                setYa(a);
                setYb(b);
                setMonth(m);
              }}
              className="rounded-full border border-line px-3 py-1 text-[0.7188rem] text-silver hover:border-cyan hover:text-glacial"
            >
              {l}
            </button>
          ))}
        </div>
        <Legend colors={layer.colors} vmin={layer.vmin} vmax={layer.vmax} units={layer.units} />
        <p className="text-[0.75rem] leading-relaxed text-muted">
          Monthly mean sea-ice concentration (≥ 15 %), {layer.source}. Reprojected in your browser to south-polar stereographic over NASA Blue Marble.
          The dashed ring is the Antarctic Circle. Single months show weather-driven variability as well as long-term change.
        </p>
      </aside>
    </div>
  );
}
