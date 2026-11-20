import type { Metadata } from "next";
import { ModuleShell, Prose, BulletList } from "@/components/ml/ModuleShell";
import { MapViewer } from "@/components/ml/MapViewer";
import { Ml02Limits, Ml02Metrics, Ml02Model, Ml02Regions, Ml02Summary } from "@/components/ml/Ml02Live";
import { KV } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "ML-02 Temperature & Anomaly Forecasting" };

export default function Page() {
  return (
    <ModuleShell
      slug="ml-02"
      headline={["Temperature", <span key="b">and <span className="t-serif text-ice">anomaly</span> outlook.</span>]}
      lead="A U-Net forecasts next week's mean 2 m air temperature and its departure from the 1981–2010 climatology over Antarctica and the Southern Ocean — a statistical outlook learnt from reanalysis, not a weather forecast."
      heroAside={<Ml02Summary />}
      sections={[
        {
          id: "overview",
          title: "Overview",
          content: (
            <Prose>
              <p>
                ML-02 predicts the <strong>7-day mean 2 m temperature</strong> and its <strong>standardised anomaly class</strong> (strong cold … strong
                warm) for each grid cell south of 50° S, with regional summaries for East and West Antarctica, the Peninsula and the Southern Ocean.
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
                Weekly temperature anomalies drive surface melt on ice shelves, sea-ice growth and ecosystem stress. The objective is a
                <strong> sub-seasonal outlook with measurable skill over climatology and persistence</strong>, evaluated on years the model never saw.
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
                ["Atmosphere", "NCEP/NCAR Reanalysis 1 daily means, 1979 → 2026-03 (interim substitute for ERA5)"],
                ["Grid", "Regridded to the 25 km EPSG:3412 polar grid shared with ML-01"],
                ["Predictors", "Lagged daily / weekly t2m, anomalies, circulation fields, sea-ice context, seasonality — 35 features"],
                ["Climatology", "1981–2010 per cell and calendar week"],
                ["ERA5 status", "ERA5 daily inputs are being downloaded; retraining on ERA5 has not been run"],
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
                "Time-ordered split: training 1979–2010, validation 2011–2017, test 2018–2025.",
                "Candidates: LightGBM, XGBoost, random forest and a U-Net; selection by rank-sum of area-weighted RMSE, Antarctic-land RMSE, anomaly correlation and MAE on validation only.",
                "Baselines: climatology, persistence, damped anomaly persistence and recent trend.",
                "Anomaly classes from training-period σ per cell and season.",
              ]}
            />
          ),
        },
        { id: "map", title: "Interactive visualisation", content: <MapViewer product="t2m" initial="forecast_anomaly" /> },
        { id: "results", title: "Regional results", content: <Ml02Regions /> },
        { id: "metrics", title: "Evaluation metrics", content: <Ml02Metrics /> },
        { id: "model", title: "Model details", content: <Ml02Model /> },
        { id: "limitations", title: "Known limitations", content: <Ml02Limits /> },
        {
          id: "provenance",
          title: "Data provenance",
          content: (
            <Prose>
              <p>
                API endpoints: <code className="font-mono text-ice">/temperature/forecast/latest</code>,{" "}
                <code className="font-mono text-ice">/temperature/forecast/metrics</code>, <code className="font-mono text-ice">/temperature/model/info</code>,{" "}
                <code className="font-mono text-ice">/layers/t2m/latest</code>. The reanalysis source is written into every forecast file.
              </p>
            </Prose>
          ),
        },
      ]}
    />
  );
}
