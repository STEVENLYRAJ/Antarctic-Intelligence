import type { Metadata } from "next";
import { Footer } from "@/components/layout/Footer";
import { ArchitectureDiagram } from "@/components/home/ArchitectureDiagram";
import { ButtonLink, Eyebrow } from "@/components/ui/primitives";
import { Reveal, SplitReveal } from "@/components/ui/Reveal";
import { BulletList } from "@/components/ml/ModuleShell";

export const metadata: Metadata = { title: "About" };

const PHASES = [
  { n: "Phase 1", t: "Antarctic Scientific Intelligence", s: "Implemented", d: "Sea-ice and temperature forecasting, SAR sea-ice detection and multivariate anomaly detection over Antarctica and the Southern Ocean." },
  { n: "Phase 2", t: "Planned direction", s: "Planned", d: "Future scientific domain — scope to be defined. Nothing in this release implements it." },
  { n: "Phase 3", t: "Planned direction", s: "Planned", d: "Future scientific domain — scope to be defined. Nothing in this release implements it." },
  { n: "Phase 4", t: "Planned direction", s: "Planned", d: "Future scientific domain — scope to be defined. Nothing in this release implements it." },
];

const STACK = [
  ["Data & science", "Python · xarray · NumPy · rasterio · pandas"],
  ["Machine learning", "PyTorch U-Nets · LightGBM · XGBoost · scikit-learn"],
  ["Serving", "FastAPI · GeoTIFF / NetCDF / JSON · reprojected globe layers"],
  ["Frontend", "Next.js 15 · TypeScript · Tailwind CSS · GSAP + ScrollTrigger · Lenis · CesiumJS · Recharts"],
  ["Imagery", "NASA GIBS Blue Marble & MODIS · Natural Earth II"],
];

export default function AboutPage() {
  return (
    <main id="main" className="pt-16">
      <section className="container-x py-20 md:py-28">
        <Eyebrow>About AETHENTRA</Eyebrow>
        <SplitReveal as="h1" trigger="mount" className="t-h1 mt-8 max-w-4xl text-glacial" lines={["Scientific intelligence", <span key="b">for Earth&apos;s <span className="t-serif text-ice">extremes.</span></span>]} />
        <div className="mt-12 grid gap-12 lg:grid-cols-2">
          <p className="t-lead">
            AETHENTRA turns long, heterogeneous scientific records into transparent, interactive intelligence: models that are evaluated honestly against
            simple baselines, outputs that always say what kind of data they are, and visualisations that let anyone explore the evidence.
          </p>
          <div>
            <p className="t-meta">Research objectives</p>
            <div className="mt-5">
              <BulletList
                items={[
                  "Forecast weekly Antarctic sea-ice concentration and 2 m temperature with measurable skill over persistence and climatology.",
                  "Map sea ice and open water from all-weather Sentinel-1 radar.",
                  "Detect statistically unusual multivariate climate conditions for expert follow-up.",
                  "Serve every output with provenance, limitations and evaluation through one API and one interface.",
                ]}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="border-t border-line py-20 md:py-28">
        <div className="container-x">
          <Eyebrow>Roadmap</Eyebrow>
          <Reveal className="mt-10 grid gap-px overflow-hidden rounded-[var(--radius)] border border-line bg-line md:grid-cols-4">
            {PHASES.map((p, i) => (
              <div key={p.n} data-reveal className={i === 0 ? "bg-navy p-8" : "bg-polar p-8"}>
                <p className="t-meta">{p.n}</p>
                <p className={`mt-4 font-mono text-[0.625rem] uppercase tracking-[0.16em] ${i === 0 ? "text-ok" : "text-muted"}`}>{p.s}</p>
                <h3 className="t-h3 mt-3 text-glacial">{p.t}</h3>
                <p className="t-body mt-3">{p.d}</p>
              </div>
            ))}
          </Reveal>
        </div>
      </section>

      <section className="border-t border-line py-20 md:py-28">
        <div className="container-x">
          <Eyebrow>Architecture</Eyebrow>
          <Reveal className="mt-10">
            <ArchitectureDiagram />
          </Reveal>
          <div className="mt-16 grid gap-12 lg:grid-cols-2">
            <div>
              <p className="t-meta">Technology</p>
              <dl className="mt-5 divide-y divide-line text-sm">
                {STACK.map(([k, v]) => (
                  <div key={k} className="grid grid-cols-[9.375rem_minmax(0,1fr)] gap-4 py-3">
                    <dt className="text-muted">{k}</dt>
                    <dd className="text-glacial">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div>
              <p className="t-meta">Sustainable Development Goals</p>
              <div className="mt-5">
                <BulletList
                  items={[
                    <span key="13">
                      <strong className="text-glacial">SDG 13 · Climate action</strong> — open, evaluated monitoring of polar sea ice and temperature supports climate
                      understanding and education.
                    </span>,
                    <span key="14">
                      <strong className="text-glacial">SDG 14 · Life below water</strong> — sea-ice extent and ocean conditions shape Southern Ocean ecosystems.
                    </span>,
                  ]}
                />
              </div>
              <p className="mt-6 text-[0.75rem] text-muted">
                AETHENTRA is a research prototype. Its outputs are statistical, have not been independently reviewed by domain experts, and must not be used for
                navigation, operations or safety-critical decisions.
              </p>
            </div>
          </div>
          <div className="mt-16 flex flex-wrap gap-4">
            <ButtonLink href="/explore">Explore Antarctica</ButtonLink>
            <ButtonLink href="/models" variant="ghost">
              The four models
            </ButtonLink>
          </div>
        </div>
      </section>
      <Footer />
    </main>
  );
}
