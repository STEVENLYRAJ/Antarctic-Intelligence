"use client";
import Link from "next/link";
import { X } from "lucide-react";
import type { Region } from "@/config/regions";
import { useApi } from "@/hooks/useApi";
import type { ClimateSeriesFile, Ml04Latest, SicForecast, T2mForecast } from "@/lib/api/types";
import { DataBadge } from "@/components/ui/primitives";
import { fmt, titleCase } from "@/lib/utils";

function Row({ label, value, sub, type, href }: { label: string; value: string; sub: string; type: string; href?: string }) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[0.7188rem] text-silver">{label}</span>
        <DataBadge type={type} />
      </div>
      <p className="t-num mt-1 text-xl text-glacial">{value}</p>
      <p className="font-mono text-[0.5938rem] text-muted">{sub}</p>
    </>
  );
  return href ? (
    <Link href={href} className="block border-t border-line py-3 transition-colors hover:bg-navy/40">
      {body}
    </Link>
  ) : (
    <div className="border-t border-line py-3">{body}</div>
  );
}

/** Region panel: geographic context + the regional outputs the APIs actually provide for this region. */
export function RegionCard({ region, onClose }: { region: Region; onClose: () => void }) {
  const sic = useApi<SicForecast>(region.ml01Sectors ? "/forecast/latest" : null);
  const t2m = useApi<T2mForecast>(region.ml02Region ? "/temperature/forecast/latest" : null);
  const anom = useApi<Ml04Latest>(region.ml04Regions ? "/api/ml04/latest" : null);
  const clim = useApi<ClimateSeriesFile>(region.climateSector ? "/data/climate_series.json" : null, true);

  const rows: React.ReactNode[] = [];
  if (sic.data && region.ml01Sectors) {
    const secs = sic.data.sectors.filter((s) => region.ml01Sectors!.includes(s.sector));
    const ext = secs.reduce((n, s) => n + s.extent_km2, 0);
    if (secs.length)
      rows.push(
        <Row
          key="ml01"
          label={`ML-01 forecast sea-ice extent${secs.length < 5 ? ` · ${secs.map((s) => titleCase(s.sector)).join(" + ")}` : " · all sectors"}`}
          value={`${fmt(ext / 1e6, 2)} M km²`}
          sub={`${sic.data.target_start} → ${sic.data.target_end} · ${sic.data.model_version}`}
          type="model_prediction"
          href="/models/ml-01"
        />,
      );
  }
  if (t2m.data && region.ml02Region) {
    const r = t2m.data.regions.find((x) => x.region === region.ml02Region);
    if (r)
      rows.push(
        <Row
          key="ml02"
          label={`ML-02 forecast 2 m temperature anomaly · ${titleCase(r.region)}`}
          value={`${r.forecast_mean_anomaly_degC >= 0 ? "+" : ""}${fmt(r.forecast_mean_anomaly_degC, 2)} °C`}
          sub={`${t2m.data.target_start} → ${t2m.data.target_end} · mean ${fmt(r.forecast_mean_t2m_degC, 1)} °C`}
          type="model_prediction"
          href="/models/ml-02"
        />,
      );
  }
  if (anom.data && region.ml04Regions) {
    const lm = anom.data.latest_multivariate;
    const rs = lm.regions.filter((x) => region.ml04Regions!.includes(x.region));
    const cells = rs.reduce((n, x) => n + x.cells, 0);
    const fl = rs.reduce((n, x) => n + x.flagged, 0);
    if (cells)
      rows.push(
        <Row
          key="ml04"
          label={`ML-04 cells flagged unusual · ${rs.map((x) => titleCase(x.region)).join(" + ")}`}
          value={`${fl} / ${cells}  (${fmt((100 * fl) / cells, 0)} %)`}
          sub={`${lm.month} · ${lm.selected_method} · statistical unusualness, not a cause`}
          type="statistical_anomaly"
          href="/models/ml-04"
        />,
      );
  }
  if (clim.data && region.climateSector) {
    const s = clim.data.series.era5_sea_ice_extent?.sectors?.[region.climateSector];
    if (s && s.t.length) {
      const i = s.t.length - 1;
      rows.push(
        <Row
          key="era5"
          label="ERA5 sea-ice extent anomaly vs 1991–2020 (NSIDC sector)"
          value={`${s.anom[i] >= 0 ? "+" : ""}${fmt(s.anom[i], 2)} M km²`}
          sub={`${s.t[i]} · extent ${fmt(s.v[i], 2)} M km²`}
          type="reanalysis"
          href="/intelligence"
        />,
      );
    }
  }
  const loading = [sic, t2m, anom, clim].some((x) => x.loading);

  return (
    <div className="flex h-full flex-col">
      <div className="relative h-28 shrink-0 overflow-hidden">
        {region.imagery && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={`/data/imagery/${region.imagery}.jpg`} alt="" className="absolute inset-0 h-full w-full object-cover opacity-70 [filter:contrast(1.1)_brightness(0.8)]" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-polar to-polar/20" />
        <button onClick={onClose} aria-label="Close region panel" className="absolute right-3 top-3 rounded-full bg-polar/70 p-1.5 text-muted hover:text-glacial">
          <X size={14} />
        </button>
        <div className="absolute bottom-3 left-4">
          <p className="font-mono text-[0.625rem] uppercase tracking-[0.18em] text-ice">{region.kicker}</p>
          <p className="font-display text-xl text-glacial">{region.name}</p>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-4 pb-4" data-lenis-prevent>
        <p className="mt-3 text-[0.7813rem] leading-relaxed text-silver">{region.context}</p>
        <p className="mt-2 font-mono text-[0.625rem] text-muted">
          Centre {fmt(Math.abs(region.centre[0]), 1)}° {region.centre[0] < 0 ? "S" : "N"}, {fmt(Math.abs(region.centre[1]), 1)}° {region.centre[1] < 0 ? "W" : "E"}
        </p>
        <p className="t-meta mt-5 mb-1">Regional intelligence</p>
        {rows.length ? rows : loading ? <p className="py-3 font-mono text-[0.625rem] uppercase tracking-[0.16em] text-muted">Loading regional outputs…</p> : null}
        {!loading && !rows.length && (
          <p className="border-t border-line py-3 text-[0.75rem] text-muted">No AETHENTRA model reports a separate breakdown for this region. Use the map layers for spatial detail.</p>
        )}
        {region.imagery && <p className="mt-3 font-mono text-[0.5625rem] text-muted">Header image: NASA MODIS/Blue Marble via GIBS.</p>}
      </div>
    </div>
  );
}
