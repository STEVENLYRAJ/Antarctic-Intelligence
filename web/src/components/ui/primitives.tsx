import Link from "next/link";
import type { ReactNode } from "react";
import { AlertTriangle, ArrowUpRight, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DataType } from "@/lib/api/types";

/* ---------- Data-type badge: every value shown must say what kind of data it is ---------- */
const DT: Record<string, { label: string; cls: string }> = {
  model_prediction: { label: "Model prediction", cls: "border-warn/50 text-warn" },
  observation: { label: "Observation", cls: "border-ok/50 text-ok" },
  reanalysis_observation: { label: "Reanalysis", cls: "border-ice/40 text-ice" },
  reanalysis: { label: "Reanalysis", cls: "border-ice/40 text-ice" },
  reanalysis_anomaly: { label: "Reanalysis anomaly", cls: "border-ice/40 text-ice" },
  statistical_anomaly: { label: "Statistical anomaly", cls: "border-alert/50 text-alert" },
  evaluation: { label: "Evaluation", cls: "border-silver/40 text-silver" },
  model_reanalysis: { label: "Model reanalysis", cls: "border-ice/40 text-ice" },
  demo: { label: "Demo data", cls: "border-alert bg-alert/10 text-alert" },
};

export function DataBadge({ type, className }: { type: DataType; className?: string }) {
  const known = DT[type] ?? (type.includes("prediction") ? DT.model_prediction : { label: type.replace(/_/g, " "), cls: "border-silver/40 text-silver" });
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 font-mono text-[0.625rem] uppercase tracking-[0.14em]", known.cls, className)}>
      <span className="h-1 w-1 rounded-full bg-current" />
      {known.label}
    </span>
  );
}

/* ---------- Section heading ---------- */
export function Eyebrow({ index, children, className }: { index?: string; children: ReactNode; className?: string }) {
  return (
    <p className={cn("t-meta flex items-center gap-3", className)}>
      {index && <span className="text-cyan">{index}</span>}
      <span className="h-px w-8 bg-line-strong" />
      {children}
    </p>
  );
}

/* ---------- Stat ---------- */
export function Stat({ label, value, unit, note, accent }: { label: string; value: ReactNode; unit?: string; note?: ReactNode; accent?: string }) {
  return (
    <div className="border-t border-line pt-4">
      <p className="t-meta">{label}</p>
      <p className="t-num mt-2 text-3xl text-glacial md:text-4xl" style={accent ? { color: accent } : undefined}>
        {value}
        {unit && <span className="ml-1.5 text-base text-muted">{unit}</span>}
      </p>
      {note && <p className="mt-1.5 text-xs leading-relaxed text-muted">{note}</p>}
    </div>
  );
}

/* ---------- Panel ---------- */
export function Panel({ children, className, title, meta }: { children: ReactNode; className?: string; title?: ReactNode; meta?: ReactNode }) {
  return (
    <section className={cn("rounded-[var(--radius)] border border-line bg-navy/40", className)}>
      {(title || meta) && (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          {title && <h3 className="font-display text-[0.9375rem] text-glacial">{title}</h3>}
          {meta}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

/* ---------- States ---------- */
export function Loading({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <div role="status" className={cn("flex items-center gap-3 py-8 font-mono text-xs uppercase tracking-[0.16em] text-muted", className)}>
      <Loader2 className="animate-spin text-cyan" size={16} /> {label}…
    </div>
  );
}

export function ErrorState({ error, what = "data", className }: { error: Error | null; what?: string; className?: string }) {
  return (
    <div role="alert" className={cn("flex items-start gap-3 rounded border border-alert/30 bg-alert/5 p-4 text-sm text-silver", className)}>
      <AlertTriangle size={16} className="mt-0.5 shrink-0 text-alert" />
      <div>
        <p className="text-glacial">Could not load {what}.</p>
        <p className="mt-1 font-mono text-xs text-muted">
          {error?.message ?? "Unknown error"} — is the AETHENTRA API running on the configured backend URL?
        </p>
      </div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-sm text-muted">{children}</p>;
}

/* ---------- Buttons ---------- */
export function ButtonLink({ href, children, variant = "primary", className }: { href: string; children: ReactNode; variant?: "primary" | "ghost"; className?: string }) {
  return (
    <Link
      href={href}
      className={cn(
        "group inline-flex items-center gap-3 rounded-full px-6 py-3.5 text-[0.8125rem] font-medium uppercase tracking-[0.16em] transition-all duration-300",
        variant === "primary"
          ? "bg-glacial text-polar hover:bg-cyan"
          : "border border-line-strong text-glacial hover:border-cyan hover:text-cyan",
        className,
      )}
    >
      {children}
      <ArrowUpRight size={16} className="transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
    </Link>
  );
}

/* ---------- Key-value list ---------- */
export function KV({ rows, className }: { rows: [string, ReactNode][]; className?: string }) {
  return (
    <dl className={cn("divide-y divide-line text-sm", className)}>
      {rows.map(([k, v]) => (
        <div key={k} className="grid grid-cols-[minmax(7.5rem,40%)_minmax(0,1fr)] gap-4 py-2.5">
          <dt className="text-muted">{k}</dt>
          <dd className="break-words text-glacial">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/* ---------- Colour legend ---------- */
export function Legend({ colors, vmin, vmax, units, className }: { colors: string[]; vmin: number | null; vmax: number | null; units: string; className?: string }) {
  return (
    <div className={cn("w-full", className)}>
      <div className="h-2 w-full rounded-sm" style={{ background: `linear-gradient(90deg, ${colors.join(",")})` }} />
      <div className="mt-1.5 flex justify-between font-mono text-[0.625rem] text-muted">
        <span>{vmin ?? "auto"}</span>
        <span>{units}</span>
        <span>{vmax ?? "auto"}</span>
      </div>
    </div>
  );
}
