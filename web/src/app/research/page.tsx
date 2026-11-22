import type { Metadata } from "next";
import Link from "next/link";
import { Insights } from "@/components/research/Insights";
import { Agreement, RegimeShift, Sectors, TrendTable } from "@/components/research/Analyses";
import { Footer } from "@/components/layout/Footer";
import { Eyebrow } from "@/components/ui/primitives";
import { SplitReveal } from "@/components/ui/Reveal";
import { BulletList } from "@/components/ml/ModuleShell";

export const metadata: Metadata = { title: "Research Insights" };

const SECTIONS = [
  ["#findings", "01 Key findings"],
  ["#regimes", "02 Two sea-ice regimes"],
  ["#trends", "03 Long-term trends"],
  ["#agreement", "04 Do the records agree?"],
  ["#regions", "05 Regional picture"],
  ["#reading", "06 How to read this"],
  ["#questions", "07 Limits & open questions"],
];

function Head({ id, n, title, accent, lead }: { id: string; n: string; title: string; accent: string; lead: string }) {
  return (
    <div id={id} className="scroll-mt-24">
      <p className="t-meta flex items-center gap-3">
        <span className="text-cyan">{n}</span>
        <span className="h-px w-8 bg-line-strong" />
        Research
      </p>
      <h2 className="t-h2 mt-5 max-w-4xl text-glacial">
        {title} <span className="t-serif text-ice">{accent}</span>
      </h2>
      <p className="t-body mt-4 max-w-3xl">{lead}</p>
    </div>
  );
}

const GLOSSARY: [string, string][] = [
  ["Anomaly", "The difference between a value and the long-term average for the same calendar month (here usually 1991–2020). Anomalies remove the huge seasonal cycle so that unusual months stand out."],
  ["Climatology / baseline", "The reference average. Changing the baseline changes every anomaly, so each chart states its baseline. Records that start late (e.g. daily ERA5 from 2014) use shorter baselines, which are noisier."],
  ["Sea-ice extent", "Total area of grid cells with at least 15 % ice. It is not the same as ice area (which weights by concentration) or volume (which also needs thickness)."],
  ["Area weighting", "Grid cells shrink toward the pole, so regional means weight each cell by cos(latitude). Without this, the tiny polar cells would dominate the average."],
  ["Observation vs reanalysis", "Observations come straight from instruments (e.g. passive microwave). A reanalysis (ERA5, MERRA-2, GLORYS12) blends observations into a weather or ocean model to fill gaps — complete in space and time, but only as good as the observations constraining it."],
  ["Model prediction", "Output of a trained ML model (ML-01, ML-02). Always labelled as a prediction and never mixed with observations on this site."],
  ["Statistical anomaly (ML-04)", "A month that is unusual relative to the 1979–2010 training climate. It is a flag for further study, not a confirmed extreme event, and it carries no causal claim."],
  ["Trend ± 2 SE", "Linear slope per decade with a rough 95 % range. It ignores autocorrelation, so it overstates confidence; a straight line also cannot describe abrupt shifts such as sea ice after 2016."],
];

