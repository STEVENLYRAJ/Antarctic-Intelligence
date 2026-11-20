"use client";
import { useApi } from "@/hooks/useApi";
import type { ClimateSeriesFile } from "@/lib/api/types";
import { TimeSeries } from "@/components/charts/TimeSeries";
import { DataBadge, ErrorState, Loading } from "@/components/ui/primitives";

/** 12-month running mean so the multi-decade signal is readable at a glance. */
function running(v: number[], w = 12): (number | null)[] {
  return v.map((_, i) => {
    if (i < w - 1) return null;
    let s = 0;
    for (let k = i - w + 1; k <= i; k++) s += v[k];
    return s / w;
  });
}

export function ClimateTeaser() {
  const { data, error, loading } = useApi<ClimateSeriesFile>("/data/climate_series.json", true);
  if (loading) return <Loading label="Loading climate record" />;
  if (error || !data) return <ErrorState error={error} what="the climate record" />;
  const era = data.series.era5_sea_ice_extent?.antarctic;
  const osi = data.series.osisaf_sea_ice_extent?.antarctic;
  if (!era) return <ErrorState error={new Error("series missing")} what="the sea-ice series" />;
  return (
    <div className="rounded-[var(--radius)] border border-line bg-navy/30 p-5 md:p-8">
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <DataBadge type="reanalysis" />
        <DataBadge type="observation" />
        <span className="font-mono text-[11px] text-muted">12-month running mean · million km² · baseline 1991–2020</span>
      </div>
      <TimeSeries
        units="M km²"
        zeroLine
        height={340}
        series={[
          { key: "era", name: "ERA5 sea-ice extent anomaly", color: "#48c8e8", t: era.t, v: running(era.anom) },
          ...(osi ? [{ key: "osi", name: "OSI SAF CDR extent anomaly", color: "#f4a261", t: osi.t, v: running(osi.anom), dashed: true }] : []),
        ]}
      />
      <p className="mt-4 text-xs text-muted">
        Sources: ERA5 monthly sea-ice cover (Copernicus CDS); OSI-450/OSI-430 via Copernicus Marine. Extent = area with concentration ≥ 15 %.
      </p>
    </div>
  );
}
