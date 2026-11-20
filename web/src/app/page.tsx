import Link from "next/link";
import { HeroDescent } from "@/components/scrolly/HeroDescent";
import { ModuleCards } from "@/components/home/ModuleCards";
import { ClimateTeaser } from "@/components/home/ClimateTeaser";
import { ArchitectureDiagram } from "@/components/home/ArchitectureDiagram";
import { Footer } from "@/components/layout/Footer";
import { ButtonLink, Eyebrow } from "@/components/ui/primitives";
import { Reveal, SplitReveal } from "@/components/ui/Reveal";
import { DATASETS } from "@/config/datasets";

const CHALLENGES = [
  { t: "Polar night", d: "For months each year there is no sunlight over much of the continent, so optical satellites see nothing. Microwave and radar sensors are essential." },
  { t: "Persistent cloud", d: "The Southern Ocean is one of the cloudiest regions on Earth. Synthetic-aperture radar (Sentinel-1) sees through cloud and darkness." },
  { t: "Sparse observations", d: "A continent larger than Europe has only a few dozen long-running surface stations. Reanalyses fill the gaps — with their own uncertainty." },
  { t: "Rapid change", d: "Antarctic sea ice reached record lows in 2023 after decades of slight growth. Separating variability from trend needs long, consistent records." },
];

export default function Home() {
  const modelSets = DATASETS.filter((d) => d.status.includes("model")).length;
  return (
    <main id="main">
      <HeroDescent />

      {/* SECTION — scientific challenge */}
      <section className="relative border-t border-line py-32 md:py-44">
        <div className="container-x grid gap-16 lg:grid-cols-[1fr_1.1fr]">
          <div className="lg:sticky lg:top-32 lg:self-start">
            <Eyebrow index="02">The scientific challenge</Eyebrow>
            <SplitReveal className="t-h1 mt-8 text-glacial" lines={["Observing the", <span key="l1">planet&apos;s most <span className="t-serif text-ice">remote</span></span>, "environment."]} />
            <p className="t-lead mt-8 max-w-md">
              Antarctica regulates global sea level, ocean circulation and climate — yet it is one of the hardest places on Earth to
              measure.
            </p>
          </div>
          <Reveal className="grid gap-px overflow-hidden rounded-[var(--radius)] border border-line bg-line sm:grid-cols-2">
            {CHALLENGES.map((c, i) => (
              <div key={c.t} data-reveal className="bg-polar p-8">
                <span className="font-mono text-xs text-cyan">0{i + 1}</span>
                <h3 className="t-h3 mt-5 text-glacial">{c.t}</h3>
                <p className="t-body mt-3">{c.d}</p>
              </div>
            ))}
          </Reveal>
        </div>
      </section>

      {/* SECTION — platform / ML modules */}
      <section id="platform" className="relative border-t border-line py-32 md:py-44">
        <div className="container-x">
          <div className="grid gap-10 md:grid-cols-[1.2fr_1fr] md:items-end">
            <div>
              <Eyebrow index="03">Machine-learning intelligence</Eyebrow>
              <SplitReveal className="t-h1 mt-8 text-glacial" lines={["Four models.", <span key="l2">One <span className="t-serif text-ice">frozen</span> continent.</span>]} />
            </div>
            <p className="t-lead">
              Each module is trained on a strictly time-ordered split, evaluated on held-out years, and served through the AETHENTRA API.
              The values below are the latest real outputs, labelled by data type.
            </p>
          </div>
          <Reveal className="mt-16">
            <ModuleCards />
          </Reveal>
        </div>
      </section>

      {/* SECTION — climate teaser */}
      <section className="relative border-t border-line py-32 md:py-44">
        <div className="container-x">
          <Eyebrow index="04">Antarctic climate record</Eyebrow>
          <div className="mt-8 grid gap-10 md:grid-cols-[1fr_1.4fr] md:items-end">
            <SplitReveal className="t-h1 text-glacial" lines={["Forty-seven years", <span key="l3">of <span className="t-serif text-ice">sea ice.</span></span>]} />
            <p className="t-lead">
              Monthly Antarctic sea-ice extent anomaly from two independent records — ERA5 and the EUMETSAT OSI SAF climate data record —
              relative to the 1991–2020 average.
            </p>
          </div>
          <Reveal className="mt-14">
            <ClimateTeaser />
          </Reveal>
          <div className="mt-10">
            <ButtonLink href="/intelligence" variant="ghost">
              Open the climate explorer
            </ButtonLink>
          </div>
        </div>
      </section>

      {/* SECTION — data intelligence strip */}
      <section className="relative border-t border-line py-32 md:py-40">
        <div className="container-x">
          <Eyebrow index="05">Data intelligence</Eyebrow>
          <div className="mt-8 grid gap-12 lg:grid-cols-[1fr_1.3fr]">
            <SplitReveal className="t-h1 text-glacial" lines={["Built on", <span key="l4">verified <span className="t-serif text-ice">records.</span></span>]} />
            <Reveal className="grid grid-cols-2 gap-x-10 gap-y-10 sm:grid-cols-3">
              {[
                ["14", "datasets catalogued"],
                [String(modelSets), "feed trained models"],
                ["1978", "earliest record"],
                ["≈ 105 GB", "scientific archive (raw + processed)"],
                ["4", "ML models served by the API"],
                ["3", "atmospheric reanalyses compared"],
              ].map(([v, l]) => (
                <div key={l} data-reveal className="border-t border-line pt-4">
                  <p className="t-num text-4xl text-glacial md:text-5xl">{v}</p>
                  <p className="mt-2 text-sm text-muted">{l}</p>
                </div>
              ))}
            </Reveal>
          </div>
          <div className="mt-14">
            <ButtonLink href="/data" variant="ghost">
              Browse the dataset catalogue
            </ButtonLink>
          </div>
        </div>
      </section>

      {/* SECTION — architecture */}
      <section className="relative border-t border-line py-32 md:py-40">
        <div className="container-x">
          <Eyebrow index="06">System architecture</Eyebrow>
          <SplitReveal className="t-h1 mt-8 max-w-3xl text-glacial" lines={["From raw observation", <span key="l5">to <span className="t-serif text-ice">interactive</span> intelligence.</span>]} />
          <Reveal className="mt-16">
            <ArchitectureDiagram />
          </Reveal>
        </div>
      </section>

      {/* SECTION — CTA */}
      <section className="relative overflow-hidden border-t border-line py-40">
        <div className="grid-lines absolute inset-0 opacity-60" />
        <div className="container-x relative text-center">
          <SplitReveal className="t-display mx-auto text-glacial" lines={[<span key="l6">Explore the <span className="t-serif text-ice">ice.</span></span>]} />
          <p className="t-lead mx-auto mt-8 max-w-xl">
            Fly to any Antarctic region, drape model forecasts and reanalysis anomalies over the globe, and compare them with daily satellite imagery.
          </p>
          <div className="mt-12 flex flex-wrap justify-center gap-4">
            <ButtonLink href="/explore">Launch Earth explorer</ButtonLink>
            <ButtonLink href="/about" variant="ghost">
              About AETHENTRA
            </ButtonLink>
          </div>
          <p className="mt-16 font-mono text-[11px] text-muted">
            Research prototype · statistical models · not for operational or safety-critical use ·{" "}
            <Link href="/research" className="underline decoration-line-strong underline-offset-4 hover:text-glacial">
              methods & limitations
            </Link>
          </p>
        </div>
      </section>
      <Footer />
    </main>
  );
}
