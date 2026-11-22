"use client";
import { useMemo } from "react";
import { useApi } from "@/hooks/useApi";
import type { ClimateSeriesFile, DailySeriesFile, Ml04MonthlySummary, SeriesPack } from "@/lib/api/types";
import { DataBadge, ErrorState, Loading } from "@/components/ui/primitives";
import { TimeSeries } from "@/components/charts/TimeSeries";
import { fmt } from "@/lib/utils";

interface Insight {
  k: string;
  kicker: string;
  title: string;
  value: string;
  body: string;
  method: string;
  type: string;
  chart?: { t: string[]; v: (number | null)[]; units: string; signed?: boolean; label?: string; second?: { name: string; v: (number | null)[] } };
}

const minIdx = (a: number[]) => a.reduce((b, v, i) => (v < a[b] ? i : b), 0);
const maxIdx = (a: number[]) => a.reduce((b, v, i) => (v > a[b] ? i : b), 0);
const mon = (t: string) => new Date(`${t}-15`).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
const annual = (p: SeriesPack) => {
  const m = new Map<string, number[]>();
  p.t.forEach((t, i) => m.set(t.slice(0, 4), [...(m.get(t.slice(0, 4)) ?? []), p.anom[i]]));
  const years = [...m.entries()].filter(([, v]) => v.length === 12);
  return { t: years.map(([y]) => y), v: years.map(([, v]) => v.reduce((a, b) => a + b, 0) / 12) };
};

