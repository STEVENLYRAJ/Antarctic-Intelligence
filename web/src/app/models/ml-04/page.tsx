import type { Metadata } from "next";
import { ModuleShell, Prose, BulletList } from "@/components/ml/ModuleShell";
import { MapViewer } from "@/components/ml/MapViewer";
import { Ml04Events, Ml04Limits, Ml04Metrics, Ml04Model, Ml04Summary, Ml04Trend, Ml04Variables } from "@/components/ml/Ml04Live";
import { KV } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "ML-04 Climate Anomaly Intelligence" };

export default function Page() {
  return (
    <ModuleShell
      slug="ml-04"
      headline={["Finding the", <span key="b"><span className="t-serif text-ice">unusual</span> in 47 years.</span>]}
      lead="An unsupervised multivariate detector scores how unusual each month's combination of temperature, pressure, wind, humidity, precipitation, cloud, circulation and sea ice is, relative to a fixed climate baseline."
      heroAside={<Ml04Summary />}
      sections={[
        {
          id: "overview",
          title: "Overview",
          content: (
            <Prose>
              <p>
                ML-04 assigns every 2.5° grid cell and month an <strong>anomaly score</strong> and a <strong>severity class</strong> (mild → extreme), and
                groups contiguous flagged cell-months into <strong>episodes</strong>. Univariate z-score, percentile and MAD detectors are kept as references.
              </p>
            </Prose>
          ),
        },
        {
          id: "objective",
          title: "Scientific objective",
          content: (
            <Prose>
              <p>
                Compound conditions — for example warm, moist air with low sea ice — matter more than any single variable. The objective is to <strong>surface
                statistically unusual combinations</strong> for expert follow-up, without claiming causes, impacts or confirmed extremes.
              </p>
            </Prose>
          ),
        },
        {
          id: "inputs",
          title: "Input datasets",
          content: (
            <KV
              rows={[
                ["Atmosphere", "NCEP/NCAR Reanalysis 1 daily → monthly: t2m, SLP, wind speed, relative humidity, precipitation rate, cloud cover, z500"],
                ["Sea ice", "NOAA/NSIDC SIC CDR v6, aggregated to the 2.5° grid (cells need ≥ 25 % valid ocean)"],
                ["Coverage", "1979-01 → 2026-02 multivariate; sea-ice-only afterwards (NCEP R1 at NOAA PSL ends 2026-03-17)"],
              ]}
            />
          ),
        },
        {
          id: "method",
          title: "Methodology",
          content: (
            <BulletList
              items={[
                "Standardised anomalies per cell and calendar month against the leakage-free 1981–2010 baseline; reporting baseline 1991–2020.",
                "Candidates: z-score, percentile, MAD, Mahalanobis, isolation forest, local outlier factor, one-class SVM and autoencoders.",
                "Time-ordered split: train 1979–2010, validation 2011–2017, test 2018–2025. Selection by lowest rank-sum over four PR-AUC criteria among seed-stable candidates; the decision was frozen before testing.",
                "Severity classes are base rates (P90 / P95 / P98 / P99.5 of the 1979–2010 score distribution).",
              ]}
            />
          ),
        },
        { id: "map", title: "Anomaly map", content: <MapViewer product="anom" /> },
        { id: "variables", title: "Variable-wise analysis", content: <Ml04Variables /> },
        { id: "trend", title: "Monthly trend", content: <Ml04Trend /> },
        { id: "episodes", title: "Anomaly episodes", content: <Ml04Events /> },
        { id: "metrics", title: "Evaluation metrics", content: <Ml04Metrics /> },
        { id: "model", title: "Model details", content: <Ml04Model /> },
        { id: "limitations", title: "Known limitations", content: <Ml04Limits /> },
        {
          id: "provenance",
          title: "Data provenance",
          content: (
            <Prose>
              <p>
                API endpoints: <code className="font-mono text-ice">/api/ml04/latest</code>, <code className="font-mono text-ice">/api/ml04/monthly-summary</code>,{" "}
                <code className="font-mono text-ice">/api/ml04/events</code>, <code className="font-mono text-ice">/api/ml04/metrics</code>,{" "}
                <code className="font-mono text-ice">/api/ml04/model-info</code>, <code className="font-mono text-ice">/layers/anom/latest</code>.
              </p>
            </Prose>
          ),
        },
      ]}
    />
  );
}
