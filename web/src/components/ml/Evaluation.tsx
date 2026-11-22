"use client";
import { useMemo, useState } from "react";
import { useApi } from "@/hooks/useApi";
import { ErrorState, Loading } from "@/components/ui/primitives";
import { cn, fmt } from "@/lib/utils";

const BASELINES = new Set([
  "persistence",
  "persistence_week",
  "anomaly_persistence",
  "climatology",
  "linear_trend",
  "damped_persistence",
  "recent_trend",
  "threshold",
  "zscore",
  "percentile",
  "mad",
]);

interface MetricDef {
  key: string;
  label: string;
  units?: string;
  better: "lower" | "higher" | "zero";
  digits: number;
  scale?: number;
}

type Rows = Record<string, Record<string, number | null>>;

/** Horizontal skill comparison: every candidate and baseline exactly as returned by the API; deployed model highlighted. */
function SkillBars({ rows, metrics, deployed, accent, note }: { rows: Rows; metrics: MetricDef[]; deployed: string; accent: string; note: string }) {
  const [mk, setMk] = useState(metrics[0].key);
  const m = metrics.find((x) => x.key === mk)!;
  const data = useMemo(() => {
    const out = Object.entries(rows)
      .map(([name, r]) => ({ name, v: typeof r[mk] === "number" ? (r[mk] as number) * (m.scale ?? 1) : null }))
      .filter((r): r is { name: string; v: number } => r.v !== null && Number.isFinite(r.v));
    const score = (v: number) => (m.better === "lower" ? v : m.better === "higher" ? -v : Math.abs(v));
    return out.sort((a, b) => score(a.v) - score(b.v));
  }, [rows, mk, m]);
  const max = Math.max(...data.map((d) => Math.abs(d.v)), 1e-9);
  const dep = data.find((d) => d.name === deployed);
  const bestBase = data.find((d) => BASELINES.has(d.name));
  return (
    <div>
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Metric">
        {metrics.map((x) => (
          <button
            key={x.key}
            role="tab"
            aria-selected={x.key === mk}
            onClick={() => setMk(x.key)}
            className={cn("rounded-full border px-3 py-1 text-[12px] transition-colors", x.key === mk ? "border-cyan bg-cyan/10 text-glacial" : "border-line text-silver hover:border-line-strong")}
          >
            {x.label}
          </button>
        ))}
      </div>
      <p className="mt-4 font-mono text-[10.5px] text-muted">
        {m.better === "lower" ? "Lower is better" : m.better === "higher" ? "Higher is better" : "Closer to zero is better"}
        {m.units ? ` · ${m.units}` : ""} · sorted best → worst
      </p>
      <ul className="mt-4 space-y-2">
        {data.map((d) => {
          const isDep = d.name === deployed;
          const isBase = BASELINES.has(d.name);
          return (
            <li key={d.name} className="grid grid-cols-[minmax(120px,190px)_1fr_auto] items-center gap-3 text-[12.5px]">
              <span className={cn("truncate", isDep ? "text-glacial" : "text-silver")} title={d.name}>
                {d.name}
                {isDep && (
                  <span className="ml-2 rounded-sm border px-1 font-mono text-[9px] uppercase" style={{ borderColor: accent, color: accent }}>
                    deployed
                  </span>
                )}
                {isBase && <span className="ml-2 font-mono text-[9px] uppercase text-muted">baseline</span>}
              </span>
              <span className="relative h-2.5 overflow-hidden rounded-sm bg-navy/70">
                <span
                  className="absolute inset-y-0 left-0 rounded-sm transition-[width] duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
                  style={{ width: `${(100 * Math.abs(d.v)) / max}%`, background: isDep ? accent : isBase ? "rgba(139,155,170,0.45)" : "rgba(141,220,244,0.55)" }}
                />
              </span>
              <span className="t-num w-20 text-right text-glacial">{fmt(d.v, m.digits)}</span>
            </li>
          );
        })}
      </ul>
      {dep && bestBase && (
        <p className="mt-5 text-[13px] text-silver">
          Deployed <span className="text-glacial">{deployed}</span>: {fmt(dep.v, m.digits)}
          {m.units ? ` ${m.units}` : ""} vs best baseline <span className="text-glacial">{bestBase.name}</span>: {fmt(bestBase.v, m.digits)}
          {m.units ? ` ${m.units}` : ""}.
        </p>
      )}
      <p className="mt-3 text-[12px] leading-relaxed text-muted">{note}</p>
    </div>
  );
}

