import type { Metadata } from "next";
import { ModuleShell, Prose, BulletList, Sub } from "@/components/ml/ModuleShell";
import { MapViewer } from "@/components/ml/MapViewer";
import { Ml02Limits, Ml02Metrics, Ml02Model, Ml02Regions, Ml02Summary } from "@/components/ml/Ml02Live";
import { Ml02Skill } from "@/components/ml/Evaluation";
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
          title: "Module introduction",
          content: (
            <Prose>
              <p>
                ML-02 predicts the <strong>7-day mean 2 m temperature</strong> and its <strong>standardised anomaly class</strong> (strong cold … strong warm)
                for each grid cell south of 50° S, with regional summaries for East and West Antarctica, the Peninsula and the Southern Ocean.
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
          title: "Data inputs",
          content: (
            <KV
              rows={[
                ["Atmosphere", "NCEP/NCAR Reanalysis 1 daily means, 1979 → 2026-03 (interim substitute for ERA5)"],
                ["Grid", "Regridded to the 25 km EPSG:3412 polar grid shared with ML-01"],
                ["Predictors", "Lagged daily / weekly t2m, anomalies, circulation fields, sea-ice context, seasonality — 35 features"],
                ["Climatology", "1981–2010 per cell and calendar week"],
                ["ERA5 status", "ERA5 monthly (1979 → Oct 2026) and daily 2 m temperature (2014 → Oct 2026) are on disk and shown in Climate Intelligence; retraining on ERA5 has not been run"],
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
        {
          id: "visualisation",
          title: "Interactive visualisation",
          content: (
            <>
              <MapViewer product="t2m" initial="forecast_anomaly" />
              <p className="mt-4 text-[0.7813rem] text-muted">
                For the most recent reanalysis temperature (ERA5, daily to 31 Oct 2026), open the{" "}
                <a href="/explore?layer=era5_t2m_daily" className="text-cyan hover:text-glacial">
                  explorer
                </a>{" "}
                — that layer is an observation-based reanalysis, not this model&apos;s forecast.
              </p>
            </>
          ),
        },
        {
          id: "results",
          title: "Results & metrics",
          content: (
            <>
              <Sub title="Regional forecast" note="Latest forecast mean temperature and anomaly by region.">
                <Ml02Regions />
              </Sub>
              <Sub title="Test-period metrics" note="All candidates and baselines, exactly as returned by /temperature/forecast/metrics.">
                <Ml02Metrics />
              </Sub>
            </>
          ),
        },
        {
          id: "evaluation",
          title: "Evaluation",
          content: (
            <>
              <Sub title="Skill against baselines">
                <Ml02Skill />
              </Sub>
              <Sub title="Deployed model">
                <Ml02Model />
              </Sub>
              <Sub title="Provenance">
                <Prose>
                  <p>
                    API endpoints: <code className="font-mono text-ice">/temperature/forecast/latest</code>,{" "}
                    <code className="font-mono text-ice">/temperature/forecast/metrics</code>, <code className="font-mono text-ice">/temperature/model/info</code>,{" "}
                    <code className="font-mono text-ice">/layers/t2m/latest</code>. The reanalysis source is written into every forecast file.
                  </p>
                </Prose>
              </Sub>
            </>
          ),
        },
        { id: "limitations", title: "Limitations", content: <Ml02Limits /> },
        {
          id: "interpretation",
          title: "Research interpretation",
          content: (
            <Prose>
              <p>
                The U-Net is <strong>more skilful than climatology and every persistence baseline</strong> on 2018–2025, but absolute errors remain several
                degrees. Weekly Antarctic temperature is dominated by synoptic weather — blocking highs, warm-air intrusions, katabatic outflow — that is only
                partly predictable a week ahead from statistics alone.
              </p>
              <p>
                A positive anomaly correlation means the model captures part of the <em>spatial pattern</em> of warm and cold regions, which is often more
                useful than the regional mean. The anomaly classes should be read as tendencies, not as warnings of extremes.
              </p>
              <p>
                Results rest on NCEP/NCAR R1, an older reanalysis with known Antarctic biases, which ended in March 2026 at NOAA PSL. Retraining on ERA5 —
                already downloaded — is the obvious next step and has not been done.
              </p>
            </Prose>
          ),
        },
      ]}
    />
  );
}
