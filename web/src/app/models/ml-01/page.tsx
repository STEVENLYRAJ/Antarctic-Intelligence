import type { Metadata } from "next";
import { ModuleShell, Prose, BulletList, Sub } from "@/components/ml/ModuleShell";
import { MapViewer } from "@/components/ml/MapViewer";
import { Ml01Limits, Ml01Metrics, Ml01Model, Ml01Sectors, Ml01Summary } from "@/components/ml/Ml01Live";
import { Ml01Skill } from "@/components/ml/Evaluation";
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
          title: "Module introduction",
          content: (
            <Prose>
              <p>
                ML-01 issues a <strong>weekly-mean sea-ice concentration forecast</strong> for days t+1…t+7 over the whole Southern Ocean. From the forecast
                field it derives sea-ice <strong>extent</strong> (area with ≥ 15 % concentration), <strong>area</strong> and the forecast ice edge, regionally
                for the five NSIDC sectors.
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
                Sea ice controls heat, moisture and momentum exchange between ocean and atmosphere and sets the conditions for shipping, logistics and
                ecosystems. The objective is a <strong>skilful, honest weekly outlook</strong> that beats persistence and climatology baselines on held-out
                years — not an operational navigation product.
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
                ["Sea-ice concentration", "NOAA/NSIDC Climate Data Record v6 (G02202), daily, 25 km, 1979 → 2026"],
                ["Atmosphere (past week)", "NCEP/NCAR Reanalysis 1 daily means — interim substitute for ERA5"],
                ["Derived predictors", "Lagged SIC (d0…d-k), weekly means, anomalies, climatology, trend, day-of-year encoding — 39 features"],
                ["Target", "7-day mean SIC for days t+1…t+7, modelled as a residual over persistence"],
                ["Independent context", "OSI SAF climate record (Copernicus Marine C1) is shown in the explorer for comparison; it is not a model input"],
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
        {
          id: "visualisation",
          title: "Interactive visualisation",
          content: (
            <>
              <MapViewer product="sic" initial="forecast_7day_mean" />
              <p className="mt-4 text-[12.5px] text-muted">
                Toggle between the latest observed week and the forecast. The same layers can be draped on the 3D globe in the{" "}
                <a href="/explore?layer=sic:forecast_7day_mean" className="text-cyan hover:text-glacial">
                  Earth explorer
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
            <>
              <Sub title="Regional forecast" note="Latest forecast extent per NSIDC sector, against persistence.">
                <Ml01Sectors />
              </Sub>
              <Sub title="Test-period metrics" note="All candidates and baselines, exactly as returned by /forecast/metrics.">
                <Ml01Metrics />
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
                <Ml01Skill />
              </Sub>
              <Sub title="Deployed model">
                <Ml01Model />
              </Sub>
              <Sub title="Provenance">
                <Prose>
                  <p>
                    API endpoints: <code className="font-mono text-ice">/forecast/latest</code>, <code className="font-mono text-ice">/forecast/metrics</code>,{" "}
                    <code className="font-mono text-ice">/model/info</code>, <code className="font-mono text-ice">/layers/sic/latest</code>. Every forecast file carries
                    its issue time, model version, input-quality flags and limitations. Uncertainty is shown only when the backend marks it as validated.
                  </p>
                </Prose>
              </Sub>
            </>
          ),
        },
        { id: "limitations", title: "Limitations", content: <Ml01Limits /> },
        {
          id: "interpretation",
          title: "Research interpretation",
          content: (
            <Prose>
              <p>
                At a one-week lead, <strong>persistence is already a very strong forecast</strong>: sea ice changes slowly, so last week&apos;s field explains
                most of next week&apos;s. The value of the U-Net is in the errors that matter at the margin — on the 2021–2025 test years, which include the
                record-low winter of 2023, it reduces extent error and integrated ice-edge error relative to every baseline.
              </p>
              <p>
                The SIC-only fallback performs almost as well as the full model. This indicates that most one-week skill comes from the ice&apos;s own recent
                history rather than from the atmospheric predictors — consistent with the short lead time, and a reason to test longer leads before claiming
                atmospheric value.
              </p>
              <p>
                The forecast describes <em>what</em> the ice is likely to do next week, not <em>why</em>. It should be read alongside the observed record in
                Climate Intelligence and the explorer&apos;s OSI SAF time series.
              </p>
            </Prose>
          ),
        },
      ]}
    />
  );
}
