"use client";
import { useMemo, useState } from "react";
import { useApi } from "@/hooks/useApi";
import type { ClimateSeriesFile, SeriesPack } from "@/lib/api/types";
import { TimeSeries, type Series } from "@/components/charts/TimeSeries";
import { DataBadge, ErrorState, Loading, Stat } from "@/components/ui/primitives";
import { cn, fmt, titleCase } from "@/lib/utils";

const VARIABLES = [
  { id: "era5_sea_ice_extent", label: "Sea-ice extent", digits: 2, compare: "osisaf_sea_ice_extent", type: "reanalysis" },
  { id: "era5_t2m", label: "Temperature", digits: 2, compare: "merra2_t2m", type: "reanalysis" },
  { id: "era5_msl", label: "Sea-level pressure", digits: 1, compare: "merra2_slp", type: "reanalysis" },
  { id: "era5_wind10", label: "Wind (10 m)", digits: 2, type: "reanalysis" },
  { id: "era5_tp", label: "Precipitation", digits: 2, type: "reanalysis" },
  { id: "era5_sf", label: "Snowfall", digits: 2, type: "reanalysis" },
  { id: "era5_sst", label: "Sea-surface temp.", digits: 2, type: "reanalysis" },
  { id: "glorys_sea_ice_thickness", label: "Ice thickness", digits: 2, type: "model_reanalysis" },
  { id: "ifremer_drift_speed", label: "Ice drift speed", digits: 2, type: "observation" },
  { id: "multiobs_sst", label: "Ocean temperature", digits: 2, type: "observation" },
  { id: "multiobs_mld", label: "Mixed-layer depth", digits: 1, type: "observation" },
] as const;