function useRows(path: string, pick: (d: Record<string, unknown>) => Rows | undefined) {
  const { data, error, loading } = useApi<Record<string, unknown>>(path);
  return { rows: data ? pick(data) : undefined, error, loading };
}

const allOf = (d: Record<string, unknown>) =>
  Object.fromEntries(Object.entries((d.metrics ?? {}) as Record<string, { all?: Rows[string] }>).map(([k, v]) => [k, v.all ?? {}])) as Rows;

function Wrap({ path, pick, ...p }: { path: string; pick: (d: Record<string, unknown>) => Rows | undefined; metrics: MetricDef[]; deployed: string; accent: string; note: string }) {
  const { rows, error, loading } = useRows(path, pick);
  if (loading) return <Loading label="Loading evaluation" />;
  if (error || !rows) return <ErrorState error={error} what="evaluation metrics" />;
  return <SkillBars rows={rows} {...p} />;
}

export function Ml01Skill() {
  return (
    <Wrap
      path="/forecast/metrics"
      pick={allOf}
      deployed="cnn_unet_final"
      accent="#48c8e8"
      metrics={[
        { key: "mae_pp", label: "MAE", units: "percentage points", better: "lower", digits: 2 },
        { key: "rmse_pp", label: "RMSE", units: "percentage points", better: "lower", digits: 2 },
        { key: "extent_mae_km2", label: "Extent error", units: "thousand km²", better: "lower", digits: 0, scale: 1e-3 },
        { key: "iiee_mean_km2", label: "IIEE", units: "thousand km²", better: "lower", digits: 0, scale: 1e-3 },
        { key: "edge_f1", label: "Ice-edge F1", better: "higher", digits: 3 },
      ]}
      note="Held-out test period 2021–2025 (weekly issue dates). IIEE = integrated ice-edge error. Persistence is a strong baseline at one-week lead, so gains are modest in absolute terms."
    />
  );
}

export function Ml02Skill() {
  return (
    <Wrap
      path="/temperature/forecast/metrics"
      pick={allOf}
      deployed="cnn_unet_final"
      accent="#f4a261"
      metrics={[
        { key: "rmse_degC", label: "RMSE", units: "°C", better: "lower", digits: 2 },
        { key: "mae_degC", label: "MAE", units: "°C", better: "lower", digits: 2 },
        { key: "acc_pattern_mean", label: "Anomaly correlation", better: "higher", digits: 3 },
        { key: "msss_vs_climatology", label: "MSSS vs climatology", better: "higher", digits: 3 },
      ]}
      note="Held-out test period 2018–2025 (weekly issue dates), area-weighted south of 50° S. MSSS > 0 means more skilful than climatology."
    />
  );
}

export function Ml03Skill() {
  return (
    <Wrap
      path="/seaice-detection/detection/metrics"
      pick={(d) => d.metrics as Rows}
      deployed="final_model"
      accent="#c9e6f5"
      metrics={[
        { key: "miou", label: "Mean IoU", better: "higher", digits: 3 },
        { key: "dice_ice", label: "Dice (ice)", better: "higher", digits: 3 },
        { key: "precision_ice", label: "Precision (ice)", better: "higher", digits: 3 },
        { key: "recall_ice", label: "Recall (ice)", better: "higher", digits: 3 },
        { key: "ice_area_bias_pct", label: "Ice-area bias", units: "%", better: "zero", digits: 1 },
        { key: "edge_displacement_km_mean_scene_mean", label: "Edge displacement", units: "km", better: "lower", digits: 0 },
      ]}
      note="157 held-out scenes (2025–2026) scored against U.S. National Ice Center charts — agreement with expert charts, not independent pixel-level ground truth. The tree models (xgb, rf) score higher than the deployed U-Net here."
    />
  );
}

export function Ml04Skill() {
  return (
    <Wrap
      path="/api/ml04/metrics"
      pick={(d) => (d.test ?? d.validation) as Rows}
      deployed="lof_k20"
      accent="#e76f6a"
      metrics={[
        { key: "pr_auc", label: "PR-AUC", better: "higher", digits: 3 },
        { key: "roc_auc", label: "ROC-AUC", better: "higher", digits: 3 },
        { key: "recall_at_moderate", label: "Recall at moderate", better: "higher", digits: 3 },
        { key: "flag_rate_non_injected", label: "Flag rate (non-injected)", better: "lower", digits: 3 },
      ]}
      note="SYNTHETIC evaluation: scores measure how well each method recovers anomalies injected into 2018–2025 test data. No labelled real Antarctic anomalies exist, so this is not evidence of detecting real events."
    />
  );
}
