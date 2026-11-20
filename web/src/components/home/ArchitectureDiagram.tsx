"use client";
import { useLayoutEffect, useRef } from "react";
import { getGsap, prefersReducedMotion } from "@/lib/animations/gsap";

/**
 * Actual AETHENTRA pipeline (repository: scripts/, src/aethentra/, api/, web/).
 * Columns: acquisition → preprocessing → models → serving → frontend.
 */
const COLS = [
  {
    h: "Acquisition",
    items: ["NSIDC G02202 v6", "NOAA PSL NCEP R1", "Sentinel-1 EW GRD", "USNIC ice charts", "ERA5 · MERRA-2", "Copernicus Marine C1–C7"],
  },
  {
    h: "Preprocessing",
    items: ["Polar-stereographic regridding", "Daily → weekly / monthly cubes", "SAR calibration & geocoding", "Climatologies 1981–2010 / 1991–2020", "Time-ordered splits"],
  },
  {
    h: "Models",
    items: ["ML-01 U-Net sea-ice forecast", "ML-02 U-Net temperature forecast", "ML-03 U-Net SAR segmentation", "ML-04 LOF anomaly detector"],
  },
  {
    h: "Serving",
    items: ["FastAPI · 45 routes", "GeoTIFF / NetCDF / JSON", "PNG + reprojected globe layers", "Provenance & limitations"],
  },
  {
    h: "Frontend",
    items: ["Next.js · TypeScript", "CesiumJS globe", "GSAP scrollytelling", "Recharts dashboards"],
  },
];

export function ArchitectureDiagram() {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!ref.current || prefersReducedMotion()) return;
    const { gsap } = getGsap();
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({ scrollTrigger: { trigger: ref.current, start: "top 75%", once: true } });
      tl.from(".arch-col", { autoAlpha: 0, y: 30, duration: 0.8, stagger: 0.12, ease: "power3.out" })
        .from(".arch-flow", { scaleX: 0, transformOrigin: "left center", duration: 0.6, stagger: 0.12, ease: "power2.inOut" }, "-=0.6")
        .from(".arch-item", { autoAlpha: 0, x: -8, duration: 0.4, stagger: 0.02 }, "-=0.6");
    }, ref);
    return () => ctx.revert();
  }, []);
  return (
    <div ref={ref} className="grid gap-4 lg:grid-cols-5">
      {COLS.map((c, i) => (
        <div key={c.h} className="arch-col relative rounded-[var(--radius)] border border-line bg-navy/30 p-5">
          <p className="t-meta">
            <span className="text-cyan">0{i + 1}</span> · {c.h}
          </p>
          <ul className="mt-5 space-y-2.5">
            {c.items.map((it) => (
              <li key={it} className="arch-item flex gap-2 text-[13px] leading-snug text-silver">
                <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-ice/60" />
                {it}
              </li>
            ))}
          </ul>
          {i < COLS.length - 1 && <span className="arch-flow absolute -right-4 top-9 hidden h-px w-4 bg-cyan/70 lg:block" />}
        </div>
      ))}
    </div>
  );
}
