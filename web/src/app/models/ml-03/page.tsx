import type { Metadata } from "next";
import { ModuleShell, Prose, BulletList } from "@/components/ml/ModuleShell";
import { MapViewer } from "@/components/ml/MapViewer";
import { Ml03Compare, Ml03Metrics, Ml03Model, Ml03Summary } from "@/components/ml/Ml03Live";
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
          title: "Overview",
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
          title: "Input datasets",
          content: (
            <KV
              rows={[
                ["Imagery", "Copernicus Sentinel-1 EW GRDM, HH polarisation, 2018 → 2026 (1,142 scenes on disk)"],
                ["Processing", "σ⁰ from the product calibration LUT, thermal-noise removal, GCP geocoding to EPSG:3031 at 400 m"],
                ["Labels", "U.S. National Ice Center Antarctic charts (SIGRID-3), matched 0–3 days before the chart date"],
                ["Label rules", "Concentration ≥ 70 % → ice; open-water codes → water; 10–70 % and 4 km around boundaries → uncertain"],
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
        { id: "compare", title: "Interactive comparison", content: <Ml03Compare /> },
        { id: "map", title: "Weekly composite", content: <MapViewer product="sar" initial="weekly_class" /> },
        { id: "metrics", title: "Evaluation metrics", content: <Ml03Metrics /> },
        { id: "model", title: "Model details", content: <Ml03Model /> },
        {
          id: "limitations",
          title: "Known limitations",
          content: (
            <BulletList
              items={[
                "Labels are chart-scale expert analyses, not pixel-level ground truth; edge displacement against charts averages ~100 km per scene, largely reflecting chart smoothing and the 0–3 day time gap.",
                "Wind-roughened open water and smooth new ice can have similar backscatter in HH; these appear in the uncertain class.",
                "No speckle filtering or terrain correction; land and ice shelves are masked with Natural Earth + Antarctic ice-shelf polygons.",
                "Weekly detection frequency is not an ice concentration.",
              ]}
            />
          ),
        },
        {
          id: "provenance",
          title: "Data provenance",
          content: (
            <Prose>
              <p>
                API endpoints: <code className="font-mono text-ice">/seaice-detection/detection/latest</code>,{" "}
                <code className="font-mono text-ice">/seaice-detection/detection/weekly</code>, <code className="font-mono text-ice">/seaice-detection/detection/metrics</code>,{" "}
                <code className="font-mono text-ice">/seaice-detection/model/info</code>. Comparison images are exported by{" "}
                <code className="font-mono text-ice">scripts/web/build_sar_examples.py</code> from the pipeline&apos;s own scene cache and segmentation files.
              </p>
            </Prose>
          ),
        },
      ]}
    />
  );
}
