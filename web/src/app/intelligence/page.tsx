import type { Metadata } from "next";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { ClimateExplorer } from "@/components/dashboard/ClimateExplorer";
import { DailyRecords } from "@/components/dashboard/DailyRecordChart";
import { PolarCompare } from "@/components/dashboard/PolarCompare";
import { Footer } from "@/components/layout/Footer";
import { ButtonLink, DataBadge, Eyebrow } from "@/components/ui/primitives";
import { Spotlight } from "@/components/ui/interactive";
import { Reveal, SplitReveal } from "@/components/ui/Reveal";

export const metadata: Metadata = { title: "Antarctic Climate Intelligence" };

const GLOBE_LAYERS = [
  { id: "drift_speed", t: "Sea-ice drift", d: "Monthly drift speed 2003–2026 with direction arrows from 2023 — IFREMER AMSR-E/AMSR2.", type: "observation" },
  { id: "multiobs_sst_anom", t: "Ocean temperature anomaly", d: "Near-surface temperature vs 1993–2020 from the observation-based MULTIOBS reconstruction.", type: "observation" },
  { id: "smos_sit", t: "Sea-ice thickness (satellite)", d: "Merged CryoSat-2, Sentinel-3 and SMOS thickness analysis (AWI), weekly samples 2025–2026.", type: "observation" },
  { id: "glorys_sithick", t: "Ice thickness (reanalysis)", d: "GLORYS12 monthly thickness 2023–2026 — model reanalysis, not an observation.", type: "model_reanalysis" },
  { id: "ens_sic_spread", t: "Reanalysis disagreement", d: "Spread of sea-ice concentration across an ensemble of ocean reanalyses.", type: "model_reanalysis" },
  { id: "era5_t2m_anom_series", t: "Temperature anomaly maps", d: "ERA5 monthly 2 m temperature anomaly for the latest 36 months.", type: "reanalysis_anomaly" },
  { id: "era5_wind10_daily", t: "Katabatic and westerly winds", d: "ERA5 daily 10 m wind speed with direction arrows for the latest 92 days.", type: "reanalysis" },
  { id: "era5_z500_daily", t: "The polar vortex", d: "ERA5 daily 500 hPa geopotential height — troughs, ridges and the circumpolar jet.", type: "reanalysis" },
  { id: "era5_siconc_anom_series", t: "Sea-ice anomaly maps", d: "ERA5 monthly sea-ice concentration anomaly vs 1991–2020 for the latest 36 months.", type: "reanalysis_anomaly" },
];

export default function IntelligencePage() {
  return (
    <main id="main" className="pt-16">
      <section className="relative overflow-hidden">
        <div className="atmo pointer-events-none absolute inset-0" />
        <div className="container-x relative py-20 md:py-28">
          <Eyebrow>Antarctic climate intelligence</Eyebrow>
          <div className="mt-8 grid gap-10 lg:grid-cols-[1.3fr_minmax(0,1fr)] lg:items-end">
            <SplitReveal as="h1" trigger="mount" className="t-h1 text-glacial" lines={["Forty-seven years", <span key="b">of the <span className="t-serif text-ice">southern</span> climate.</span>]} />
            <p className="t-lead">
              Records from ERA5, MERRA-2, the EUMETSAT OSI SAF sea-ice climate record, IFREMER sea-ice drift, the GLORYS12 reanalysis and the MULTIOBS ocean
              reconstruction — each labelled with its units, coverage, method and limitations.
            </p>
          </div>
          <nav aria-label="Sections" className="mt-12 flex flex-wrap gap-2 font-mono text-[0.6875rem] uppercase tracking-[0.14em]">
            {[
              ["#monthly", "01 Monthly records"],
              ["#daily", "02 This year vs history"],
              ["#then-now", "03 Then and now"],
              ["#globe-layers", "04 On the globe"],
            ].map(([h, l]) => (
              <a key={h} href={h} className="rounded-full border border-line px-3 py-1.5 text-silver hover:border-cyan hover:text-glacial">
                {l}
              </a>
            ))}
          </nav>
        </div>
      </section>

      <section id="monthly" className="container-x scroll-mt-24 pb-24">
        <h2 className="t-h2 text-glacial">Monthly records</h2>
        <p className="t-body mt-3 max-w-2xl">Area-weighted monthly means and anomalies, with an independent second record wherever one exists.</p>
        <div className="mt-10">
          <ClimateExplorer />
        </div>
      </section>

      <section id="daily" className="scroll-mt-24 border-t border-line py-24">
        <div className="container-x">
          <h2 className="t-h2 text-glacial">
            This year against <span className="t-serif text-ice">history.</span>
          </h2>
          <p className="t-body mt-3 max-w-2xl">
            Every year on one calendar, against the reference envelope. The sea-ice record shows the abrupt shift after 2016 and the 2023 winter far below
            anything in 1991–2020.
          </p>
          <div className="surface mt-10 p-5 md:p-8">
            <DailyRecords />
          </div>
        </div>
      </section>

      <section id="then-now" className="scroll-mt-24 border-t border-line py-24">
        <div className="container-x">
          <h2 className="t-h2 text-glacial">
            Then and <span className="t-serif text-ice">now.</span>
          </h2>
          <p className="t-body mt-3 max-w-2xl">Drag to compare the same month in two years of the 47-year satellite climate record.</p>
          <div className="surface mt-10 p-5 md:p-8">
            <PolarCompare />
          </div>
        </div>
      </section>

      <section id="globe-layers" className="scroll-mt-24 border-t border-line py-24">
        <div className="container-x">
          <h2 className="t-h2 text-glacial">
            Ocean and ice <span className="t-serif text-ice">dynamics</span> on the globe.
          </h2>
          <p className="t-body mt-3 max-w-2xl">Time-enabled map layers built from the Copernicus Marine and ERA5 archive. Each opens the 3D explorer with that layer and its timeline.</p>
          <Reveal className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {GLOBE_LAYERS.map((l) => (
              <Spotlight key={l.id} className="rounded-[var(--radius-lg)]">
                <Link href={`/explore?layer=${l.id}`} data-reveal className="group block h-full rounded-[var(--radius-lg)] border border-line bg-midnight/60 p-6 transition-colors hover:bg-navy/50">
                  <div className="flex items-center justify-between">
                    <DataBadge type={l.type} />
                    <ArrowUpRight size={16} className="text-muted transition-all group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-cyan" />
                  </div>
                  <h3 className="mt-5 font-display text-lg text-glacial">{l.t}</h3>
                  <p className="mt-2 text-[0.8125rem] leading-relaxed text-silver">{l.d}</p>
                </Link>
              </Spotlight>
            ))}
          </Reveal>
          <div className="mt-14 flex flex-wrap gap-4">
            <ButtonLink href="/explore">Open the Earth explorer</ButtonLink>
            <ButtonLink href="/data" variant="ghost">
              Dataset catalogue
            </ButtonLink>
          </div>
        </div>
      </section>
      <Footer />
    </main>
  );
}
