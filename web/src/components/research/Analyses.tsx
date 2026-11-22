"use client";
import { useMemo } from "react";
import { useApi } from "@/hooks/useApi";
import type { ClimateSeriesFile, SeriesPack } from "@/lib/api/types";
import { TimeSeries } from "@/components/charts/TimeSeries";
import { DataBadge, ErrorState, Loading } from "@/components/ui/primitives";
import { cn, fmt, titleCase } from "@/lib/utils";

/* All numbers on this component are computed in the browser from /data/climate_series.json. */

type XY = [number, number][];

/** Annual means of monthly anomalies (complete years only). */
function annual(p: SeriesPack): XY {
  const m = new Map<number, number[]>();
  p.t.forEach((t, i) => m.set(+t.slice(0, 4), [...(m.get(+t.slice(0, 4)) ?? []), p.anom[i]]));
  return [...m.entries()].filter(([, v]) => v.length === 12).map(([y, v]) => [y, v.reduce((a, b) => a + b, 0) / 12]);
}

/** Ordinary least-squares slope per decade with ±2 standard errors (not corrected for autocorrelation). */
function ols(xy: XY) {
  const n = xy.length;
  const mx = xy.reduce((a, [x]) => a + x, 0) / n;
  const my = xy.reduce((a, [, y]) => a + y, 0) / n;
  let sxy = 0;
  let sxx = 0;
  for (const [x, y] of xy) {
    sxy += (x - mx) * (y - my);
    sxx += (x - mx) ** 2;
  }
  const b = sxy / sxx;
  let sse = 0;
  for (const [x, y] of xy) sse += (y - my - b * (x - mx)) ** 2;
  const se = Math.sqrt(sse / (n - 2) / sxx);
  return { b: b * 10, ci: 2 * se * 10, n, y0: xy[0][0], y1: xy[n - 1][0] };
}

/** Correlation and RMS difference of monthly anomalies over common months. */
function agree(a: SeriesPack, b: SeriesPack) {
  const m = new Map(b.t.map((t, i) => [t, b.anom[i]]));
  const p = a.t.map((t, i) => [a.anom[i], m.get(t)] as const).filter((x): x is readonly [number, number] => x[1] != null);
  const n = p.length;
  const ma = p.reduce((s, x) => s + x[0], 0) / n;
  const mb = p.reduce((s, x) => s + x[1], 0) / n;
  let c = 0;
  let va = 0;
  let vb = 0;
  let d = 0;
  for (const [x, y] of p) {
    c += (x - ma) * (y - mb);
    va += (x - ma) ** 2;
    vb += (y - mb) ** 2;
    d += (x - y) ** 2;
  }
  const common = new Set(p.length ? a.t.filter((t) => m.has(t)) : []);
  return { n, r: c / Math.sqrt(va * vb), rmsd: Math.sqrt(d / n), first: [...common][0], last: [...common][common.size - 1] };
}

function useSeries() {
  return useApi<ClimateSeriesFile>("/data/climate_series.json", true);
}

