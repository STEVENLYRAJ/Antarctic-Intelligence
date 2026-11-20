"use client";
import { useApi } from "@/hooks/useApi";
import type { ModelInfo, SicForecast, SicMetrics } from "@/lib/api/types";
import { DataBadge, ErrorState, KV, Loading, Stat } from "@/components/ui/primitives";
import { MetricsTable } from "./MetricsTable";
import { BulletList } from "./ModuleShell";
import { fmt, titleCase } from "@/lib/utils";

export function Ml01Summary() {
  const { data: f, error, loading } = useApi<SicForecast>("/forecast/latest");
  if (loading) return <Loading />;
  if (error || !f) return <ErrorState error={error} what="the latest forecast" />;
  const fallback = String(f.model_version ?? "").includes("sic-only");
  return (
    <div className="rounded-[var(--radius)] border border-dashed border-warn/50 bg-polar/60 p-6 backdrop-blur">
      <div className="flex flex-wrap items-center gap-3">
        <DataBadge type={f.data_type} />
        <span className="font-mono text-[11px] text-muted">
          {f.target_start} → {f.target_end}
        </span>
      </div>
      <div className="mt-6 grid grid-cols-2 gap-6">
        <Stat label="Forecast extent" value={fmt(f.extent_km2 / 1e6, 2)} unit="M km²" />
        <Stat label="Forecast area" value={fmt(f.area_km2 / 1e6, 2)} unit="M km²" />
        <Stat label="Persistence" value={fmt(f.persistence_extent_km2 / 1e6, 2)} unit="M km²" note="Baseline: last observed week" />
        <Stat label="Climatology" value={fmt(f.climatology_extent_km2 / 1e6, 2)} unit="M km²" note="Same week, long-term mean" />
      </div>
      <p className="mt-6 font-mono text-[10.5px] leading-relaxed text-muted">
        Issued {f.issue_date} · {String(f.model_version)}
        {fallback && <span className="block text-warn">Issued by the SIC-only fallback model (atmospheric inputs unavailable for this date).</span>}
      </p>
    </div>
  );
}

export function Ml01Sectors() {
  const { data: f, error, loading } = useApi<SicForecast>("/forecast/latest");
  if (loading) return <Loading />;
  if (error || !f) return <ErrorState error={error} what="regional forecast" />;
  const max = Math.max(...f.sectors.map((s) => Math.max(s.extent_km2, s.persistence_extent_km2 ?? 0)));
  return (
    <div>
      <div className="space-y-5">
        {f.sectors.map((s) => (
          <div key={s.sector}>
            <div className="flex items-baseline justify-between text-[13px]">
              <span className="text-glacial">{titleCase(s.sector)}</span>
              <span className="t-num text-silver">
                {fmt(s.extent_km2 / 1e6, 2)} <span className="text-muted">M km² forecast</span>
                {s.persistence_extent_km2 != null && <span className="ml-3 text-muted">{fmt(s.persistence_extent_km2 / 1e6, 2)} persistence</span>}
              </span>
            </div>
            <div className="relative mt-2 h-2.5 rounded-sm bg-navy">
              {s.persistence_extent_km2 != null && <div className="absolute inset-y-0 left-0 rounded-sm bg-ice/25" style={{ width: `${(s.persistence_extent_km2 / max) * 100}%` }} />}
              <div className="absolute inset-y-[3px] left-0 rounded-sm bg-cyan" style={{ width: `${(s.extent_km2 / max) * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
      <p className="mt-5 font-mono text-[10px] text-muted">Cyan: forecast 7-day-mean extent · pale: persistence baseline. Sectors follow the NSIDC regional convention.</p>
    </div>
  );
}

const NAMES: Record<string, string> = {
  cnn_unet_final: "U-Net (residual) — final",
  final_model: "Gradient-boosted trees — final",
  final_model_sic_only: "Trees, SIC-only fallback",
  persistence: "Persistence (last day)",
  persistence_week: "Persistence (last week)",
  anomaly_persistence: "Anomaly persistence",
  linear_trend: "Linear trend",
  climatology: "Climatology",
};

export function Ml01Metrics() {
  const { data, error, loading } = useApi<SicMetrics>("/forecast/metrics");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorState error={error} what="evaluation metrics" />;
  const rows = Object.fromEntries(Object.entries(data.metrics).map(([k, v]) => [k, v.all ?? {}]));
  return (
    <div>
      <p className="mb-6 text-sm text-silver">
        Test period {data.evaluation_period[0]} → {data.evaluation_period[1]} · {data.issue_dates} weekly issue dates · all grid cells south of 50° S.
      </p>
      <MetricsTable
        rows={rows}
        names={NAMES}
        highlight={["cnn_unet_final"]}
        cols={[
          { key: "mae_pp", label: "MAE", unit: "pp", digits: 2, better: "lower" },
          { key: "rmse_pp", label: "RMSE", unit: "pp", digits: 2, better: "lower" },
          { key: "r2", label: "R²", digits: 3, better: "higher" },
          { key: "extent_mae_km2", label: "Extent MAE", unit: "k km²", digits: 0, scale: 1e-3, better: "lower" },
          { key: "iiee_mean_km2", label: "IIEE", unit: "k km²", digits: 0, scale: 1e-3, better: "lower" },
          { key: "edge_f1", label: "Edge F1", digits: 3, better: "higher" },
        ]}
      />
    </div>
  );
}

export function Ml01Model() {
  const { data, error, loading } = useApi<ModelInfo>("/model/info");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorState error={error} what="model information" />;
  const d = data as ModelInfo & { model_family: string; selected_candidate: string; target: string; operational_decision: string; training_period: string[]; grid: string; features: string[] };
  return (
    <KV
      rows={[
        ["Model version", d.model_version],
        ["Family", `${d.model_family} (${d.selected_candidate})`],
        ["Target", d.target],
        ["Training period", `${d.training_period[0]} → ${d.training_period[1]}`],
        ["Grid", d.grid],
        ["Input features", `${d.features.length}: ${d.features.slice(0, 8).join(", ")}…`],
        ["Operational rule", d.operational_decision],
      ]}
    />
  );
}

export function Ml01Limits() {
  const { data } = useApi<SicForecast>("/forecast/latest");
  const lim = (data?.limitations as string[] | undefined) ?? [];
  return lim.length ? <BulletList items={lim} /> : <Loading />;
}
