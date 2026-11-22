import type { Metadata } from "next";
import { DatasetCatalogue } from "@/components/dashboard/DatasetCatalogue";
import { Footer } from "@/components/layout/Footer";
import { Eyebrow } from "@/components/ui/primitives";
import { SplitReveal } from "@/components/ui/Reveal";

export const metadata: Metadata = { title: "Scientific Data" };

export default function DataPage() {
  return (
    <main id="main" className="pt-16">
      <section className="container-x py-20 md:py-28">
        <Eyebrow>Scientific data intelligence</Eyebrow>
        <div className="mt-8 grid gap-10 lg:grid-cols-[1.3fr_minmax(0,1fr)] lg:items-end">
          <SplitReveal as="h1" trigger="mount" className="t-h1 text-glacial" lines={["What powers", <span key="b"><span className="t-serif text-ice">AETHENTRA.</span></span>]} />
          <p className="t-lead">
            Every dataset in the archive, with its source, coverage, resolution and how it is used today. A source being listed does not mean it is integrated —
            the status column says exactly where each one is used.
          </p>
        </div>
        <div className="mt-16">
          <DatasetCatalogue />
        </div>
      </section>
      <Footer />
    </main>
  );
}
