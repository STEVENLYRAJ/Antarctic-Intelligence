import type { Metadata } from "next";
import { ModuleCards } from "@/components/home/ModuleCards";
import { Footer } from "@/components/layout/Footer";
import { Eyebrow } from "@/components/ui/primitives";
import { Reveal, SplitReveal } from "@/components/ui/Reveal";

export const metadata: Metadata = { title: "ML Models" };

export default function ModelsPage() {
  return (
    <main id="main" className="pt-16">
      <section className="container-x py-24 md:py-32">
        <Eyebrow>Machine-learning intelligence</Eyebrow>
        <SplitReveal as="h1" trigger="mount" className="t-h1 mt-8 max-w-4xl text-glacial" lines={["Four models,", <span key="b">each with a <span className="t-serif text-ice">different</span> question.</span>]} />
        <p className="t-lead mt-8 max-w-2xl">
          Every module follows the same discipline: time-ordered splits, frozen selection on validation data, comparison against simple baselines on held-out
          years, and limitations published next to the results.
        </p>
        <Reveal className="mt-16">
          <ModuleCards />
        </Reveal>
      </section>
      <Footer />
    </main>
  );
}