/* ------------------------------------------------------------------------------------------------ regime shift */
export function RegimeShift() {
  const { data, error, loading } = useSeries();
  const r = useMemo(() => {
    const p = data?.series.era5_sea_ice_extent?.antarctic;
    if (!p) return null;
    const a = annual(p);
    const pre = a.filter(([y]) => y <= 2015);
    const post = a.filter(([y]) => y >= 2016);
    const mPre = pre.reduce((s, [, v]) => s + v, 0) / pre.length;
    const mPost = post.reduce((s, [, v]) => s + v, 0) / post.length;
    const below = post.filter(([, v]) => v < Math.min(...pre.map(([, x]) => x))).length;
    return { a, tPre: ols(pre), mPre, mPost, post, below, minPre: Math.min(...pre.map(([, x]) => x)) };
  }, [data]);
  if (loading) return <Loading label="Computing regimes" />;
  if (error || !r) return <ErrorState error={error} what="the sea-ice record" />;
  const t = r.a.map(([y]) => String(y));
  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_1.2fr] lg:items-center">
      <div>
        <div className="grid grid-cols-2 gap-6">
          <div className="border-t border-line pt-4">
            <p className="t-num text-4xl text-glacial">
              {r.tPre.b >= 0 ? "+" : ""}
              {fmt(r.tPre.b, 2)}
            </p>
            <p className="mt-2 text-sm text-muted">M km² per decade, 1979–2015 (± {fmt(r.tPre.ci, 2)})</p>
          </div>
          <div className="border-t border-line pt-4">
            <p className="t-num text-4xl text-alert">{fmt(r.mPost, 2)}</p>
            <p className="mt-2 text-sm text-muted">M km² mean anomaly, 2016–{r.post[r.post.length - 1][0]}</p>
          </div>
        </div>
        <p className="t-body mt-8">
          For 37 years Antarctic sea ice did the opposite of the Arctic: it expanded slightly, by about {fmt(r.tPre.b, 2)} million km² per decade. Then,
          in 2016, it dropped and has not recovered. The mean annual anomaly since 2016 is {fmt(r.mPost, 2)} million km², against {fmt(r.mPre, 2)} for
          1979–2015. In {r.below} of the {r.post.length} years since 2016 the annual mean was lower than in <em>any</em> year of 1979–2015.
        </p>
        <p className="t-body mt-4">
          A single straight line through 1979–2025 hides this: the gentle rise and the abrupt drop cancel, giving a near-zero long-term trend. That is why
          the trend table below must be read alongside this chart. Whether the post-2016 state is a new regime or a long excursion is an open scientific
          question; the record alone cannot answer it.
        </p>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <DataBadge type="reanalysis" />
          <span className="text-[0.6875rem] text-muted">
            ERA5 sea-ice cover ≥ 15 % south of 50° S, annual mean of monthly anomalies vs 1991–2020. Same pattern in the independent OSI SAF satellite record
            (Intelligence page).
          </span>
        </div>
      </div>
      <div>
        <p className="t-meta mb-3">Annual-mean extent anomaly and the two period means</p>
        <TimeSeries
          series={[
            { key: "a", name: "Annual anomaly", color: "#48c8e8", t, v: r.a.map(([, v]) => v), kind: "bar" },
            { key: "b", name: "Period mean", color: "#f4a261", t, v: r.a.map(([y]) => (y <= 2015 ? r.mPre : r.mPost)), dashed: true },
          ]}
          units="M km²"
          zeroLine
          height={300}
        />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------------------------------------ trend table */
const TREND_ROWS: { id: string; label: string; units: string; digits: number; type: string }[] = [
  { id: "era5_t2m", label: "2 m air temperature · ERA5", units: "°C", digits: 3, type: "reanalysis" },
  { id: "merra2_t2m", label: "2 m air temperature · MERRA-2", units: "°C", digits: 3, type: "reanalysis" },
  { id: "era5_t850", label: "850 hPa temperature · ERA5", units: "°C", digits: 3, type: "reanalysis" },
  { id: "era5_msl", label: "Sea-level pressure · ERA5", units: "hPa", digits: 2, type: "reanalysis" },
  { id: "merra2_slp", label: "Sea-level pressure · MERRA-2", units: "hPa", digits: 2, type: "reanalysis" },
  { id: "era5_z500", label: "500 hPa height · ERA5", units: "dam", digits: 2, type: "reanalysis" },
  { id: "era5_wind10", label: "10 m wind speed · ERA5", units: "m/s", digits: 3, type: "reanalysis" },
  { id: "era5_tp", label: "Precipitation · ERA5", units: "mm/day", digits: 3, type: "reanalysis" },
  { id: "era5_sf", label: "Snowfall · ERA5", units: "mm/day", digits: 3, type: "reanalysis" },
  { id: "era5_tcc", label: "Cloud cover · ERA5", units: "%", digits: 2, type: "reanalysis" },
  { id: "era5_sea_ice_extent", label: "Sea-ice extent · ERA5", units: "M km²", digits: 3, type: "reanalysis" },
  { id: "osisaf_sea_ice_extent", label: "Sea-ice extent · OSI SAF", units: "M km²", digits: 3, type: "observation" },
  { id: "glorys_sea_ice_thickness", label: "Sea-ice thickness · GLORYS12", units: "m", digits: 3, type: "model_reanalysis" },
  { id: "era5_sst", label: "Sea-surface temperature · ERA5", units: "°C", digits: 3, type: "reanalysis" },
  { id: "multiobs_sst", label: "Near-surface ocean temp. · MULTIOBS", units: "°C", digits: 3, type: "observation" },
  { id: "multiobs_mld", label: "Mixed-layer depth · MULTIOBS", units: "m", digits: 2, type: "observation" },
];

