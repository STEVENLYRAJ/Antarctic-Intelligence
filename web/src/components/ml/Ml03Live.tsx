"use client";
import { useState } from "react";
import { useApi } from "@/hooks/useApi";
import type { ModelInfo, SarMetrics, SarWeekly } from "@/lib/api/types";
import { DataBadge, ErrorState, KV, Loading, Stat } from "@/components/ui/primitives";
import { MetricsTable } from "./MetricsTable";
import { CompareSlider } from "./CompareSlider";
import { cn, fmt, pct } from "@/lib/utils";

interface SarExample {
  scene_id: string;
  acquired: string;
  model_version: string;
  data_type: string;
  fractions: { ice: number; water: number; uncertain: number };
  nominal_ice_area_km2: number;
  width: number;
  height: number;
  files: { sar: string; class: string; prob: string };
}

export function Ml03Summary() {
  const { data: w, error, loading } = useApi<SarWeekly>("/seaice-detection/detection/weekly");
  if (loading) return <Loading />;
  if (error || !w) return <ErrorState error={error} what="the weekly composite" />;
  const tot = w.cells_weekly_ice + w.cells_weekly_water + w.cells_variable;
  return (
    <div className="rounded-[var(--radius)] border border-dashed border-warn/50 bg-polar/60 p-6 backdrop-blur">
      <div className="flex flex-wrap items-center gap-3">
        <DataBadge type="model_prediction" />
        <span className="font-mono text-[11px] text-muted">
          Week {w.week_start} → {w.week_end}
        </span>
      </div>
      <div className="mt-6 grid grid-cols-2 gap-6">
        <Stat label="Scenes classified" value={fmt(w.n_acquisitions, 0)} note="Sentinel-1 EW, HH" />
        <Stat label="Area observed" value={fmt(w.observed_area_km2_nominal / 1e6, 1)} unit="M km²" note="Nominal, 2 km composite grid" />
        <Stat label="Ice in every view" value={pct(w.cells_weekly_ice / tot)} note="Share of observed cells" />
        <Stat label="Changed during week" value={pct(w.cells_variable / tot)} note="Ice in some views, water in others" />
      </div>
      <p className="mt-6 font-mono text-[10.5px] text-muted">{w.model_version}</p>
    </div>
  );
}

export function Ml03Compare() {
  const { data, error, loading } = useApi<SarExample[]>("/data/sar/index.json", true);
  const [i, setI] = useState(0);
  const [mode, setMode] = useState<"class" | "prob">("class");
  if (loading) return <Loading />;
  if (error || !data?.length) return <ErrorState error={error} what="SAR examples" />;
  const s = data[i];
  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_300px]">
      <CompareSlider
        before={s.files.sar}
        after={mode === "class" ? s.files.class : s.files.prob}
        beforeLabel="Sentinel-1 σ⁰ HH (observation)"
        afterLabel={mode === "class" ? "ML-03 classes (prediction)" : "ML-03 ice probability"}
        aspect={s.width / s.height}
      />
      <div>
        <p className="t-meta mb-3">Scene</p>
        <div className="space-y-1">
          {data.map((d, k) => (
            <button
              key={d.scene_id}
              onClick={() => setI(k)}
              className={cn("block w-full rounded px-3 py-2 text-left font-mono text-[11px]", k === i ? "bg-navy-2 text-glacial" : "text-muted hover:bg-navy hover:text-glacial")}
            >
              {d.scene_id.slice(0, 3)} · {d.acquired.slice(0, 16).replace("T", " ")} UTC
            </button>
          ))}
        </div>
        <div className="mt-6 flex gap-2">
          {(["class", "prob"] as const).map((m) => (
            <button key={m} onClick={() => setMode(m)} className={cn("rounded-full border px-3 py-1.5 text-[12px]", mode === m ? "border-cyan text-cyan" : "border-line text-silver hover:text-glacial")}>
              {m === "class" ? "Classes" : "Probability"}
            </button>
          ))}
        </div>
        <div className="mt-6 space-y-2 text-[13px]">
          {[
            ["Sea ice", s.fractions.ice, "#eaf5fc"],
            ["Open water", s.fractions.water, "#0a2452"],
            ["Uncertain (p 0.35–0.65)", s.fractions.uncertain, "#f4a261"],
          ].map(([l, v, c]) => (
            <div key={l as string} className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-silver">
                <span className="h-3 w-3 rounded-sm border border-line" style={{ background: c as string }} />
                {l}
              </span>
              <span className="t-num text-glacial">{pct(v as number)}</span>
            </div>
          ))}
        </div>
        <p className="mt-6 text-[11px] leading-relaxed text-muted">
          Both images are on the identical 400 m EPSG:3031 grid produced by the ML-03 pipeline. Drag the handle (or use ← →) to compare the radar backscatter
          with the model output.
        </p>
      </div>
    </div>
  );
}

const NAMES: Record<string, string> = {
  final_model: "Deployed model (final)",
  unet_bce_dice: "U-Net, BCE + Dice",
  unet_bce: "U-Net, BCE",
  xgb: "XGBoost (pixel features)",
  rf: "Random forest (pixel features)",
  threshold: "σ⁰ threshold baseline",
};

export function Ml03Metrics() {
  const { data, error, loading } = useApi<SarMetrics>("/seaice-detection/detection/metrics");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorState error={error} what="evaluation metrics" />;
  return (
    <div>
      <p className="mb-6 text-sm text-silver">
        Test split · {data.n_scenes} scenes · charts {data.charts[0]} → {data.charts[1]} · reference: {data.label_source}.
      </p>
      <MetricsTable
        rows={data.metrics}
        names={NAMES}
        highlight={["final_model"]}
        cols={[
          { key: "miou", label: "mIoU", digits: 3, better: "higher" },
          { key: "f1_ice", label: "F1 ice", digits: 3, better: "higher" },
          { key: "f1_water", label: "F1 water", digits: 3, better: "higher" },
          { key: "overall_accuracy", label: "Accuracy", digits: 3, better: "higher" },
          { key: "ice_area_bias_pct", label: "Ice-area bias", unit: "%", digits: 1, better: "abs-lower" },
        ]}
      />
      <p className="mt-4 max-w-3xl text-[13px] leading-relaxed text-silver">
        On this test set the pixel-feature tree models score slightly higher than the deployed U-Net on overlap metrics. The scores measure agreement with
        chart-scale USNIC analyses, which smooth the ice edge, so they favour smooth classifiers and are not independent ground truth.
      </p>
    </div>
  );
}

export function Ml03Model() {
  const { data, error, loading } = useApi<ModelInfo>("/seaice-detection/model/info");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorState error={error} what="model information" />;
  const d = data as ModelInfo & { kind: string; selected_from: string; channels: string[]; architecture: Record<string, number>; loss: string; input: string; labels: string; trained_utc: string };
  return (
    <KV
      rows={[
        ["Model version", d.model_version],
        ["Architecture", `${d.kind} (${d.selected_from}) · base ${d.architecture.base}, depth ${d.architecture.depth}, dropout ${d.architecture.dropout}`],
        ["Input channels", d.channels.join(", ")],
        ["Loss", d.loss],
        ["Input", d.input],
        ["Labels", d.labels],
        ["Trained", d.trained_utc?.slice(0, 16).replace("T", " ") + " UTC"],
      ]}
    />
  );
}
