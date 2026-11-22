"use client";
import { useMemo, useState } from "react";
import { useApi } from "@/hooks/useApi";
import type { LayerManifest, Ml04Events, Ml04Latest, Ml04Metrics, Ml04ModelInfo, Ml04MonthlySummary } from "@/lib/api/types";
import { DataBadge, ErrorState, KV, Loading, Stat } from "@/components/ui/primitives";
import { TimeSeries } from "@/components/charts/TimeSeries";
import { MetricsTable } from "./MetricsTable";
import { BulletList } from "./ModuleShell";
import { cn, fmt, titleCase } from "@/lib/utils";

const VARS: Record<string, string> = {
  t2m: "2 m temperature",
  slp: "Sea-level pressure",
  wspd: "Wind speed",
  rhum: "Relative humidity",
  prate: "Precipitation rate",
  tcdc: "Cloud cover",
  z500: "500 hPa height",
  sic: "Sea-ice concentration",
};

export function Ml04Summary() {
  const { data, error, loading } = useApi<Ml04Latest>("/api/ml04/latest");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorState error={error} what="the latest month" />;
  const s = data.latest_multivariate;
  return (
    <div className="rounded-[var(--radius)] border border-alert/40 bg-polar/60 p-6 backdrop-blur">
      <div className="flex flex-wrap items-center gap-3">
        <DataBadge type="statistical_anomaly" />
        <span className="font-mono text-[0.6875rem] text-muted">Latest multivariate month · {s.month}</span>
      </div>
      <div className="mt-6 grid grid-cols-2 gap-6">
        <Stat label="Flagged cells" value={fmt(s.statistics.multivariate_flag_cells, 0)} note="≥ moderate severity, 2.5° grid" accent="#e76f6a" />
        <Stat label="Strong or extreme" value={fmt(s.statistics.strong_or_extreme_cells, 0)} note="Base-rate classes P98 / P99.5" />
      </div>
      <p className="mt-6 font-mono text-[0.6563rem] leading-relaxed text-muted">
        {s.model_version} · method {s.selected_method}
        <span className="block text-warn">Statistical unusualness only — not a confirmed extreme event.</span>
      </p>
    </div>
  );
}

