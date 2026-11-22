import clsx, { type ClassValue } from "clsx";

export const cn = (...c: ClassValue[]) => clsx(c);

const nf = (d: number) => new Intl.NumberFormat("en-GB", { maximumFractionDigits: d, minimumFractionDigits: d });
export const fmt = (v: number | null | undefined, d = 1) => (v == null || !Number.isFinite(v) ? "—" : nf(d).format(v));
export const fmtMkm2 = (km2: number | null | undefined, d = 2) => (km2 == null ? "—" : `${fmt(km2 / 1e6, d)}`);
export const pct = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${fmt(v * 100, d)}%`);
export const titleCase = (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
