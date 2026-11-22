"use client";
import { useApi } from "@/hooks/useApi";
import type { ModelInfo, T2mForecast, T2mMetrics, LayerManifest } from "@/lib/api/types";
import { DataBadge, ErrorState, KV, Loading, Stat } from "@/components/ui/primitives";
import { MetricsTable } from "./MetricsTable";
import { BulletList } from "./ModuleShell";
import { fmt, titleCase } from "@/lib/utils";

const sign = (v: number, d = 2) => `${v >= 0 ? "+" : ""}${fmt(v, d)}`;

export function Ml02Summary() {
  const { data: f, error, loading } = useApi<T2mForecast>("/temperature/forecast/latest");
  if (loading) return <Loading />;
  if (error || !f) return <ErrorState error={error} what="the latest forecast" />;
  const all = f.regions.find((r) => r.region === "all");
  return (
    <div className="rounded-[var(--radius)] border border-dashed border-warn/50 bg-polar/60 p-6 backdrop-blur">
      <div className="flex flex-wrap items-center gap-3">
        <DataBadge type={f.data_type} />
        <span className="font-mono text-[0.6875rem] text-muted">
          {f.target_start} → {f.target_end}
        </span>
      </div>
      {all && (
        <div className="mt-6 grid grid-cols-2 gap-6">
          <Stat label="Forecast mean t2m" value={fmt(all.forecast_mean_t2m_degC, 2)} unit="°C" note="Area mean, 50–90° S" />
          <Stat label="Forecast anomaly" value={sign(all.forecast_mean_anomaly_degC)} unit="°C" accent={all.forecast_mean_anomaly_degC >= 0 ? "#e76f6a" : "#48c8e8"} note={`vs ${f.climatology_reference_period.join("–")}`} />
        </div>
      )}
      <p className="mt-6 font-mono text-[0.6563rem] leading-relaxed text-muted">
        Issued {f.issue_date} · {f.model_version}
        <span className="block text-warn">Driven by NCEP/NCAR R1, whose record ends in March 2026; the latest possible issue date is therefore 2025-12-31.</span>
      </p>
    </div>
  );
}

export function Ml02Regions() {
  const { data: f, error, loading } = useApi<T2mForecast>("/temperature/forecast/latest");
  if (loading) return <Loading />;
  if (error || !f) return <ErrorState error={error} what="regional forecast" />;
  const max = Math.max(...f.regions.map((r) => Math.abs(r.forecast_mean_anomaly_degC)), 1);
  return (
    <div className="space-y-4">
      {f.regions.map((r) => (
        <div key={r.region} className="grid grid-cols-[11.25rem_minmax(0,1fr)_7.5rem] items-center gap-4 text-[0.8125rem]">
          <span className="text-glacial">{titleCase(r.region)}</span>
          <div className="relative h-3">
            <div className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
            <div
              className="absolute inset-y-0.5 rounded-sm"
              style={{
                background: r.forecast_mean_anomaly_degC >= 0 ? "#e76f6a" : "#48c8e8",
                left: r.forecast_mean_anomaly_degC >= 0 ? "50%" : `${50 - (Math.abs(r.forecast_mean_anomaly_degC) / max) * 50}%`,
                width: `${(Math.abs(r.forecast_mean_anomaly_degC) / max) * 50}%`,
              }}
            />
          </div>
          <span className="t-num text-right text-silver">{sign(r.forecast_mean_anomaly_degC)} °C</span>
        </div>
      ))}
      <p className="pt-2 font-mono text-[0.625rem] text-muted">Forecast 7-day-mean anomaly by region · red warmer, cyan colder than the {f.climatology_reference_period.join("–")} climatology.</p>
    </div>
  );
}

const NAMES: Record<string, string> = {
  cnn_unet_final: "U-Net — final",
  final_model: "Gradient-boosted trees — final",
  damped_persistence: "Damped anomaly persistence",
  persistence: "Persistence (last day)",
  persistence_week: "Persistence (last week)",
  recent_trend: "Recent trend",
  climatology: "Climatology",
};

export function Ml02Metrics() {
  const { data, error, loading } = useApi<T2mMetrics>("/temperature/forecast/metrics");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorState error={error} what="evaluation metrics" />;
  const rows = Object.fromEntries(Object.entries(data.metrics).map(([k, v]) => [k, v.all ?? {}]));
  return (
    <div>
      <p className="mb-6 text-sm text-silver">
        Test split · {data.n_issue_dates} weekly issue dates ({data.issue_dates[0]} → {data.issue_dates[1]}) · truth: {data.source === "ncep_r1" ? "NCEP/NCAR Reanalysis 1" : data.source}.
      </p>
      <MetricsTable
        rows={rows}
        names={NAMES}
        highlight={["cnn_unet_final"]}
        cols={[
          { key: "mae_degC", label: "MAE", unit: "°C", digits: 2, better: "lower" },
          { key: "rmse_degC", label: "RMSE", unit: "°C", digits: 2, better: "lower" },
          { key: "acc_pattern_mean", label: "Anomaly corr.", digits: 3, better: "higher" },
          { key: "msss_vs_climatology", label: "MSSS vs clim.", digits: 3, better: "higher" },
          { key: "r2_anomaly", label: "R² anomaly", digits: 3, better: "higher" },
        ]}
      />
    </div>
  );
}

export function Ml02Model() {
  const { data, error, loading } = useApi<ModelInfo>("/temperature/model/info");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorState error={error} what="model information" />;
  const d = data as ModelInfo & { kind: string; selected_from: string; n_features: number; train_period: string[]; source: string; selection: string; operational_decision: string };
  return (
    <KV
      rows={[
        ["Model version", d.model_version],
        ["Architecture", `${d.kind} (${d.selected_from})`],
        ["Training period", `${d.train_period[0]} → ${d.train_period[1]}`],
        ["Input features", String(d.n_features)],
        ["Reanalysis", d.source === "ncep_r1" ? "NCEP/NCAR Reanalysis 1 (interim substitute for ERA5)" : d.source],
        ["Selection rule", d.selection],
        ["Operational rule", d.operational_decision],
      ]}
    />
  );
}

export function Ml02Limits() {
  const { data } = useApi<LayerManifest>("/layers/t2m/latest");
  const lim = (data?.limitations as string[] | undefined) ?? [];
  return lim.length ? <BulletList items={lim} /> : <Loading />;
}