export function Insights() {
  const cs = useApi<ClimateSeriesFile>("/data/climate_series.json", true);
  const ml4 = useApi<Ml04MonthlySummary>("/api/ml04/monthly-summary");
  const daily = useApi<DailySeriesFile>("/data/daily_series.json", true);

  const items = useMemo<Insight[]>(() => {
    if (!cs.data) return [];
    const S = cs.data.series;
    const out: Insight[] = [];
    const ice = S.era5_sea_ice_extent.antarctic;
    const iMin = minIdx(ice.anom);
    const ann = annual(ice);
    out.push({
      k: "ice-low",
      kicker: "Sea ice",
      title: "The largest sea-ice deficit in the ERA5 record",
      value: `${fmt(ice.anom[iMin], 2)} M km²`,
      body: `${mon(ice.t[iMin])} had the lowest monthly sea-ice extent relative to the 1991–2020 average for that month in the 1979–2026 ERA5 record (${fmt(ice.v[iMin], 2)} million km²).`,
      method: "ERA5 monthly sea-ice cover ≥ 15 %, area south of 50° S, anomaly vs 1991–2020 monthly climatology.",
      type: "reanalysis",
      chart: { t: ann.t, v: ann.v, units: "M km²", signed: true },
    });
    const recent = ice.anom.slice(-36);
    const below = recent.filter((x) => x < 0).length;
    out.push({
      k: "ice-recent",
      kicker: "Sea ice",
      title: "A persistent shift below the recent average",
      value: `${below} of 36`,
      body: `In the last 36 months of the record (${ice.t[ice.t.length - 36]} → ${ice.t[ice.t.length - 1]}), ${below} months had below-average Antarctic sea-ice extent.`,
      method: "Count of months with negative ERA5 extent anomaly. Descriptive statistic; no attribution of cause.",
      type: "reanalysis",
    });
    const t = S.era5_t2m.antarctic;
    const tMax = maxIdx(t.anom);
    const tAnn = annual(t);
    out.push({
      k: "t2m-warm",
      kicker: "Temperature",
      title: "The warmest month relative to normal",
      value: `+${fmt(t.anom[tMax], 2)} °C`,
      body: `${mon(t.t[tMax])} was the largest positive 2 m temperature anomaly averaged over 60–90° S in ERA5 (monthly mean ${fmt(t.v[tMax], 1)} °C).`,
      method: "cos(latitude)-weighted ERA5 monthly 2 m temperature, anomaly vs 1991–2020. MERRA-2 is available in the Climate Explorer for comparison.",
      type: "reanalysis",
      chart: { t: tAnn.t, v: tAnn.v, units: "°C", signed: true },
    });
    const g = S.glorys_sea_ice_thickness?.antarctic;
    if (g) {
      const gAnn = annual(g);
      out.push({
        k: "thick",
        kicker: "Ocean & ice",
        title: "Modelled sea-ice thickness, year by year",
        value: `${fmt(g.v.reduce((a, b) => a + b, 0) / g.v.length, 2)} m`,
        body: "Mean thickness of ice-covered cells in the GLORYS12 reanalysis over 1993–2026. Thickness is modelled, not observed: the only satellite Antarctic thickness record in the archive (merged CryoSat-2 + Sentinel-3 + SMOS) begins in April 2025.",
        method: "GLORYS12 monthly sithick where siconc ≥ 15 %, cos(latitude)-weighted, 50–80° S.",
        type: "model_reanalysis",
        chart: { t: gAnn.t, v: gAnn.v, units: "m", signed: true },
      });
    }
    const de = daily.data?.sea_ice_extent;
    if (de) {
      const yrs = Object.entries(de.years)
        .map(([y, a]) => ({ y, a: a.filter((v): v is number => v != null), feb: a.slice(31, 59).some((v) => v != null), sep: a.slice(243, 273).some((v) => v != null) }))
        .filter((r) => r.a.length >= 150 && r.feb && r.sep && r.y !== "1978");
      const mins = yrs.map((r) => Math.min(...r.a));
      const maxs = yrs.map((r) => Math.max(...r.a));
      const lo = minIdx(maxs);
      const loMin = minIdx(mins);
      out.push({
        k: "daily-max",
        kicker: "Sea ice · daily record",
        title: "The lowest winter maximum in the satellite record",
        value: `${fmt(maxs[lo], 2)} M km²`,
        body: `${yrs[lo].y} had the lowest annual maximum daily extent in the OSI SAF record (${yrs[0].y}–${yrs[yrs.length - 1].y}). The lowest annual minimum was ${fmt(mins[loMin], 2)} M km² in ${yrs[loMin].y}.`,
        method: `${de.source}. Annual max / min of daily extent (≥ 15 %); years need data in both February and September. Single-day extremes are sensitive to weather.`,
        type: "observation",
        chart: { t: yrs.map((r) => r.y), v: maxs, units: "M km²", label: "Annual maximum and minimum daily extent", second: { name: "Annual minimum", v: mins } },
      });
    }
    const dr = S.ifremer_drift_speed?.antarctic;
    if (dr) {
      const m = new Map<string, number[]>();
      dr.t.forEach((t, i) => {
        const mo = +t.slice(5, 7);
        if (mo >= 5 && mo <= 10) m.set(t.slice(0, 4), [...(m.get(t.slice(0, 4)) ?? []), dr.v[i]]);
      });
      const yrs = [...m.entries()].filter(([, v]) => v.length === 6);
      const vv = yrs.map(([, v]) => v.reduce((a, b) => a + b, 0) / v.length);
      const fast = maxIdx(vv);
      out.push({
        k: "drift",
        kicker: "Sea ice · motion",
        title: "How fast the pack ice moves",
        value: `${fmt(vv.reduce((a, b) => a + b, 0) / vv.length, 1)} cm/s`,
        body: `Average winter (May–October) drift speed of Antarctic sea ice, ${yrs[0][0]}–${yrs[yrs.length - 1][0]} — roughly ${fmt((vv.reduce((a, b) => a + b, 0) / vv.length) * 0.864, 0)} km per day. The fastest winter was ${yrs[fast][0]} (${fmt(vv[fast], 1)} cm/s). Drift is driven mainly by wind, so it tracks the atmosphere year to year.`,
        method: "IFREMER AMSR-E/AMSR2 3-day drift (Copernicus Marine C5): monthly mean of daily speeds over ice-covered cells, averaged May–Oct. Winters with a missing month are skipped (AMSR-E/AMSR2 gap 2011–2012).",
        type: "observation",
        chart: { t: yrs.map(([y]) => y), v: vv, units: "cm/s", label: "Winter-mean drift speed" },
      });
    }
    const so = S.multiobs_sst?.antarctic;
    if (so) {
      const sAnn = annual(so);
      const w = maxIdx(sAnn.v);
      out.push({
        k: "ocean",
        kicker: "Southern Ocean",
        title: "The warmest year at the ocean surface",
        value: `+${fmt(sAnn.v[w], 2)} °C`,
        body: `${sAnn.t[w]} had the highest annual-mean near-surface ocean temperature anomaly south of 50° S in the MULTIOBS reconstruction (${sAnn.t[0]}–${sAnn.t[sAnn.t.length - 1]}, complete years only), relative to 1993–2020.`,
        method: "Copernicus Marine MULTIOBS observation-based T/S (C7), area-weighted 50–82° S, anomaly vs 1993–2020 monthly climatology. Under-ice values are sparse and largely interpolated.",
        type: "observation",
        chart: { t: sAnn.t, v: sAnn.v, units: "°C", signed: true },
      });
    }
    if (ml4.data) {
      const rows = ml4.data.rows.filter((r) => typeof r.multivariate_flag_area_fraction === "number");
      const lastYear = rows.slice(-12);
      const mean = lastYear.reduce((a, r) => a + (r.multivariate_flag_area_fraction as number), 0) / lastYear.length;
      out.push({
        k: "ml04",
        kicker: "ML-04",
        title: "How often the detector raises a flag",
        value: `${fmt(mean * 100, 1)} %`,
        body: `Average share of the 50–90° S area flagged at ≥ moderate severity over the 12 months ending ${lastYear[lastYear.length - 1].month}, against an expected 5 % under the 1979–2010 training climate. A higher rate signals a climate that differs from the training baseline — it is not, by itself, evidence of extreme events.`,
        method: "ML-04 LOF (k = 20) monthly summary from /api/ml04/monthly-summary.",
        type: "statistical_anomaly",
      });
    }
    return out;
  }, [cs.data, ml4.data, daily.data]);

  if (cs.loading) return <Loading label="Computing insights" />;
  if (cs.error) return <ErrorState error={cs.error} what="the climate record" />;

  return (
    <div className="space-y-px overflow-hidden rounded-[var(--radius)] border border-line bg-line">
      {items.map((it, i) => (
        <article key={it.k} className="grid gap-10 bg-polar p-8 md:p-12 lg:grid-cols-[1fr_1.1fr]">
          <div>
            <p className="t-meta flex items-center gap-3">
              <span className="text-cyan">{String(i + 1).padStart(2, "0")}</span>
              <span className="h-px w-8 bg-line-strong" />
              {it.kicker}
            </p>
            <h3 className="t-h2 mt-6 text-glacial">{it.title}</h3>
            <p className="t-num mt-6 text-5xl text-glacial">{it.value}</p>
            <p className="t-body mt-5 max-w-xl">{it.body}</p>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <DataBadge type={it.type} />
              <span className="text-[11px] text-muted">{it.method}</span>
            </div>
          </div>
          {it.chart && (
            <div className="self-center">
              <p className="t-meta mb-3">{it.chart.label ?? "Annual-mean anomaly"}</p>
              <TimeSeries
                series={[
                  { key: "a", name: it.chart.second ? "Annual maximum" : it.chart.label ?? "Annual anomaly", color: "#48c8e8", t: it.chart.t, v: it.chart.v, kind: it.chart.second || !it.chart.signed ? "line" : "bar" },
                  ...(it.chart.second ? [{ key: "b", name: it.chart.second.name, color: "#f4a261", t: it.chart.t, v: it.chart.second.v }] : []),
                ]}
                units={it.chart.units}
                signed={it.chart.signed && !it.chart.second}
                zeroLine={!!it.chart.signed}
                height={240}
              />
            </div>
          )}
        </article>
      ))}
    </div>
  );
}
