import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { REGIONS } from "@/config/regions";
import { Eyebrow } from "@/components/ui/primitives";
import { Reveal, SplitReveal } from "@/components/ui/Reveal";
import { Spotlight } from "@/components/ui/interactive";

const CHALLENGES = [
  { t: "Polar night", d: "Months without sunlight blind optical satellites. Microwave radiometers and radar keep observing." },
  { t: "Persistent cloud", d: "The Southern Ocean is among the cloudiest places on Earth. Sentinel-1 SAR sees through cloud and darkness." },
  { t: "Sparse observations", d: "A continent larger than Europe has a few dozen long-running stations. Reanalyses fill the gaps, with uncertainty." },
  { t: "Rapid change", d: "Antarctic sea ice hit record lows in 2023 after decades of slight growth. Separating variability from trend needs long records." },
];

/** Chapter 04: the continent. Real NASA MODIS imagery (cached from GIBS) and one-click camera destinations. */
export function ContinentSection() {
  const regions = REGIONS.filter((r) => r.imagery && r.id !== "antarctica");
  return (
    <section id="continent" className="relative overflow-hidden border-t border-line py-32 md:py-44">
      <div className="atmo pointer-events-none absolute inset-0" />
      <div className="container-x relative">
        <div className="grid gap-14 lg:grid-cols-[1fr_1.05fr] lg:items-center">
          <div>
            <Eyebrow index="04">The continent</Eyebrow>
            <SplitReveal className="t-h1 mt-8 text-glacial" lines={["A frozen continent,", <span key="a">seen from <span className="t-serif text-ice">orbit.</span></span>]} />
            <p className="t-lead mt-8 max-w-lg">
              Antarctica and its sea-ice ring as NASA&apos;s MODIS instrument saw them in mid-December 2025 — real satellite reflectance, including the
              cloud that hides much of the surface on any given day.
            </p>
            <Reveal className="mt-12 grid gap-px overflow-hidden rounded-[var(--radius-lg)] border border-line bg-line sm:grid-cols-2">
              {CHALLENGES.map((c, i) => (
                <div key={c.t} data-reveal className="bg-polar/95 p-6">
                  <span className="font-mono text-[10px] text-cyan">0{i + 1}</span>
                  <h3 className="mt-3 font-display text-[17px] text-glacial">{c.t}</h3>
                  <p className="mt-2 text-[13.5px] leading-relaxed text-silver">{c.d}</p>
                </div>
              ))}
            </Reveal>
          </div>
          <Reveal>
            <figure data-reveal className="relative mx-auto aspect-square w-full max-w-[640px]">
              <div className="absolute inset-[-8%] rounded-full bg-[radial-gradient(circle,rgba(72,200,232,0.12),transparent_62%)]" />
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/data/imagery/continent.jpg"
                alt="MODIS Terra true-colour mosaic of Antarctica and surrounding sea ice, 15 December 2025, polar stereographic projection"
                className="relative h-full w-full rounded-full object-cover shadow-[0_0_120px_rgba(72,200,232,0.15)] [mask-image:radial-gradient(circle,#000_62%,transparent_71%)]"
                loading="lazy"
              />
              <figcaption className="mt-4 text-center font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                NASA MODIS Terra corrected reflectance · 15 Dec 2025 · EPSG:3031 · via NASA GIBS (public domain)
              </figcaption>
            </figure>
          </Reveal>
        </div>

        <div className="mt-28 flex flex-wrap items-end justify-between gap-6">
          <div>
            <p className="t-meta">Destinations</p>
            <h3 className="t-h2 mt-4 text-glacial">Fly to a region.</h3>
          </div>
          <p className="max-w-md text-sm text-silver">Each card opens the 3D explorer and flies the camera to that region, with its live regional model outputs.</p>
        </div>
        <Reveal className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {regions.map((r) => (
            <Spotlight key={r.id} className="group rounded-[var(--radius-lg)]">
              <Link
                href={`/explore?region=${r.id}`}
                data-reveal
                className="relative block aspect-[4/5] overflow-hidden rounded-[var(--radius-lg)] border border-line bg-navy"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/data/imagery/${r.imagery}.jpg`}
                  alt={`Satellite view of ${r.name}`}
                  loading="lazy"
                  className="absolute inset-0 h-full w-full object-cover opacity-80 [filter:contrast(1.12)_brightness(0.82)_saturate(0.9)] transition-transform duration-[1400ms] ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:scale-[1.06]"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-polar via-polar/55 to-polar/10" />
                <div className="absolute inset-x-0 bottom-0 p-5">
                  <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ice">{r.kicker}</p>
                  <p className="mt-2 flex items-center justify-between font-display text-xl text-glacial">
                    {r.name}
                    <ArrowUpRight size={18} className="text-muted transition-all duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-cyan" />
                  </p>
                  <p className="mt-2 line-clamp-3 text-[12.5px] leading-relaxed text-silver">{r.context}</p>
                  <p className="mt-3 font-mono text-[9.5px] text-muted">
                    {Math.abs(r.centre[0]).toFixed(1)}° S · {Math.abs(r.centre[1]).toFixed(1)}° {r.centre[1] < 0 ? "W" : "E"}
                  </p>
                </div>
              </Link>
            </Spotlight>
          ))}
        </Reveal>
        <p className="mt-6 font-mono text-[10px] text-muted">Imagery: NASA EOSDIS GIBS — MODIS Terra true colour (15 Dec 2025) and Blue Marble. Polar stereographic views; grid north points toward 180°.</p>
      </div>
    </section>
  );
}
