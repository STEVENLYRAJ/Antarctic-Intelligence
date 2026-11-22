import type { Metadata } from "next";
import { ModuleShell, Prose, BulletList, Sub } from "@/components/ml/ModuleShell";
import { MapViewer } from "@/components/ml/MapViewer";
import { Ml03Compare, Ml03Metrics, Ml03Model, Ml03Summary } from "@/components/ml/Ml03Live";
import { Ml03Skill } from "@/components/ml/Evaluation";
import { KV } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "ML-03 Satellite Sea-Ice Detection" };

export default function Page() {
  return (
    <ModuleShell
      slug="ml-03"
      headline={["Seeing ice", <span key="b">through <span className="t-serif text-ice">cloud & darkness.</span></span>]}
      lead="A U-Net segments Sentinel-1 synthetic-aperture radar scenes into sea ice and open water. Radar works day and night and through cloud — exactly where optical satellites fail over the Southern Ocean."
      heroAside={<Ml03Summary />}
      sections={[
        {
          id: "overview",
          title: "Module introduction",
          content: (
            <Prose>
              <p>
                For every Sentinel-1 Extra-Wide scene over the Antarctic sea-ice zone, ML-03 outputs a per-pixel <strong>sea-ice probability</strong>, an
                <strong> ice / open-water / uncertain</strong> class map and ice-area statistics. Scenes are combined into a weekly detection-frequency composite.
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
                Passive-microwave products (25 km) cannot resolve leads, polynyas or a sharp ice edge. The objective is a <strong>high-resolution, all-weather
                ice / water map</strong> from SAR that is consistent with expert ice charts.
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
                ["Imagery", "Copernicus Sentinel-1 EW GRDM, HH polarisation, 2018 → 2026 (1,142 scenes on disk)"],
                ["Processing", "σ⁰ from the product calibration LUT, thermal-noise removal, GCP geocoding to EPSG:3031 at 400 m"],
                ["Reference labels", "U.S. National Ice Center Antarctic charts (SIGRID-3), matched 0–3 days before the chart date — expert analyses, not pixel ground truth"],
                ["Label rules", "Concentration ≥ 70 % → ice; open-water codes → water; 10–70 % and 4 km around boundaries → uncertain"],
                ["Independent context", "DMI ASIP SAR + AMSR2 1 km concentration (Copernicus Marine C4) on 96 of the test dates, viewable in the explorer; not used for training or scoring"],
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
                "Scene-level, time-ordered split by chart date: training 2018–2022, validation 2023–2024, test 2025–2026.",
                "Candidates: σ⁰ threshold, random forest and XGBoost on texture features (GLCM, local statistics), U-Nets with BCE and BCE + Dice loss.",
                "Probabilities between 0.35 and 0.65 are reported as uncertain rather than forced into a class.",
                "Weekly composites count how often each 2 km cell was classified as ice across all valid acquisitions.",
              ]}
            />
          ),
        },
        {
          id: "visualisation",
          title: "Interactive visualisation",
          content: (
            <>
              <Sub title="SAR input vs segmentation" note="Drag the divider. Left: calibrated Sentinel-1 σ⁰. Right: model classes (ice / water / uncertain).">
                <Ml03Compare />
              </Sub>
              <Sub title="Weekly composite">
                <MapViewer product="sar" initial="weekly_class" />
              </Sub>
              <p className="mt-4 text-[0.7813rem] text-muted">
                Compare with an independent SAR + AMSR2 analysis on the same dates:{" "}
                <a href="/explore?layer=dmi_asip" className="text-cyan hover:text-glacial">
                  DMI ASIP in the explorer
                </a>
                .
              </p>
            </>
          ),
        },
        {
          id: "results",
          title: "Results & metrics",
          content: (
            <Sub title="Test-scene metrics" note="Scored against USNIC charts (agreement, not independent ground truth). Dice for ice equals the ice F1 score.">
              <Ml03Metrics />
            </Sub>
          ),
        },
        {
          id: "evaluation",
          title: "Evaluation",
          content: (
            <>
              <Sub title="Candidates compared">
                <Ml03Skill />
              </Sub>
              <Sub title="Deployed model">
                <Ml03Model />
              </Sub>
              <Sub title="Provenance">
                <Prose>
                  <p>
                    API endpoints: <code className="font-mono text-ice">/seaice-detection/detection/latest</code>,{" "}
                    <code className="font-mono text-ice">/seaice-detection/detection/weekly</code>, <code className="font-mono text-ice">/seaice-detection/detection/metrics</code>,{" "}
                    <code className="font-mono text-ice">/seaice-detection/model/info</code>. Comparison images are exported by{" "}
                    <code className="font-mono text-ice">scripts/web/build_sar_examples.py</code> from the pipeline&apos;s own scene cache and segmentation files.
                  </p>
                </Prose>
              </Sub>
            </>
          ),
        },
        {
          id: "limitations",
          title: "Limitations",
          content: (
            <BulletList
              items={[
                "Labels are chart-scale expert analyses, not pixel-level ground truth; edge displacement against charts averages tens of km per scene, largely reflecting chart smoothing and the 0–3 day time gap.",
                "Wind-roughened open water and smooth new ice can have similar backscatter in HH; these appear in the uncertain class.",
                "No speckle filtering or terrain correction; land and ice shelves are masked with Natural Earth + Antarctic ice-shelf polygons.",
                "Weekly detection frequency is not an ice concentration.",
              ]}
            />
          ),
        },
        {
          id: "interpretation",
          title: "Research interpretation",
          content: (
            <Prose>
              <p>
                Every learned model agrees with the expert charts far better than a simple backscatter threshold, which confirms that <strong>spatial texture
                context</strong> — not brightness alone — separates sea ice from wind-roughened water in single-polarisation SAR.
              </p>
              <p>
                The deployed U-Net is <strong>conservative</strong>: it has the highest ice precision but under-detects ice area relative to the charts. The
                tree models (XGBoost, random forest) are better balanced and score higher overall on this test set. We report that openly rather than
                re-selecting the model after seeing test results.
              </p>
              <p>
                Because the reference is a generalised chart issued up to three days later, edge-displacement numbers bound the agreement with charts; they are
                not a measurement of the true ice-edge error.
              </p>
            </Prose>
          ),
        },
      ]}
    />
  );
}