export function Ml04Variables() {
  const { data, error, loading } = useApi<Ml04Latest>("/api/ml04/latest");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorState error={error} what="variable anomalies" />;
  const st = data.latest_multivariate.statistics;
  const vars = Object.keys(VARS).filter((k) => st[`${k}_area_weighted_mean_z`] != null);
  return (
    <div className="grid gap-12 lg:grid-cols-2">
      <div>
        <p className="t-meta mb-5">Area-weighted mean z-score · {data.latest_multivariate.month}</p>
        <div className="space-y-3.5">
          {vars.map((k) => {
            const z = st[`${k}_area_weighted_mean_z`];
            const w = Math.min(Math.abs(z) / 1.5, 1) * 50;
            return (
              <div key={k} className="grid grid-cols-[9.375rem_minmax(0,1fr)_3.5rem] items-center gap-3 text-[0.8125rem]">
                <span className="text-silver">{VARS[k]}</span>
                <div className="relative h-2.5">
                  <div className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
                  <div className="absolute inset-y-0 rounded-sm" style={{ background: z >= 0 ? "#e76f6a" : "#48c8e8", left: z >= 0 ? "50%" : `${50 - w}%`, width: `${w}%` }} />
                </div>
                <span className="t-num text-right text-glacial">{z >= 0 ? "+" : ""}{fmt(z, 2)}</span>
              </div>
            );
          })}
        </div>
        <p className="mt-4 font-mono text-[0.625rem] text-muted">σ relative to the {data.latest_multivariate.period ? "1981–2010 model baseline" : "baseline"}; scale ±1.5σ.</p>
      </div>
      <div>
        <p className="t-meta mb-5">Flagged cells by region</p>
        <div className="space-y-3.5">
          {data.latest_multivariate.regions.map((r) => (
            <div key={r.region} className="grid grid-cols-[10.625rem_minmax(0,1fr)_4.5rem] items-center gap-3 text-[0.8125rem]">
              <span className="text-silver">{titleCase(r.region)}</span>
              <div className="h-2.5 rounded-sm bg-navy">
                <div className="h-full rounded-sm bg-alert" style={{ width: `${(r.flagged / Math.max(r.cells, 1)) * 100}%` }} />
              </div>
              <span className="t-num text-right text-glacial">
                {r.flagged}/{r.cells}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function Ml04Trend() {
  const { data, error, loading } = useApi<Ml04MonthlySummary>("/api/ml04/monthly-summary");
  const [v, setV] = useState("multivariate");
  const series = useMemo(() => {
    if (!data) return null;
    const rows = data.rows;
    const key = v === "multivariate" ? "multivariate_flag_area_fraction" : `${v}_flag_area_fraction`;
    const vals = rows.map((r) => (typeof r[key] === "number" ? (r[key] as number) * 100 : null));
    const run = vals.map((_, i) => {
      if (i < 11) return null;
      const w = vals.slice(i - 11, i + 1).filter((x): x is number => x != null);
      return w.length >= 9 ? w.reduce((a, b) => a + b, 0) / w.length : null;
    });
    return { t: rows.map((r) => r.month), vals, run };
  }, [data, v]);
  if (loading) return <Loading />;
  if (error || !data || !series) return <ErrorState error={error} what="the monthly trend" />;
  return (
    <div>
      <div className="mb-5 flex flex-wrap gap-2">
        {["multivariate", ...Object.keys(VARS)].map((k) => (
          <button key={k} onClick={() => setV(k)} className={cn("rounded-full border px-3 py-1.5 text-[0.75rem]", v === k ? "border-alert text-alert" : "border-line text-silver hover:text-glacial")}>
            {k === "multivariate" ? "Multivariate (LOF)" : VARS[k]}
          </button>
        ))}
      </div>
      <TimeSeries
        units="% of area"
        height={320}
        brush
        digits={1}
        series={[
          { key: "m", name: "Flagged area (monthly)", color: "rgba(255,106,61,0.45)", t: series.t, v: series.vals, kind: "area" },
          { key: "r", name: "12-month mean", color: "#e76f6a", t: series.t, v: series.run },
        ]}
      />
      <p className="mt-3 text-[0.75rem] text-muted">
        Share of the 50–90° S area flagged at ≥ moderate severity. Expected base rate under the 1979–2010 training climate: 5 %. {data.note}
      </p>
    </div>
  );
}

export function Ml04Events() {
  const { data, error, loading } = useApi<Ml04Events>("/api/ml04/events");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorState error={error} what="anomaly episodes" />;
  const top = [...data.events].sort((a, b) => b.max_area_km2 - a.max_area_km2).slice(0, 12);
  return (
    <div>
      <p className="mb-5 max-w-3xl text-[0.8125rem] text-silver">{data.definition}</p>
      <div className="overflow-x-auto" data-lenis-prevent>
        <table className="w-full min-w-[40rem] text-[0.8125rem]">
          <thead>
            <tr className="border-b border-line-strong text-left font-mono text-[0.625rem] uppercase tracking-[0.14em] text-muted">
              <th className="py-3 font-normal">Period</th>
              <th className="py-3 font-normal">Regions</th>
              <th className="py-3 text-right font-normal">Months</th>
              <th className="py-3 text-right font-normal">Max area</th>
              <th className="py-3 text-right font-normal">Peak score</th>
              <th className="py-3 text-right font-normal">Method agreement</th>
            </tr>
          </thead>
          <tbody>
            {top.map((e) => (
              <tr key={e.event_id} className="border-b border-line">
                <td className="py-2.5 font-mono text-glacial">{e.start === e.end ? e.start : `${e.start} → ${e.end}`}</td>
                <td className="py-2.5 text-silver">{e.regions.split(/[;,]/).map((r) => titleCase(r.trim())).join(", ")}</td>
                <td className="t-num py-2.5 text-right text-silver">{e.n_months}</td>
                <td className="t-num py-2.5 text-right text-silver">{fmt(e.max_area_km2 / 1e3, 0)}k km²</td>
                <td className="t-num py-2.5 text-right text-alert">{fmt(e.peak_score, 2)}</td>
                <td className="t-num py-2.5 text-right text-silver">{fmt(e.mean_agreement, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 font-mono text-[0.625rem] text-muted">Largest 12 of {data.events.length} episodes by area. {data.note}</p>
    </div>
  );
}

export function Ml04Metrics() {
  const { data, error, loading } = useApi<Ml04Metrics>("/api/ml04/metrics");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorState error={error} what="evaluation metrics" />;
  const rows = data.test ?? data.validation;
  return (
    <div>
      <div className="mb-6 flex items-start gap-3 rounded border border-warn/40 bg-warn/5 p-4 text-[0.8125rem] text-silver">
        <DataBadge type="demo" className="shrink-0" />
        <p>
          <strong className="text-glacial">Synthetic evaluation.</strong> {data.evaluation}. These scores measure whether each detector recovers anomalies
          deliberately injected into held-out data; they are software and method tests, not accuracy against real events.
        </p>
      </div>
      <MetricsTable
        rows={rows}
        highlight={["lof_k20"]}
        cols={[
          { key: "pr_auc", label: "PR-AUC", digits: 3, better: "higher" },
          { key: "roc_auc", label: "ROC-AUC", digits: 3, better: "higher" },
          { key: "recall_at_moderate", label: "Recall @ moderate", digits: 3, better: "higher" },
          { key: "flag_rate_non_injected", label: "False-flag rate", digits: 3, better: "lower" },
        ]}
      />
      <p className="mt-2 font-mono text-[0.625rem] text-muted">{data.test ? "Test split (2018–2025)" : "Validation split (2011–2017)"} with injected anomalies.</p>
    </div>
  );
}

export function Ml04Model() {
  const { data, error, loading } = useApi<Ml04ModelInfo>("/api/ml04/model-info");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorState error={error} what="model information" />;
  return (
    <KV
      rows={[
        ["Model version", data.model_version],
        ["Selected detector", `${data.selected_multivariate} (${data.family}, ${JSON.stringify(data.params ?? {})})`],
        ["Features", data.features.join(", ")],
        ["Training period", data.train_period],
        ["Baselines", `model ${data.baseline_model} · reporting ${data.baseline_reporting}`],
        ["Severity thresholds", Object.entries(data.severity_thresholds).map(([k, v]) => `${k} ${fmt(v, 2)}`).join(" · ")],
        ["Reference methods", data.reference_methods.join(", ")],
      ]}
    />
  );
}

export function Ml04Limits() {
  const { data } = useApi<LayerManifest>("/layers/anom/latest");
  const lim = (data?.limitations as string[] | undefined) ?? [];
  return lim.length ? <BulletList items={lim} /> : <Loading />;
}

