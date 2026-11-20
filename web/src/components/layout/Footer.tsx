import Link from "next/link";
import { NAV, MODELS } from "@/config/site";
import { Logo } from "./Nav";

export function Footer() {
  return (
    <footer className="border-t border-line bg-polar">
      <div className="container-x grid gap-12 py-16 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <div className="flex items-center gap-3">
            <Logo />
            <span className="font-display tracking-[0.28em]">AETHENTRA</span>
          </div>
          <p className="t-body mt-5 max-w-sm">
            Scientific intelligence platform — Phase 1: Antarctic sea ice, temperature, satellite detection and climate
            anomalies. Research prototype; not for operational or safety-critical use.
          </p>
        </div>
        <div>
          <p className="t-meta mb-4">Navigate</p>
          <ul className="space-y-2 text-sm text-silver">
            {NAV.map((n) => (
              <li key={n.href}>
                <Link className="hover:text-glacial" href={n.href}>
                  {n.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="t-meta mb-4">Models</p>
          <ul className="space-y-2 text-sm text-silver">
            {MODELS.map((m) => (
              <li key={m.slug}>
                <Link className="hover:text-glacial" href={`/models/${m.slug}`}>
                  {m.code} · {m.name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="container-x flex flex-col justify-between gap-2 border-t border-line py-6 font-mono text-[11px] text-muted md:flex-row">
        <span>Data: NSIDC · NOAA PSL · ECMWF ERA5 · NASA MERRA-2 · Copernicus Marine · ESA Sentinel-1 · NASA GIBS</span>
        <span>© 2026 AETHENTRA</span>
      </div>
    </footer>
  );
}
