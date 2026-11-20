import type { Metadata } from "next";
import { ModuleShell, Prose, BulletList, Sub } from "@/components/ml/ModuleShell";
import { MapViewer } from "@/components/ml/MapViewer";
import { Ml04Events, Ml04Limits, Ml04Metrics, Ml04Model, Ml04Summary, Ml04Trend, Ml04Variables } from "@/components/ml/Ml04Live";
import { Ml04Skill } from "@/components/ml/Evaluation";
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
          title: "Module introduction",
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
          title: "Data inputs",
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
        {
          id: "visualisation",
          title: "Interactive visualisation",
          content: (
            <>
              <Sub title="Anomaly map">
                <MapViewer product="anom" />
              </Sub>
              <Sub title="Variable-wise analysis" note="Area-weighted mean standardised anomaly per variable for the latest multivariate month, and flagged cells by region.">
                <Ml04Variables />
              </Sub>
            </>
          ),
        },
        {
          id: "results",
          title: "Results & metrics",
          content: (
            <>
              <Sub title="Monthly trend">
                <Ml04Trend />
              </Sub>
              <Sub title="Largest anomaly episodes">
                <Ml04Events />
              </Sub>
              <Sub title="Detector metrics" note="SYNTHETIC evaluation — see Evaluation below.">
                <Ml04Metrics />
              </Sub>
            </>
          ),
        },
        {
          id: "evaluation",
          title: "Evaluation",
          content: (
            <>
              <Sub title="Detectors compared on injected anomalies">
                <Ml04Skill />
              </Sub>
              <Sub title="Deployed detector">
                <Ml04Model />
              </Sub>
              <Sub title="Provenance">
                <Prose>
                  <p>
                    API endpoints: <code className="font-mono text-ice">/api/ml04/latest</code>, <code className="font-mono text-ice">/api/ml04/monthly-summary</code>,{" "}
                    <code className="font-mono text-ice">/api/ml04/events</code>, <code className="font-mono text-ice">/api/ml04/metrics</code>,{" "}
                    <code className="font-mono text-ice">/api/ml04/model-info</code>, <code className="font-mono text-ice">/layers/anom/latest</code>.
                  </p>
                </Prose>
              </Sub>
            </>
          ),
        },
        { id: "limitations", title: "Limitations", content: <Ml04Limits /> },
        {
          id: "interpretation",
          title: "Research interpretation",
          content: (
            <Prose>
              <p>
                On injected test anomalies, the selected local-outlier-factor detector recovers <strong>compound and covariance-break anomalies</strong> far
                better than univariate z-scores, which mostly catch single-variable spikes. That is the case for a multivariate approach: unusual
                combinations can hide inside individually ordinary values.
              </p>
              <p>
                Absolute PR-AUC values are low because anomalies are rare and the definition is strict. Above all, <strong>injected anomalies are not real
                events</strong>: the evaluation shows the detector behaves as designed, not that it finds physically significant episodes.
              </p>
              <p>
                A flag means a month is statistically unusual relative to 1981–2010. It does not identify a cause, an impact or a trend. Flagged episodes are
                prompts for expert analysis.
              </p>
            </Prose>
          ),
        },
      ]}
    />
  );
}
