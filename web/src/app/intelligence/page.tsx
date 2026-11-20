import type { Metadata } from "next";
import { ClimateExplorer } from "@/components/dashboard/ClimateExplorer";
import { Footer } from "@/components/layout/Footer";
import { ButtonLink, Eyebrow } from "@/components/ui/primitives";
import { SplitReveal } from "@/components/ui/Reveal";

export const metadata: Metadata = { title: "Antarctic Climate Intelligence" };

export default function IntelligencePage() {
  return (
    <main id="main" className="pt-16">
      <section className="container-x py-20 md:py-28">
        <Eyebrow>Antarctic climate explorer</Eyebrow>
        <div className="mt-8 grid gap-10 lg:grid-cols-[1.3fr_1fr] lg:items-end">
          <SplitReveal as="h1" trigger="mount" className="t-h1 text-glacial" lines={["Forty-seven years", <span key="b">of the <span className="t-serif text-ice">southern</span> climate.</span>]} />
          <p className="t-lead">
            Monthly records from ERA5, MERRA-2, the EUMETSAT OSI SAF sea-ice climate record and the GLORYS12 ocean reanalysis — area-weighted over 60–90° S, with
            anomalies against 1991–2020 and an independent second record wherever one exists.
          </p>
        </div>
        <div className="mt-16">
          <ClimateExplorer />
        </div>
        <div className="mt-16 flex flex-wrap gap-4">
          <ButtonLink href="/explore">See anomaly maps on the globe</ButtonLink>
          <ButtonLink href="/data" variant="ghost">
            Dataset catalogue
          </ButtonLink>
        </div>
      </section>
      <Footer />
    </main>
  );
}