const METHOD: Record<string, string> = {
  era5_sea_ice_extent: "Total area of 0.25° cells with concentration ≥ 15 %, south of 50° S.",
  glorys_sea_ice_thickness: "Mean thickness over cells with concentration ≥ 15 %; model reanalysis with data assimilation.",
  ifremer_drift_speed: "Monthly mean of daily 3-day drift speeds over ice-covered cells; summer melt degrades passive-microwave drift.",
  multiobs_sst: "Area-weighted mean near-surface temperature of the observation-based reconstruction; under-ice values are sparse.",
  multiobs_mld: "Area-weighted mean mixed-layer depth from the observation-based reconstruction.",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const SECTOR_COLORS: Record<string, string> = { weddell: "#48c8e8", indian: "#f4a261", pacific: "#7ed3b2", ross: "#b9a3ff", bellingshausen_amundsen: "#e76f6a" };

function slice(p: SeriesPack, from: number, to: number): SeriesPack {
  const idx = p.t.map((t, i) => [Number(t.slice(0, 4)), i] as const).filter(([y]) => y >= from && y <= to).map(([, i]) => i);
  return { t: idx.map((i) => p.t[i]), v: idx.map((i) => p.v[i]), anom: idx.map((i) => p.anom[i]) };
}

function linfit(t: string[], y: number[]) {
  const x = t.map((s) => Number(s.slice(0, 4)) + (Number(s.slice(5, 7)) - 0.5) / 12);
  const n = x.length;
  const mx = x.reduce((a, b) => a + b, 0) / n;
  const my = y.reduce((a, b) => a + b, 0) / n;
  let sxy = 0;
  let sxx = 0;
  for (let i = 0; i < n; i++) {
    sxy += (x[i] - mx) * (y[i] - my);
    sxx += (x[i] - mx) ** 2;
  }
  return sxy / sxx; // units per year
}

export function ClimateExplorer() {
  const { data, error, loading } = useApi<ClimateSeriesFile>("/data/climate_series.json", true);
  const [vid, setVid] = useState<(typeof VARIABLES)[number]["id"]>("era5_sea_ice_extent");
  const [mode, setMode] = useState<"anom" | "value">("anom");
  const [from, setFrom] = useState(1979);
  const [to, setTo] = useState(2026);
  const [region, setRegion] = useState("antarctic");
  const [cmp, setCmp] = useState(true);

  const v = VARIABLES.find((x) => x.id === vid)!;
  const avail = VARIABLES.filter((x) => !data || data.series[x.id]);
  const s = data?.series[vid];
  const pack = useMemo(() => {
    if (!s) return null;
    const base = region === "antarctic" ? s.antarctic : s.sectors?.[region] ?? s.antarctic;
    return slice(base, from, to);
  }, [s, region, from, to]);

  const chart: Series[] = useMemo(() => {
    if (!data || !s || !pack) return [];
    const out: Series[] = [{ key: "a", name: `ERA5${region !== "antarctic" ? ` · ${titleCase(region)}` : ""}`.replace("ERA5", s.source.split(" ")[0]), color: "#48c8e8", t: pack.t, v: mode === "anom" ? pack.anom : pack.v, kind: mode === "anom" ? "bar" : "line" }];
    const c = "compare" in v ? data.series[v.compare] : undefined;
    if (cmp && c && region === "antarctic") {
      const cp = slice(c.antarctic, from, to);
      out.push({ key: "b", name: c.source.split(" ").slice(0, 2).join(" "), color: "#f4a261", t: cp.t, v: mode === "anom" ? cp.anom : cp.v, dashed: true });
    }
    return out;
  }, [data, s, pack, mode, v, cmp, region, from, to]);

  const seasonal = useMemo(() => {
    if (!s) return [];
    const base = region === "antarctic" ? s.antarctic : s.sectors?.[region] ?? s.antarctic;
    const years = [...new Set(base.t.map((t) => t.slice(0, 4)))].map(Number);
    const pick = [1980, 2000, 2015, years[years.length - 2], years[years.length - 1]].filter((y, i, a) => years.includes(y) && a.indexOf(y) === i);
    const colors = ["#3b5675", "#5f7fa3", "#7fa6c4", "#f4a261", "#e76f6a"];
    return pick.map((y, k) => ({
      key: String(y),
      name: String(y),
      color: colors[k] ?? "#fff",
      t: MONTHS,
      v: MONTHS.map((_, m) => {
        const i = base.t.indexOf(`${y}-${String(m + 1).padStart(2, "0")}`);
        return i >= 0 ? base.v[i] : null;
      }),
    }));
  }, [s, region]);

  if (loading) return <Loading label="Loading climate record" />;
  if (error || !data || !s || !pack) return <ErrorState error={error} what="the climate record" />;

  const trend = pack.t.length > 24 ? linfit(pack.t, pack.anom) * 10 : null;
  const last = pack.t.length - 1;
  const sectors = s.sectors ? Object.keys(s.sectors) : [];

  return (
    <div className="space-y-10">
      {/* controls */}
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Variable">
        {avail.map((x) => (
          <button
            key={x.id}
            role="tab"
            aria-selected={x.id === vid}
            onClick={() => {
              setVid(x.id);
              if (!data.series[x.id]?.sectors) setRegion("antarctic");
            }}
            className={cn("rounded-full border px-4 py-2 text-[13px] transition-colors", x.id === vid ? "border-cyan bg-cyan/10 text-cyan" : "border-line text-silver hover:border-line-strong hover:text-glacial")}
          >
            {x.label}
          </button>
        ))}
      </div>

      <div className="grid gap-8 rounded-[var(--radius)] border border-line bg-navy/30 p-5 md:p-8 lg:grid-cols-[1fr_260px]">
        <div className="min-w-0">
          <div className="mb-5 flex flex-wrap items-center gap-3">
            <DataBadge type={v.type} />
            <span className="font-mono text-[11px] text-muted">
              {s.title} · {s.units} · {s.domain}
            </span>
          </div>
          <TimeSeries series={chart} units={s.units} zeroLine={mode === "anom"} signed={mode === "anom"} brush height={360} digits={v.digits} />
          <dl className="mt-6 grid gap-x-8 gap-y-3 border-t border-line pt-5 text-[12px] sm:grid-cols-2 xl:grid-cols-3">
            {[
              ["Metric", s.title],
              ["Units", `${s.units}${mode === "anom" ? " (anomaly)" : ""}`],
              ["Coverage", `${s.antarctic.t[0]} → ${s.antarctic.t[s.antarctic.t.length - 1]} · ${s.domain}`],
              ["Source", s.source],
              ["Method", `${METHOD[vid] ?? "Area-weighted (cos latitude) monthly mean."} ${mode === "anom" ? `Anomaly vs ${s.clim ?? data.meta.climatology}.` : ""}`],
              [
                "Limitations",
                `${s.note ?? ""}${vid === "era5_sea_ice_extent" ? " OSI SAF reads up to ~1.6 M km² lower than ERA5 in December (summer melt affects passive-microwave retrievals); anomalies use each record's own climatology." : ""}${s.clim ? " Anomaly baseline is shorter than 1991–2020 because the record starts later." : ""}` || "Reanalysis values are model-constrained estimates, sparse in the interior before the satellite era.",
              ],
            ].map(([k, val]) => (
              <div key={k}>
                <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{k}</dt>
                <dd className="mt-1 leading-relaxed text-silver">{val}</dd>
              </div>
            ))}
          </dl>
        </div>
        <aside className="space-y-6">
          <div>
            <p className="t-meta mb-2">View</p>
            <div className="flex gap-2">
              {(["anom", "value"] as const).map((m) => (
                <button key={m} onClick={() => setMode(m)} className={cn("flex-1 rounded border px-3 py-2 text-[12px]", mode === m ? "border-cyan text-cyan" : "border-line text-silver")}>
                  {m === "anom" ? "Anomaly" : "Absolute"}
                </button>
              ))}
            </div>
          </div>
          <div>
            <p className="t-meta mb-2">Years</p>
            <div className="flex items-center gap-2 font-mono text-[12px]">
              <input type="number" min={1979} max={to} value={from} onChange={(e) => setFrom(Math.min(+e.target.value, to))} className="w-full rounded border border-line bg-navy px-2 py-1.5 text-glacial" aria-label="From year" />
              <span className="text-muted">→</span>
              <input type="number" min={from} max={2026} value={to} onChange={(e) => setTo(Math.max(+e.target.value, from))} className="w-full rounded border border-line bg-navy px-2 py-1.5 text-glacial" aria-label="To year" />
            </div>
          </div>
          {sectors.length > 0 && (
            <div>
              <p className="t-meta mb-2">Region</p>
              <select value={region} onChange={(e) => setRegion(e.target.value)} className="w-full rounded border border-line bg-navy px-2 py-2 text-[13px] text-glacial" aria-label="Region">
                <option value="antarctic">Whole domain ({s.domain})</option>
                {sectors.map((k) => (
                  <option key={k} value={k}>
                    {titleCase(k)} sector
                  </option>
                ))}
              </select>
            </div>
          )}
          {"compare" in v && (
            <label className="flex items-center gap-2 text-[13px] text-silver">
              <input type="checkbox" checked={cmp} onChange={(e) => setCmp(e.target.checked)} className="accent-[var(--cyan)]" />
              Compare with {data.series[v.compare]?.source.split(" ").slice(0, 2).join(" ")}
            </label>
          )}
          <div className="space-y-5 border-t border-line pt-5">
            <Stat label={`Latest · ${pack.t[last]}`} value={fmt(pack.v[last], v.digits)} unit={s.units} note={`Anomaly ${pack.anom[last] >= 0 ? "+" : ""}${fmt(pack.anom[last], v.digits)}`} />
            {trend != null && <Stat label={`Linear trend ${pack.t[0].slice(0, 4)}–${pack.t[last].slice(0, 4)}`} value={`${trend >= 0 ? "+" : ""}${fmt(trend, 3)}`} unit={`${s.units}/decade`} note="Least-squares fit to monthly anomalies; descriptive only." />}
          </div>
        </aside>
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        <div className="rounded-[var(--radius)] border border-line bg-navy/30 p-5 md:p-8">
          <p className="t-meta mb-5">Seasonal cycle · selected years</p>
          <TimeSeries series={seasonal} units={s.units} height={280} digits={v.digits} />
        </div>
        <div className="rounded-[var(--radius)] border border-line bg-navy/30 p-5 md:p-8">
          <p className="t-meta mb-5">Regional comparison · anomaly, 12-month mean</p>
          {s.sectors ? (
            <TimeSeries
              units={s.units}
              height={280}
              zeroLine
              digits={v.digits}
              series={Object.entries(s.sectors).map(([k, p]) => {
                const sp = slice(p, from, to);
                return { key: k, name: titleCase(k), color: SECTOR_COLORS[k] ?? "#fff", t: sp.t, v: sp.anom.map((_, i) => (i < 11 ? null : sp.anom.slice(i - 11, i + 1).reduce((a, b) => a + b, 0) / 12)) };
              })}
            />
          ) : (
            <p className="text-sm text-muted">Regional sectors are not computed for this variable.</p>
          )}
        </div>
      </div>
    </div>
  );
}
