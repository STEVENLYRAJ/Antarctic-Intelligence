"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Globe2 } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { apiUrl } from "@/lib/api/client";
import type { Layer, LayerManifest } from "@/lib/api/types";
import { DataBadge, ErrorState, Legend, Loading } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

const period = (p: Layer["period"]) => (Array.isArray(p) ? `${p[0]} → ${p[1]}` : p ?? "");

/**
 * 2D map viewer for a product's latest layers (native polar-stereographic PNGs rendered by the API from GeoTIFFs).
 * Every layer shows its data type, period and units; model predictions are framed in amber.
 */
export function MapViewer({ product, initial, height = 560 }: { product: LayerManifest["product"]; initial?: string; height?: number }) {
  const { data, error, loading } = useApi<LayerManifest>(`/layers/${product}/latest`);
  const rasters = (data?.layers ?? []).filter((l) => l.png_url);
  const [sel, setSel] = useState<string | null>(null);
  const [imgOk, setImgOk] = useState<boolean | null>(null);
  useEffect(() => {
    if (!sel && rasters.length) setSel(rasters.find((l) => l.id === initial)?.id ?? rasters[0].id);
  }, [rasters, sel, initial]);
  const layer = rasters.find((l) => l.id === sel);
  useEffect(() => setImgOk(null), [sel]);

  if (loading) return <Loading label="Loading map layers" />;
  if (error || !data) return <ErrorState error={error} what="map layers" />;
  if (!rasters.length) return <p className="text-sm text-muted">No raster layers in the latest output.</p>;

  const pred = layer?.data_type.includes("prediction");
  return (
    <div className="grid gap-6 lg:grid-cols-[17.5rem_minmax(0,1fr)]">
      <div role="tablist" aria-label="Map layers" className="flex flex-col gap-1">
        {rasters.map((l) => (
          <button
            key={l.id}
            role="tab"
            aria-selected={l.id === sel}
            onClick={() => setSel(l.id)}
            className={cn(
              "rounded px-3 py-2.5 text-left text-[0.8125rem] leading-snug transition-colors",
              l.id === sel ? "bg-navy-2 text-glacial" : "text-silver hover:bg-navy hover:text-glacial",
            )}
          >
            {l.title}
            <span className="mt-1.5 flex flex-wrap items-center gap-2">
              <DataBadge type={l.data_type} />
            </span>
          </button>
        ))}
        <Link href="/explore" className="mt-4 inline-flex items-center gap-2 px-3 text-[0.75rem] text-cyan hover:underline">
          <Globe2 size={14} /> View these layers on the 3D globe
        </Link>
      </div>
      {layer && (
        <figure className="min-w-0">
          <div
            className={cn("relative flex items-center justify-center overflow-hidden rounded-[var(--radius)] border bg-[#0a1220]", pred ? "border-dashed border-warn/70" : "border-line")}
            style={{ height }}
          >
            {imgOk === false && <p className="text-sm text-muted">Layer image could not be rendered.</p>}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              key={layer.png_url}
              src={apiUrl(layer.png_url!)}
              alt={`${layer.title}, ${period(layer.period)}`}
              onLoad={() => setImgOk(true)}
              onError={() => setImgOk(false)}
              className={cn("h-full w-full object-contain transition-opacity duration-500", imgOk ? "opacity-100" : "opacity-0")}
              style={{ imageRendering: "auto" }}
            />
            {imgOk === null && <span className="absolute font-mono text-[0.6875rem] uppercase tracking-[0.16em] text-muted">Rendering…</span>}
            {pred && (
              <span className="absolute left-3 top-3 rounded-sm bg-warn px-2 py-0.5 font-mono text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-polar">
                Model prediction
              </span>
            )}
          </div>
          <figcaption className="mt-4 grid gap-4 md:grid-cols-[minmax(0,1fr)_16.25rem]">
            <div className="text-[0.8125rem] text-silver">
              <p className="text-glacial">{layer.title}</p>
              <p className="mt-1 font-mono text-[0.6875rem] text-muted">
                {period(layer.period)} · issued {layer.issue_date} · {data.forecast_id}
              </p>
            </div>
            <Legend colors={layer.style.colors} vmin={layer.style.vmin} vmax={layer.style.vmax} units={layer.units} />
          </figcaption>
        </figure>
      )}
    </div>
  );
}
