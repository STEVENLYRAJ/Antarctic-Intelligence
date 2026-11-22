"use client";
import { useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "@/hooks/useApi";
import type { DailyRecord, DailySeriesFile } from "@/lib/api/types";
import { DataBadge, ErrorState, Loading } from "@/components/ui/primitives";
import { cn, fmt } from "@/lib/utils";

const MONTH_START = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const HILITE = ["#e76f6a", "#f4a261", "#48c8e8", "#7ed3b2", "#c9e6f5"];

/** Day-of-year chart: every year vs the reference envelope (min–max and 10–90th percentile), highlighted years on top. */
function RecordChart({ rec, digits, defaults }: { rec: DailyRecord; digits: number; defaults: string[] }) {
  const years = Object.keys(rec.years).sort();
  const [picked, setPicked] = useState<string[]>(defaults.filter((y) => years.includes(y)));
  const [ghosts, setGhosts] = useState(true);
  const data = useMemo(
    () =>
      Array.from({ length: 365 }, (_, d) => {
        const row: Record<string, number | null | [number, number] | null> = {
          d: d + 1,
          mean: rec.clim.mean[d],
          range: rec.clim.min[d] != null && rec.clim.max[d] != null ? [rec.clim.min[d]!, rec.clim.max[d]!] : null,
          p: rec.clim.p10[d] != null && rec.clim.p90[d] != null ? [rec.clim.p10[d]!, rec.clim.p90[d]!] : null,
        };
        for (const y of years) row[y] = rec.years[y][d];
        return row;
      }),
    [rec, years],
  );
  const toggle = (y: string) => setPicked((p) => (p.includes(y) ? p.filter((x) => x !== y) : p.length >= 5 ? [...p.slice(1), y] : [...p, y]));
  const last = years[years.length - 1];
  const lastVals = rec.years[last].map((v, i) => [i, v] as const).filter(([, v]) => v != null);
  const lastPt = lastVals[lastVals.length - 1];
  const dev = lastPt && rec.clim.mean[lastPt[0]] != null ? (lastPt[1]! - rec.clim.mean[lastPt[0]]!) : null;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <DataBadge type={rec.data_type} />
        <span className="font-mono text-[0.6875rem] text-muted">
          {rec.units} · reference {rec.clim.base}
        </span>
        {lastPt && dev != null && (
          <span className="ml-auto font-mono text-[0.6875rem] text-silver">
            Latest {last}, day {lastPt[0] + 1}: <span className="text-glacial">{fmt(lastPt[1]!, digits)}</span> ({dev >= 0 ? "+" : ""}
            {fmt(dev, digits)} vs {rec.clim.base} mean)
          </span>
        )}
      </div>
      <div className="mt-5 h-[23.75rem] w-full">
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
            <CartesianGrid stroke="rgba(141,220,244,0.07)" vertical={false} />
            <XAxis dataKey="d" type="number" domain={[1, 365]} ticks={MONTH_START} tickFormatter={(d) => MONTHS[MONTH_START.indexOf(d)] ?? ""} stroke="#6f8094" fontSize={11} tickLine={false} />
            <YAxis stroke="#6f8094" fontSize={11} tickLine={false} axisLine={false} domain={["auto", "auto"]} tickFormatter={(v) => fmt(v, 0)} />
            <Tooltip
              contentStyle={{ background: "rgba(5,8,13,0.95)", border: "1px solid rgba(141,220,244,0.22)", borderRadius: 8, fontSize: 12 }}
              labelFormatter={(d) => {
                const m = MONTH_START.filter((s) => s <= Number(d)).length - 1;
                return `${MONTHS[m]} ${Number(d) - MONTH_START[m] + 1} (day ${d})`;
              }}
              formatter={(v: unknown, n) => (Array.isArray(v) ? [`${fmt(v[0], digits)} – ${fmt(v[1], digits)}`, n === "range" ? `${rec.clim.base} min–max` : `${rec.clim.base} 10–90 %`] : [fmt(v as number, digits), String(n)])}
              itemSorter={(i) => -(typeof i.value === "number" ? i.value : 0)}
            />
            <Area dataKey="range" stroke="none" fill="rgba(141,220,244,0.07)" isAnimationActive={false} name="range" />
            <Area dataKey="p" stroke="none" fill="rgba(141,220,244,0.14)" isAnimationActive={false} name="p" />
            {ghosts &&
              years
                .filter((y) => !picked.includes(y))
                .map((y) => <Line key={y} dataKey={y} stroke="rgba(139,155,170,0.18)" strokeWidth={0.8} dot={false} isAnimationActive={false} legendType="none" tooltipType="none" connectNulls />)}
            <Line dataKey="mean" stroke="#eaf5fc" strokeDasharray="4 4" strokeWidth={1.2} dot={false} isAnimationActive={false} name={`${rec.clim.base} mean`} connectNulls />
            {picked.map((y, i) => (
              <Line key={y} dataKey={y} stroke={HILITE[i % HILITE.length]} strokeWidth={2} dot={false} isAnimationActive={false} name={y} connectNulls />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-1.5">
        <span className="mr-2 text-[0.6875rem] text-muted">Highlight up to 5 years:</span>
        {years.map((y) => {
          const i = picked.indexOf(y);
          return (
            <button
              key={y}
              onClick={() => toggle(y)}
              aria-pressed={i >= 0}
              className={cn("rounded px-1.5 py-0.5 font-mono text-[0.6563rem] transition-colors", i >= 0 ? "text-polar" : "text-muted hover:text-glacial")}
              style={i >= 0 ? { background: HILITE[i % HILITE.length] } : undefined}
            >
              {y}
            </button>
          );
        })}
        <label className="ml-auto flex items-center gap-2 text-[0.6875rem] text-muted">
          <input type="checkbox" checked={ghosts} onChange={(e) => setGhosts(e.target.checked)} className="accent-[var(--cyan)]" /> show all other years
        </label>
      </div>
      <p className="mt-3 text-[0.75rem] leading-relaxed text-muted">
        {rec.title}. {rec.source}. Shaded: {rec.clim.base} minimum–maximum (light) and 10–90th percentile (darker); dashed: {rec.clim.base} mean. {rec.note}
      </p>
    </div>
  );
}

type TabKey = "sea_ice_extent" | "t2m" | "era5_t850" | "era5_z500" | "era5_msl" | "era5_wind10";
const TABS: { k: TabKey; label: string; digits: number; defaults: string[] }[] = [
  { k: "sea_ice_extent", label: "Sea-ice extent", digits: 2, defaults: ["2014", "2023", "2024", "2025"] },
  { k: "t2m", label: "Surface temperature", digits: 1, defaults: ["2023", "2025", "2026"] },
  { k: "era5_t850", label: "850 hPa temperature", digits: 1, defaults: ["2019", "2025", "2026"] },
  { k: "era5_z500", label: "500 hPa height", digits: 1, defaults: ["2019", "2025", "2026"] },
  { k: "era5_msl", label: "Sea-level pressure", digits: 1, defaults: ["2016", "2025", "2026"] },
  { k: "era5_wind10", label: "10 m wind", digits: 2, defaults: ["2019", "2025", "2026"] },
];

function span(rec?: DailyRecord) {
  if (!rec) return "";
  const ys = Object.keys(rec.years).sort();
  return `${ys[0]}–${ys[ys.length - 1]}`;
}

export function DailyRecords() {
  const { data, error, loading } = useApi<DailySeriesFile>("/data/daily_series.json", true);
  const [tab, setTab] = useState<TabKey>("sea_ice_extent");
  if (loading) return <Loading label="Loading daily records" />;
  if (error || !data) return <ErrorState error={error} what="daily records" />;
  const cfg = TABS.find((t) => t.k === tab)!;
  const rec = data[tab];
  return (
    <div>
      <div className="flex flex-wrap gap-2" role="tablist">
        {TABS.filter((t) => !!data[t.k]).map(({ k, label }) => [k, `${label} · ${span(data[k])}`, true] as const).map(([k, l, ok]) => (
          <button
            key={k}
            role="tab"
            aria-selected={tab === k}
            disabled={!ok}
            onClick={() => setTab(k)}
            className={cn("rounded-full border px-4 py-2 text-[0.8125rem] transition-colors disabled:opacity-40", tab === k ? "border-cyan bg-cyan/10 text-cyan" : "border-line text-silver hover:border-line-strong")}
          >
            {l}
          </button>
        ))}
      </div>
      <div className="mt-6">
        {rec ? (
          <RecordChart key={tab} rec={rec} digits={cfg.digits} defaults={cfg.defaults} />
        ) : (
          <p className="text-sm text-muted">This record has not been generated.</p>
        )}
      </div>
    </div>
  );
}
