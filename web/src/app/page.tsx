import fs from "node:fs";
import path from "node:path";
import Link from "next/link";
import { HeroDescent } from "@/components/scrolly/HeroDescent";
import { ModuleCards } from "@/components/home/ModuleCards";
import { ClimateTeaser } from "@/components/home/ClimateTeaser";
import { ArchitectureDiagram } from "@/components/home/ArchitectureDiagram";
import { ChapterRail } from "@/components/home/ChapterRail";
import { ContinentSection } from "@/components/home/ContinentSection";
import { Footer } from "@/components/layout/Footer";
import { ButtonLink, Eyebrow } from "@/components/ui/primitives";
import { Magnetic } from "@/components/ui/interactive";
import { CountUp, Reveal, SplitReveal } from "@/components/ui/Reveal";
import { DATASETS } from "@/config/datasets";

/** Counts read at build time from the presentation catalogue, so the numbers on the page match what ships. */
function catalogueStats() {
  try {
    const p = path.join(process.cwd(), "public", "data", "globe", "catalog.json");
    const c = JSON.parse(fs.readFileSync(p, "utf8")) as { layers: { frames: unknown[] }[] };
    return { layers: c.layers.length, frames: c.layers.reduce((n, l) => n + l.frames.length, 0) };
  } catch {
    return null;
  }
}

export default function Home() {
  const modelSets = DATASETS.filter((d) => d.status.includes("model")).length;
  const cat = catalogueStats();
  const stats: [number | string, string, string?][] = [
    [DATASETS.length, "datasets catalogued"],
    [modelSets, "feed trained models"],
    [1978, "earliest record", "nofmt"],
    ["≈ 105 GB", "scientific archive (raw + processed)"],
    ...(cat ? ([[cat.layers, "time-enabled globe layers"], [cat.frames, "map frames pre-rendered for the explorer"]] as [number, string][]) : []),
  ];
  return (
    <main id="main">
      <ChapterRail />
      <HeroDescent />

      <ContinentSection />

      {/* 05 — the data */}
      <section id="data" className="relative border-t border-line py-32 md:py-44">
        <div className="container-x">
          <Eyebrow index="05">The data</Eyebrow>
          <div className="mt-8 grid gap-10 md:grid-cols-[1fr_1.4fr] md:items-end">
            <SplitReveal className="t-h1 text-glacial" lines={["Forty-seven years", <span key="l3">of <span className="t-serif text-ice">sea ice.</span></span>]} />
            <p className="t-lead">
              Monthly Antarctic sea-ice extent anomaly from two independent records — ERA5 and the EUMETSAT OSI SAF climate data record — relative to
              the 1991–2020 average.
            </p>
          </div>
          <Reveal className="mt-14">
            <ClimateTeaser />
          </Reveal>

          <div className="mt-24 grid gap-12 lg:grid-cols-[1fr_1.3fr]">
            <div>
              <h3 className="t-h2 text-glacial">
                Built on verified <span className="t-serif text-ice">records.</span>
              </h3>
              <p className="t-body mt-5 max-w-md">
                Satellite passive microwave, SAR, altimetry and radiometry; three atmospheric reanalyses; ocean reanalyses and observation-based ocean
                reconstructions. Every product on this site is computed from files in the project archive.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <ButtonLink href="/data" variant="ghost">
                  Dataset catalogue
                </ButtonLink>
                <ButtonLink href="/intelligence" variant="ghost">
                  Climate intelligence
                </ButtonLink>
              </div>
            </div>
            <Reveal className="grid grid-cols-2 gap-x-10 gap-y-10 sm:grid-cols-3">
              {stats.map(([v, l, f]) => (
                <div key={l} data-reveal className="border-t border-line pt-4">
                  <p className="t-num text-4xl text-glacial md:text-5xl">{typeof v === "number" && !f ? <CountUp value={v} /> : v}</p>
                  <p className="mt-2 text-sm text-muted">{l}</p>
                </div>
              ))}
            </Reveal>
          </div>
        </div>
      </section>

      {/* 06 — machine intelligence */}
      <section id="platform" className="relative border-t border-line py-32 md:py-44">
        <div className="atmo pointer-events-none absolute inset-0 opacity-70" />
        <div className="container-x relative">
          <div className="grid gap-10 md:grid-cols-[1.2fr_1fr] md:items-end">
            <div>
              <Eyebrow index="06">Machine intelligence</Eyebrow>
              <SplitReveal className="t-h1 mt-8 text-glacial" lines={["Four models.", <span key="l2">One <span className="t-serif text-ice">frozen</span> continent.</span>]} />
            </div>
            <p className="t-lead">
              Each module is trained on a strictly time-ordered split, evaluated on held-out years, and served through the AETHENTRA API. The values below
              are the latest real outputs, labelled by data type.
            </p>
          </div>
          <Reveal className="mt-16">
            <ModuleCards />
          </Reveal>
        </div>
      </section>

      {/* 07 — research & method */}
      <section id="research" className="relative border-t border-line py-32 md:py-40">
        <div className="container-x">
          <Eyebrow index="07">Research &amp; method</Eyebrow>
          <SplitReveal className="t-h1 mt-8 max-w-3xl text-glacial" lines={["From raw observation", <span key="l5">to <span className="t-serif text-ice">interactive</span> intelligence.</span>]} />
          <Reveal className="mt-16">
            <ArchitectureDiagram />
          </Reveal>
        </div>
      </section>

      {/* CTA */}
      <section className="relative overflow-hidden border-t border-line py-40">
        <div className="grid-lines absolute inset-0 opacity-60" />
        <div className="absolute left-1/2 top-1/2 h-[620px] w-[620px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(72,200,232,0.10),transparent_65%)]" />
        <div className="container-x relative text-center">
          <SplitReveal className="t-display mx-auto text-glacial" lines={[<span key="l6">Explore the <span className="t-serif text-ice">ice.</span></span>]} />
          <p className="t-lead mx-auto mt-8 max-w-xl">
            Fly to any Antarctic region, play 47 years of sea ice on the globe, drape model forecasts and reanalysis anomalies, and compare them with
            daily satellite imagery.
          </p>
          <div className="mt-12 flex flex-wrap justify-center gap-4">
            <Magnetic>
              <ButtonLink href="/explore">Launch Earth explorer</ButtonLink>
            </Magnetic>
            <ButtonLink href="/research" variant="ghost">
              Research insights
            </ButtonLink>
          </div>
          <p className="mt-16 font-mono text-[11px] text-muted">
            Research prototype · statistical models · not for operational or safety-critical use ·{" "}
            <Link href="/about" className="underline decoration-line-strong underline-offset-4 hover:text-glacial">
              about & limitations
            </Link>
          </p>
        </div>
      </section>
      <Footer />
    </main>
  );
}
