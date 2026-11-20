import { cn, fmt } from "@/lib/utils";

export interface MetricCol {
  key: string;
  label: string;
  digits?: number;
  better: "lower" | "higher" | "abs-lower";
  scale?: number;
  unit?: string;
}

/**
 * Comparison of candidate / baseline models exactly as returned by the API. The best value per column is marked;
 * nothing is re-computed in the browser.
 */
export function MetricsTable({
  rows,
  cols,
  highlight,
  names = {},
}: {
  rows: Record<string, Record<string, number | null | undefined>>;
  cols: MetricCol[];
  highlight?: string[];
  names?: Record<string, string>;
}) {
  const keys = Object.keys(rows);
  const best: Record<string, string | null> = {};
  for (const c of cols) {
    let b: string | null = null;
    let bv = Infinity;
    for (const k of keys) {
      const v = rows[k][c.key];
      if (v == null || !Number.isFinite(v)) continue;
      const s = c.better === "higher" ? -v : c.better === "abs-lower" ? Math.abs(v) : v;
      if (s < bv) {
        bv = s;
        b = k;
      }
    }
    best[c.key] = b;
  }
  return (
    <div className="overflow-x-auto" data-lenis-prevent>
      <table className="w-full min-w-[640px] border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line-strong text-left">
            <th className="py-3 pr-4 font-mono text-[10px] font-normal uppercase tracking-[0.14em] text-muted">Model</th>
            {cols.map((c) => (
              <th key={c.key} className="px-3 py-3 text-right font-mono text-[10px] font-normal uppercase tracking-[0.14em] text-muted">
                {c.label}
                <span className="ml-1 text-ice-dim">{c.better === "higher" ? "↑" : "↓"}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => (
            <tr key={k} className={cn("border-b border-line", highlight?.includes(k) && "bg-navy-2/60")}>
              <td className="py-2.5 pr-4 text-glacial">
                {names[k] ?? k.replace(/_/g, " ")}
                {highlight?.includes(k) && <span className="ml-2 font-mono text-[9px] uppercase tracking-[0.14em] text-cyan">deployed</span>}
              </td>
              {cols.map((c) => {
                const v = rows[k][c.key];
                return (
                  <td key={c.key} className={cn("t-num px-3 py-2.5 text-right", best[c.key] === k ? "text-cyan" : "text-silver")}>
                    {v == null ? "—" : fmt(v * (c.scale ?? 1), c.digits ?? 3)}
                    {v != null && c.unit ? <span className="ml-0.5 text-[10px] text-muted">{c.unit}</span> : null}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 font-mono text-[10px] text-muted">Cyan = best value in column. Values are returned by the API from the frozen evaluation files.</p>
    </div>
  );
}