export function TrendTable() {
  const { data, error, loading } = useSeries();
  const rows = useMemo(
    () =>
      data
        ? TREND_ROWS.filter((r) => data.series[r.id]).map((r) => {
            const a = annual(data.series[r.id].antarctic);
            return { ...r, ...ols(a), domain: data.series[r.id].domain ?? "" };
          })
        : [],
    [data],
  );
  if (loading) return <Loading label="Fitting trends" />;
  if (error) return <ErrorState error={error} what="the climate record" />;
  return (
    <div>
      <div className="overflow-x-auto" data-lenis-prevent>
        <table className="w-full min-w-[46rem] border-collapse text-[0.8125rem]">
          <thead>
            <tr className="border-b border-line-strong text-left font-mono text-[0.625rem] uppercase tracking-[0.12em] text-muted">
              <th className="py-3 pr-4 font-normal">Variable · dataset</th>
              <th className="px-3 py-3 font-normal">Domain</th>
              <th className="px-3 py-3 font-normal">Years</th>
              <th className="px-3 py-3 text-right font-normal">Trend / decade</th>
              <th className="px-3 py-3 text-right font-normal">± 2 SE</th>
              <th className="px-3 py-3 font-normal">Reading</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const clear = Math.abs(r.b) > r.ci;
              return (
                <tr key={r.id} className="border-b border-line">
                  <td className="py-3 pr-4 text-glacial">
                    {r.label}
                    <span className="ml-2 inline-block align-middle">
                      <DataBadge type={r.type} />
                    </span>
                  </td>
                  <td className="px-3 py-3 font-mono text-[0.75rem] text-muted">{r.domain.split(" (")[0].replace("-", "–")}</td>
                  <td className="whitespace-nowrap px-3 py-3 font-mono text-[0.75rem] text-silver">
                    {r.y0}–{r.y1}
                  </td>
                  <td className={cn("whitespace-nowrap px-3 py-3 text-right font-mono", clear ? (r.b > 0 ? "text-warn" : "text-cyan") : "text-silver")}>
                    {r.b >= 0 ? "+" : ""}
                    {fmt(r.b, r.digits)} {r.units}
                  </td>
                  <td className="px-3 py-3 text-right font-mono text-muted">{fmt(r.ci, r.digits)}</td>
                  <td className="px-3 py-3 text-[0.75rem] text-silver">{clear ? (r.b > 0 ? "Increase, clear of zero" : "Decrease, clear of zero") : "Not distinguishable from zero"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-4 text-[0.75rem] leading-relaxed text-muted">
        Ordinary least-squares slope through annual means of monthly anomalies (complete years only). ± 2 SE is a rough 95 % range that ignores
        year-to-year autocorrelation, so it is optimistic: a trend that is only just “clear of zero” should be treated as uncertain. Trends depend on the
        period; records that start later are not directly comparable with 1979 onwards.
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------------------------------------ agreement */
const PAIRS: { a: string; b: string; what: string; la: string; lb: string; units: string; digits: number; note: string }[] = [
  { a: "era5_sea_ice_extent", b: "osisaf_sea_ice_extent", what: "Sea-ice extent", la: "ERA5", lb: "OSI SAF (satellite)", units: "M km²", digits: 2,
    note: "ERA5 prescribes its sea ice from OSI SAF products, so close agreement is expected; it confirms the processing chain rather than providing independent evidence." },
  { a: "era5_msl", b: "merra2_slp", what: "Sea-level pressure", la: "ERA5", lb: "MERRA-2", units: "hPa", digits: 2,
    note: "Pressure is well constrained by surface and satellite observations, so two independent reanalyses agree closely on its month-to-month variations." },
  { a: "era5_sst", b: "multiobs_sst", what: "Ocean surface temperature", la: "ERA5", lb: "MULTIOBS", units: "°C", digits: 3,
    note: "Different domains and depths (ERA5 skin SST 50–90° S vs MULTIOBS near-surface 50–82° S), so the RMS difference partly reflects definition, not error." },
  { a: "era5_t2m", b: "merra2_t2m", what: "2 m air temperature", la: "ERA5", lb: "MERRA-2", units: "°C", digits: 2,
    note: "The weakest agreement of the four. Over the ice sheet there are very few surface stations, and near-surface temperature depends strongly on each model's treatment of the stable boundary layer." },
];

export function Agreement() {
  const { data, error, loading } = useSeries();
  const rows = useMemo(
    () =>
      data
        ? PAIRS.filter((p) => data.series[p.a] && data.series[p.b]).map((p) => {
            const A = data.series[p.a].antarctic;
            const B = data.series[p.b].antarctic;
            const g = agree(A, B);
            const lo = Math.max(+A.t[0].slice(0, 4), +B.t[0].slice(0, 4));
            const hi = Math.min(+A.t[A.t.length - 1].slice(0, 4), +B.t[B.t.length - 1].slice(0, 4));
            const within = (x: XY) => x.filter(([y]) => y >= lo && y <= hi);
            return { ...p, ...g, ta: ols(within(annual(A))), tb: ols(within(annual(B))) };
          })
        : [],
    [data],
  );
  if (loading) return <Loading label="Comparing records" />;
  if (error) return <ErrorState error={error} what="the climate record" />;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {rows.map((r) => {
        const flip = Math.sign(r.ta.b) !== Math.sign(r.tb.b);
        return (
          <article key={r.what} className="rounded-[var(--radius-lg)] border border-line bg-midnight/60 p-6">
            <p className="t-meta">
              {r.la} <span className="text-ice-dim">vs</span> {r.lb}
            </p>
            <h3 className="mt-3 font-display text-xl text-glacial">{r.what}</h3>
            <div className="mt-5 grid grid-cols-3 gap-4">
              <div>
                <p className={cn("t-num text-3xl", r.r >= 0.9 ? "text-cyan" : r.r >= 0.8 ? "text-glacial" : "text-warn")}>{fmt(r.r, 2)}</p>
                <p className="mt-1 text-[0.6875rem] text-muted">correlation of monthly anomalies</p>
              </div>
              <div>
                <p className="t-num text-3xl text-glacial">{fmt(r.rmsd, r.digits)}</p>
                <p className="mt-1 text-[0.6875rem] text-muted">RMS difference, {r.units}</p>
              </div>
              <div>
                <p className="t-num text-3xl text-glacial">{r.n}</p>
                <p className="mt-1 text-[0.6875rem] text-muted">common months</p>
              </div>
            </div>
            <div className={cn("mt-5 rounded border px-3 py-2 font-mono text-[0.75rem]", flip ? "border-alert/40 bg-alert/5 text-glacial" : "border-line text-silver")}>
              Trend {r.ta.y0}–{r.ta.y1}: {r.la} {r.ta.b >= 0 ? "+" : ""}
              {fmt(r.ta.b, r.digits + 1)} · {r.lb.split(" ")[0]} {r.tb.b >= 0 ? "+" : ""}
              {fmt(r.tb.b, r.digits + 1)} {r.units}/decade{flip && " — opposite signs"}
            </div>
            <p className="mt-4 text-[0.8125rem] leading-relaxed text-silver">{r.note}</p>
          </article>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------------------------------------ sectors */
const SECTOR_VARS: { id: string; label: string; units: string; digits: number; good: "neg" | "pos" | "none" }[] = [
  { id: "era5_sea_ice_extent", label: "Sea-ice extent", units: "M km²", digits: 2, good: "pos" },
  { id: "era5_t2m", label: "2 m temperature", units: "°C", digits: 2, good: "none" },
  { id: "era5_msl", label: "Sea-level pressure", units: "hPa", digits: 2, good: "none" },
  { id: "era5_wind10", label: "10 m wind speed", units: "m/s", digits: 2, good: "none" },
];
const SECTOR_NAMES = ["weddell", "indian", "pacific", "ross", "bellingshausen_amundsen"];

export function Sectors() {
  const { data, error, loading } = useSeries();
  const res = useMemo(() => {
    if (!data) return null;
    const rows = SECTOR_VARS.filter((v) => data.series[v.id]?.sectors).map((v) => {
      const sec = data.series[v.id].sectors!;
      const vals = SECTOR_NAMES.map((n) => {
        const a = sec[n]?.anom.slice(-36) ?? [];
        return a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;
      });
      return { ...v, vals, max: Math.max(...vals.map((x) => Math.abs(x ?? 0))) };
    });
    const t = data.series.era5_t2m.sectors?.weddell?.t ?? data.series.era5_t2m.antarctic.t;
    return { rows, from: t[t.length - 36], to: t[t.length - 1] };
  }, [data]);
  if (loading) return <Loading label="Computing sectors" />;
  if (error || !res) return <ErrorState error={error} what="the sector records" />;
  return (
    <div>
      <div className="overflow-x-auto" data-lenis-prevent>
        <table className="w-full min-w-[44rem] border-collapse text-[0.8125rem]">
          <thead>
            <tr className="border-b border-line-strong text-left font-mono text-[0.625rem] uppercase tracking-[0.12em] text-muted">
              <th className="py-3 pr-4 font-normal">Mean anomaly vs 1991–2020</th>
              {SECTOR_NAMES.map((n) => (
                <th key={n} className="px-3 py-3 text-right font-normal">
                  {titleCase(n).replace("Bellingshausen Amundsen", "Bell.–Amundsen")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {res.rows.map((r) => (
              <tr key={r.id} className="border-b border-line">
                <td className="py-3 pr-4 text-glacial">
                  {r.label} <span className="text-muted">({r.units})</span>
                </td>
                {r.vals.map((v, i) => {
                  const k = v == null || r.max === 0 ? 0 : Math.abs(v) / r.max;
                  const col = v == null ? "transparent" : v < 0 ? `rgba(72,200,232,${0.08 + 0.32 * k})` : `rgba(244,162,97,${0.08 + 0.32 * k})`;
                  return (
                    <td key={i} className="px-3 py-3 text-right font-mono text-glacial" style={{ background: col }}>
                      {v == null ? "—" : `${v >= 0 ? "+" : ""}${fmt(v, r.digits)}`}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-4 text-[0.75rem] leading-relaxed text-muted">
        Mean of monthly ERA5 anomalies over the latest 36 months ({res.from} → {res.to}) in the five NSIDC longitude sectors, 60–90° S (sea ice: 50–90° S).
        Shading is relative within each row. Sector boundaries: Weddell 60° W–20° E, Indian 20–90° E, Pacific 90–160° E, Ross 160° E–130° W,
        Bellingshausen–Amundsen 130–60° W.
      </p>
    </div>
  );
}
