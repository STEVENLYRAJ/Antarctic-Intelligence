"use client";
import { useMemo } from "react";
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Brush,
  type TooltipProps,
} from "recharts";

export interface Series {
  key: string;
  name: string;
  color: string;
  t: string[];
  v: (number | null)[];
  kind?: "line" | "area" | "bar";
  dashed?: boolean;
}

interface Props {
  series: Series[];
  units: string;
  height?: number;
  zeroLine?: boolean;
  brush?: boolean;
  digits?: number;
  /** Colour bars by sign (anomaly mode for a single bar series). */
  signed?: boolean;
  yDomain?: [number | "auto", number | "auto"];
}

/** Merges series on their time key and renders a responsive, accessible chart. */
export function TimeSeries({ series, units, height = 320, zeroLine = false, brush = false, digits = 2, signed = false, yDomain }: Props) {
  const data = useMemo(() => {
    const m = new Map<string, Record<string, number | string | null>>();
    for (const s of series) {
      s.t.forEach((t, i) => {
        const row = m.get(t) ?? { t };
        row[s.key] = s.v[i];
        m.set(t, row);
      });
    }
    const rows = [...m.values()];
    // Only date-like keys (YYYY…) are sorted; categorical keys (e.g. month names) keep their given order.
    return /^\d{4}/.test(String(rows[0]?.t ?? "")) ? rows.sort((a, b) => String(a.t).localeCompare(String(b.t))) : rows;
  }, [series]);

  const Tip = ({ active, payload, label }: TooltipProps<number, string>) => {
    if (!active || !payload?.length) return null;
    return (
      <div className="rounded border border-line-strong bg-polar/95 px-3 py-2 font-mono text-[0.6875rem] shadow-xl">
        <p className="mb-1 text-muted">{label}</p>
        {payload.map((p) => (
          <p key={p.dataKey as string} style={{ color: p.color }}>
            {p.name}: {typeof p.value === "number" ? p.value.toFixed(digits) : "—"} {units}
          </p>
        ))}
      </div>
    );
  };

  return (
    <div style={{ height }} className="w-full" role="img" aria-label={`Time series chart (${series.map((s) => s.name).join(", ")}) in ${units}`}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="rgba(173,214,255,0.07)" vertical={false} />
          <XAxis dataKey="t" tick={{ fill: "#6f8094", fontSize: 10, fontFamily: "var(--font-mono)" }} tickLine={false} axisLine={{ stroke: "rgba(173,214,255,0.15)" }} minTickGap={40} />
          <YAxis
            tick={{ fill: "#6f8094", fontSize: 10, fontFamily: "var(--font-mono)" }}
            tickLine={false}
            axisLine={false}
            width={48}
            domain={yDomain ?? ["auto", "auto"]}
            tickFormatter={(v: number) => (Math.abs(v) >= 1000 ? v.toExponential(1) : String(Math.round(v * 100) / 100))}
          />
          <Tooltip content={<Tip />} cursor={{ stroke: "rgba(94,226,255,0.35)" }} />
          {zeroLine && <ReferenceLine y={0} stroke="rgba(238,246,255,0.35)" />}
          {series.map((s) =>
            s.kind === "bar" ? (
              <Bar
                key={s.key}
                dataKey={s.key}
                name={s.name}
                fill={s.color}
                isAnimationActive={false}
                shape={
                  signed
                    ? (props: unknown) => {
                        const p = props as { x: number; y: number; width: number; height: number; value: number };
                        const h = Math.abs(p.height);
                        const y = p.height < 0 ? p.y + p.height : p.y;
                        return <rect x={p.x} y={y} width={Math.max(p.width, 1)} height={h} fill={p.value >= 0 ? "#e76f6a" : "#48c8e8"} />;
                      }
                    : undefined
                }
              />
            ) : s.kind === "area" ? (
              <Area key={s.key} dataKey={s.key} name={s.name} stroke={s.color} fill={s.color} fillOpacity={0.12} strokeWidth={1.4} dot={false} isAnimationActive={false} connectNulls />
            ) : (
              <Line key={s.key} dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={1.5} dot={false} strokeDasharray={s.dashed ? "4 3" : undefined} isAnimationActive={false} connectNulls />
            ),
          )}
          {brush && <Brush dataKey="t" height={22} stroke="#2a9fc0" fill="#081321" travellerWidth={8} tickFormatter={() => ""} />}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
