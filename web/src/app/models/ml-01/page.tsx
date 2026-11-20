import type { Metadata } from "next";
import { ModuleShell, Prose, BulletList } from "@/components/ml/ModuleShell";
import { MapViewer } from "@/components/ml/MapViewer";
import { Ml01Limits, Ml01Metrics, Ml01Model, Ml01Sectors, Ml01Summary } from "@/components/ml/Ml01Live";
import { KV } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "ML-01 Sea-Ice Forecasting" };

export default function Page() {
  return (
    <ModuleShell
      slug="ml-01"
      headline={["Sea-ice", <span key="b">forecasting, <span className="t-serif text-ice">one week</span> ahead.</span>]}
      lead="A convolutional U-Net predicts the 7-day mean Antarctic sea-ice concentration for the coming week on the 25 km NSIDC grid, learning the change relative to persistence from 47 years of passive-microwave observations."
      heroAside={<Ml01Summary />}
      sections={[
        {
          id: "overview",
          title: "Overview",
          content: (
            <Prose>
              <p>
                ML-01 issues a <strong>weekly-mean sea-ice concentration forecast</strong> for days t+1…t+7 over the whole Southern Ocean.
                From the forecast field it derives sea-ice <strong>extent</strong> (area with ≥ 15 % concentration), <strong>area</strong> and
                the forecast ice edge, regionally for the five NSIDC sectors.
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
                Sea ice controls heat, moisture and momentum exchange between ocean and atmosphere and sets the conditions for shipping, logistics
                and ecosystems. The objective is a <strong>skilful, honest weekly outlook</strong> that beats persistence and climatology baselines
                on held-out years — not an operational navigation product.
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
                ["Sea-ice concentration", "NOAA/NSIDC Climate Data Record v6 (G02202), daily, 25 km, 1979 → 2026"],
                ["Atmosphere (past week)", "NCEP/NCAR Reanalysis 1 daily means — interim substitute for ERA5"],
                ["Derived predictors", "Lagged SIC (d0…d-k), weekly means, anomalies, climatology, trend, day-of-year encoding — 39 features"],
                ["Target", "7-day mean SIC for days t+1…t+7, modelled as a residual over persistence"],
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
                "Strictly time-ordered split: training 1979–2015, validation 2016–2020, test 2021–2025 (no random temporal splits, no future information in predictors). The final model is refitted on 1979–2020.",
                "Candidates: LightGBM, XGBoost and random-forest regressors, a residual U-Net, and a SIC-only tree fallback used when atmospheric inputs are missing.",
                "Baselines: persistence (last day / last week), anomaly persistence, linear trend and climatology.",
                "Selection on validation only; the frozen decision record is kept with the model files.",
                "Outputs: GeoTIFF + NetCDF fields, extent / area / ice-edge statistics, regional summaries and map layers served by the API.",
              ]}
            />
          ),
        },
        { id: "map", title: "Interactive visualisation", content: <MapViewer product="sic" initial="forecast_7day_mean" /> },
        { id: "results", title: "Regional results", content: <Ml01Sectors /> },
        { id: "metrics", title: "Evaluation metrics", content: <Ml01Metrics /> },
        { id: "model", title: "Model details", content: <Ml01Model /> },
        { id: "limitations", title: "Known limitations", content: <Ml01Limits /> },
        {
          id: "provenance",
          title: "Data provenance",
          content: (
            <Prose>
              <p>
                API endpoints: <code className="font-mono text-ice">/forecast/latest</code>, <code className="font-mono text-ice">/forecast/metrics</code>,{" "}
                <code className="font-mono text-ice">/model/info</code>, <code className="font-mono text-ice">/layers/sic/latest</code>. Every forecast file
                carries its issue time, model version, input-quality flags and limitations. Uncertainty is shown only when the backend marks it as validated.
              </p>
            </Prose>
          ),
        },
      ]}
    />
  );
}