export default function ResearchPage() {
  return (
    <main id="main" className="pt-16">
      <section className="relative overflow-hidden">
        <div className="atmo pointer-events-none absolute inset-0" />
        <div className="container-x relative py-20 md:py-28">
          <Eyebrow>Research insights</Eyebrow>
          <div className="mt-8 grid gap-10 lg:grid-cols-[1.3fr_minmax(0,1fr)] lg:items-end">
            <SplitReveal as="h1" trigger="mount" className="t-h1 text-glacial" lines={["What the", <span key="b">records <span className="t-serif text-ice">show.</span></span>]} />
            <p className="t-lead">
              Findings computed directly from the archive and the model outputs when this page loads. Each one states its data source and method, explains why
              it matters, and stops short of claiming a cause.
            </p>
          </div>
          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {[
              ["Descriptive, not causal", "Every number here describes what the records show. Explaining why requires attribution studies that are outside Phase 1."],
              ["Computed live", "Statistics are recalculated in your browser from the same series files the Climate Intelligence page uses, so they update when the data does."],
              ["Cross-checked", "Wherever a second, independent record exists, it is compared — and disagreements are reported rather than hidden."],
            ].map(([t, d]) => (
              <div key={t} className="border-t border-line pt-4">
                <p className="font-display text-lg text-glacial">{t}</p>
                <p className="mt-2 text-[0.875rem] leading-relaxed text-silver">{d}</p>
              </div>
            ))}
          </div>
          <nav aria-label="Sections" className="mt-12 flex flex-wrap gap-2 font-mono text-[0.6875rem] uppercase tracking-[0.14em]">
            {SECTIONS.map(([h, l]) => (
              <a key={h} href={h} className="rounded-full border border-line px-3 py-1.5 text-silver hover:border-cyan hover:text-glacial">
                {l}
              </a>
            ))}
          </nav>
        </div>
      </section>

      <section className="container-x pb-24">
        <Head
          id="findings"
          n="01"
          title="Eight findings from"
          accent="the archive."
          lead="Records, extremes and persistent shifts across sea ice, atmosphere, ocean and the ML-04 detector. Each card gives the number, how it was computed, and the established science that makes it relevant."
        />
        <div className="mt-12">
          <Insights />
        </div>
      </section>

      <section className="border-t border-line py-24">
        <div className="container-x">
          <Head
            id="regimes"
            n="02"
            title="Antarctic sea ice:"
            accent="two regimes."
            lead="The single most striking feature of the 47-year record is not a steady trend but a break. This section separates the two periods so the change can be read correctly."
          />
          <div className="mt-12">
            <RegimeShift />
          </div>
        </div>
      </section>

      <section className="border-t border-line py-24">
        <div className="container-x">
          <Head
            id="trends"
            n="03"
            title="Long-term trends,"
            accent="variable by variable."
            lead="The linear change per decade for every monthly series in the archive, south of 60° S unless stated. Coloured values are distinguishable from zero under a simple test; grey values are not — and many of the most-discussed quantities fall in the grey."
          />
          <div className="surface mt-12 p-5 md:p-8">
            <TrendTable />
          </div>
        </div>
      </section>

      <section className="border-t border-line py-24">
        <div className="container-x">
          <Head
            id="agreement"
            n="04"
            title="Do independent records"
            accent="agree?"
            lead="Antarctica has very few surface observations, so every dataset leans partly on models. Comparing independent products is the most direct way to see where the evidence is solid and where it is not."
          />
          <div className="mt-12">
            <Agreement />
          </div>
          <p className="mt-6 max-w-3xl text-[0.875rem] leading-relaxed text-silver">
            Reading the four panels together: month-to-month variability is captured consistently by every pair (high correlations), but{" "}
            <strong className="text-glacial">long-term temperature trends depend on the reanalysis chosen</strong>. Any statement about Antarctic-wide warming
            from a single reanalysis should therefore be treated with caution.
          </p>
        </div>
      </section>

      <section className="border-t border-line py-24">
        <div className="container-x">
          <Head
            id="regions"
            n="05"
            title="One continent,"
            accent="five different stories."
            lead="Antarctic-wide averages hide strong regional contrasts. The table shows the last three years in each of the five standard longitude sectors used by NSIDC."
          />
          <div className="surface mt-12 p-5 md:p-8">
            <Sectors />
          </div>
          <div className="mt-8 grid gap-6 md:grid-cols-3">
            {[
              ["Why sectors differ", "The Amundsen Sea Low — a semi-permanent low-pressure centre near the Ross and Amundsen seas — steers winds that push ice northward on one side and compact it on the other, so sectors often move in opposite directions."],
              ["Pressure and wind", "Sea-level pressure anomalies show how the circumpolar westerlies have shifted. Lower pressure over Antarctica relative to mid-latitudes strengthens the westerlies (a positive Southern Annular Mode)."],
              ["Explore it on the globe", "Every sector can be opened in the 3D explorer with daily wind arrows, pressure and sea-ice layers to see the patterns behind these numbers."],
            ].map(([t, d], i) => (
              <div key={t} className="rounded-[var(--radius-lg)] border border-line bg-midnight/60 p-6">
                <p className="font-display text-lg text-glacial">{t}</p>
                <p className="mt-2 text-[0.875rem] leading-relaxed text-silver">{d}</p>
                {i === 2 && (
                  <Link href="/explore?layer=era5_wind10_daily" className="mt-4 inline-block text-[0.8125rem] text-cyan hover:text-glacial">
                    Open daily winds in the explorer →
                  </Link>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-t border-line py-24">
        <div className="container-x">
          <Head
            id="reading"
            n="06"
            title="How to read"
            accent="these findings."
            lead="A short glossary of the terms and conventions used across the platform."
          />
          <dl className="mt-12 grid gap-px overflow-hidden rounded-[var(--radius)] border border-line bg-line md:grid-cols-2">
            {GLOSSARY.map(([t, d]) => (
              <div key={t} className="bg-polar p-6 md:p-8">
                <dt className="font-display text-lg text-glacial">{t}</dt>
                <dd className="mt-2 text-[0.875rem] leading-relaxed text-silver">{d}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section className="border-t border-line py-24">
        <div className="container-x">
          <Head
            id="questions"
            n="07"
            title="Limits of the evidence and"
            accent="open questions."
            lead="What this archive can and cannot tell us, and the questions it raises for the next phase."
          />
          <div className="mt-12 grid gap-12 lg:grid-cols-2">
            <div>
              <p className="t-meta">Limits of the evidence</p>
              <div className="mt-6">
                <BulletList
                  items={[
                    "47 years is short for climate statistics, especially for a system with large decadal variability such as Antarctic sea ice.",
                    "Over the ice sheet, reanalyses are constrained by very few stations; temperature trends there differ between ERA5 and MERRA-2.",
                    "Sea-ice thickness before 2025 comes only from a model reanalysis (GLORYS12), not from observations.",
                    "Precipitation, snowfall and cloud cover are model forecast fields, the least constrained variables in any reanalysis.",
                    "Daily ERA5 records start in 2014 or 2018, so their reference envelopes are short and noisy.",
                    "No finding on this page is an attribution: none separates natural variability from forced change.",
                  ]}
                />
              </div>
            </div>
            <div>
              <p className="t-meta">Open research questions</p>
              <div className="mt-6">
                <BulletList
                  items={[
                    "Is post-2016 Antarctic sea ice a new state, or a long excursion that will recover? How much of the change is ocean heat versus winds?",
                    "Why do reanalyses disagree on Antarctic near-surface warming, and which agrees best with the sparse station record?",
                    "Can the ice-drift and wind records explain the regional pattern of sea-ice loss sector by sector?",
                    "Does ML-01 forecast skill hold in the new low-ice regime, which is outside most of its training period?",
                    "How should anomaly detectors (ML-04) handle a baseline that is itself changing?",
                  ]}
                />
              </div>
            </div>
          </div>
          <div className="mt-20 grid gap-12 lg:grid-cols-2">
            <div>
              <p className="t-meta">Scientific principles</p>
              <div className="mt-6">
                <BulletList
                  items={[
                    "Model predictions are always labelled and never presented as observations.",
                    "Time-ordered training, validation and test splits; no future information in any predictor.",
                    "Every model is compared with simple baselines (persistence, climatology) on held-out years.",
                    "Statistical anomalies are not confirmed extreme events and carry no causal claim.",
                    "Synthetic test anomalies (ML-04) are labelled as synthetic wherever they appear.",
                  ]}
                />
              </div>
            </div>
            <div>
              <p className="t-meta">Project documentation</p>
              <div className="mt-6">
                <BulletList
                  items={[
                    "docs/ml_task_04 — ML-04 model card, test report and scientific limitations",
                    "docs/phase1 — Phase 1 audit, external-data plan and CMEMS inventory",
                    "configs/ — frozen split, baseline and model configuration for every task",
                    "AETHENTRA_AI_ML_Models_Guide.docx — model guide",
                  ]}
                />
              </div>
            </div>
          </div>
        </div>
      </section>
      <Footer />
    </main>
  );
}
