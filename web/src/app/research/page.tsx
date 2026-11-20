import type { Metadata } from "next";
import { Insights } from "@/components/research/Insights";
import { Footer } from "@/components/layout/Footer";
import { Eyebrow } from "@/components/ui/primitives";
import { SplitReveal } from "@/components/ui/Reveal";
import { BulletList } from "@/components/ml/ModuleShell";

export const metadata: Metadata = { title: "Research Insights" };

export default function ResearchPage() {
  return (
    <main id="main" className="pt-16">
      <section className="container-x py-20 md:py-28">
        <Eyebrow>Research insights</Eyebrow>
        <div className="mt-8 grid gap-10 lg:grid-cols-[1.3fr_1fr] lg:items-end">
          <SplitReveal as="h1" trigger="mount" className="t-h1 text-glacial" lines={["What the", <span key="b">records <span className="t-serif text-ice">show.</span></span>]} />
          <p className="t-lead">
            Findings computed directly from the archive and the model outputs when this page loads. Each one states its data source and method; none implies a
            cause.
          </p>
        </div>
        <div className="mt-16">
          <Insights />
        </div>
        <div className="mt-24 grid gap-12 lg:grid-cols-2">
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
      </section>
      <Footer />
    </main>
  );
}
