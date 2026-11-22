"use client";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { MODELS } from "@/config/site";
import { useApi } from "@/hooks/useApi";
import type { Ml04Latest, SarWeekly, SicForecast, T2mForecast } from "@/lib/api/types";
import { DataBadge } from "@/components/ui/primitives";
import { Spotlight } from "@/components/ui/interactive";
import { fmt } from "@/lib/utils";

function Headline({ slug }: { slug: string }) {
  const sic = useApi<SicForecast>(slug === "ml-01" ? "/forecast/latest" : null);
  const t2m = useApi<T2mForecast>(slug === "ml-02" ? "/temperature/forecast/latest" : null);
  const sar = useApi<SarWeekly>(slug === "ml-03" ? "/seaice-detection/detection/weekly" : null);
  const anom = useApi<Ml04Latest>(slug === "ml-04" ? "/api/ml04/latest" : null);

  let value: string | null = null;
  let label = "";
  let when = "";
  let type = "model_prediction";
  if (sic.data) {
    value = `${fmt(sic.data.extent_km2 / 1e6, 2)} M km²`;
    label = "Forecast sea-ice extent";
    when = `${sic.data.target_start} → ${sic.data.target_end}`;
  } else if (t2m.data) {
    const all = t2m.data.regions.find((r) => r.region === "all");
    value = all ? `${all.forecast_mean_anomaly_degC >= 0 ? "+" : ""}${fmt(all.forecast_mean_anomaly_degC, 2)} °C` : null;
    label = "Forecast mean anomaly, 50–90° S";
    when = `${t2m.data.target_start} → ${t2m.data.target_end}`;
  } else if (sar.data) {
    value = `${fmt(sar.data.n_acquisitions, 0)}`;
    label = "Sentinel-1 scenes classified this week";
    when = `${sar.data.week_start} → ${sar.data.week_end}`;
  } else if (anom.data) {
    const s = anom.data.latest_multivariate;
    value = `${fmt(s.statistics.multivariate_flag_cells, 0)} cells`;
    label = "Flagged by the multivariate detector";
    when = s.month;
    type = "statistical_anomaly";
  }
  const st = [sic, t2m, sar, anom].find((s) => s.loading || s.error);
  return (
    <div className="mt-8 min-h-[5.75rem]">
      {value ? (
        <>
          <DataBadge type={type} />
          <p className="t-num mt-3 text-3xl text-glacial">{value}</p>
          <p className="mt-1 text-xs text-muted">
            {label} · {when}
          </p>
        </>
      ) : st?.error ? (
        <p className="font-mono text-[0.6875rem] text-muted">Live value unavailable (API offline)</p>
      ) : (
        <p className="font-mono text-[0.6875rem] uppercase tracking-[0.16em] text-muted">Loading live output…</p>
      )}
    </div>
  );
}

export function ModuleCards() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {MODELS.map((m) => (
        <Spotlight key={m.slug} className="rounded-[var(--radius-lg)]">
        <Link
          href={`/models/${m.slug}`}
          data-reveal
          className="group relative flex h-full flex-col justify-between overflow-hidden rounded-[var(--radius-lg)] border border-line bg-midnight/60 p-8 transition-colors duration-500 hover:bg-navy/60 md:p-10"
        >
          <span className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full opacity-[0.07] blur-3xl transition-opacity duration-700 group-hover:opacity-[0.16]" style={{ background: m.accent }} />
          <span className="absolute left-0 top-0 h-px w-0 transition-all duration-700 group-hover:w-full" style={{ background: m.accent }} />
          <div>
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs tracking-[0.2em]" style={{ color: m.accent }}>
                {m.code}
              </span>
              <ArrowUpRight className="text-muted transition-all duration-500 group-hover:-translate-y-1 group-hover:translate-x-1 group-hover:text-glacial" size={20} />
            </div>
            <h3 className="t-h3 mt-6 text-glacial">{m.name}</h3>
            <p className="t-body mt-2">{m.short}</p>
          </div>
          <Headline slug={m.slug} />
        </Link>
        </Spotlight>
      ))}
    </div>
  );
}
