"use client";
import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { DATASETS, STATUS_LABEL, type Category, type Status } from "@/config/datasets";
import { cn } from "@/lib/utils";

const CATS: Category[] = ["Sea ice", "Atmosphere", "Ocean", "Satellite imagery", "Basemap"];
const STATUS: Status[] = ["model", "explorer", "downloaded", "streamed"];
const STATUS_CLS: Record<Status, string> = {
  model: "border-ok/50 text-ok",
  explorer: "border-cyan/50 text-cyan",
  downloaded: "border-silver/40 text-silver",
  streamed: "border-ice/40 text-ice",
};

export function DatasetCatalogue() {
  const [q, setQ] = useState("");
  const [cat, setCat] = useState<Category | "all">("all");
  const [st, setSt] = useState<Status | "all">("all");
  const [year, setYear] = useState<number | "">("");
  const [open, setOpen] = useState<string | null>(null);

  const rows = useMemo(
    () =>
      DATASETS.filter(
        (d) =>
          (cat === "all" || d.category === cat) &&
          (st === "all" || d.status.includes(st)) &&
          (year === "" || (d.start <= year && d.end >= year)) &&
          (!q || `${d.name} ${d.provider} ${d.variables.join(" ")} ${d.region}`.toLowerCase().includes(q.toLowerCase())),
      ),
    [q, cat, st, year],
  );

  return (
    <div>
      <div className="grid gap-4 md:grid-cols-[1fr_auto_auto_auto]">
        <label className="flex items-center gap-2 rounded border border-line bg-navy/50 px-3 py-2.5">
          <Search size={15} className="text-muted" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by name, variable, provider or region" className="w-full bg-transparent text-sm text-glacial placeholder:text-muted focus:outline-none" aria-label="Filter datasets" />
        </label>
        <select value={cat} onChange={(e) => setCat(e.target.value as Category | "all")} className="rounded border border-line bg-navy px-3 py-2.5 text-sm text-glacial" aria-label="Category">
          <option value="all">All categories</option>
          {CATS.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
        <select value={st} onChange={(e) => setSt(e.target.value as Status | "all")} className="rounded border border-line bg-navy px-3 py-2.5 text-sm text-glacial" aria-label="Processing status">
          <option value="all">Any status</option>
          {STATUS.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
        <input type="number" min={1978} max={2026} value={year} onChange={(e) => setYear(e.target.value ? +e.target.value : "")} placeholder="Covers year…" className="w-40 rounded border border-line bg-navy px-3 py-2.5 text-sm text-glacial placeholder:text-muted" aria-label="Covers year" />
      </div>
      <p className="mt-4 font-mono text-[11px] text-muted">
        {rows.length} of {DATASETS.length} datasets · coverage and sizes verified on the local archive, 20 Nov 2026
      </p>

      <ul className="mt-6 divide-y divide-line border-y border-line">
        {rows.map((d) => {
          const isOpen = open === d.id;
          return (
            <li key={d.id}>
              <button onClick={() => setOpen(isOpen ? null : d.id)} aria-expanded={isOpen} className="grid w-full gap-3 py-5 text-left md:grid-cols-[1.6fr_1fr_1fr_auto] md:items-center">
                <span>
                  <span className="block text-[15px] text-glacial">{d.name}</span>
                  <span className="mt-1 block text-[12px] text-muted">
                    {d.provider} · {d.category}
                  </span>
                </span>
                <span className="font-mono text-[11px] text-silver">{d.coverage}</span>
                <span className="font-mono text-[11px] text-silver">{d.resolution}</span>
                <span className="flex flex-wrap justify-start gap-1.5 md:justify-end">
                  {d.status.map((s) => (
                    <span key={s} className={cn("rounded-sm border px-2 py-0.5 font-mono text-[9.5px] uppercase tracking-[0.12em]", STATUS_CLS[s])}>
                      {STATUS_LABEL[s]}
                    </span>
                  ))}
                </span>
              </button>
              {isOpen && (
                <dl className="grid gap-x-10 gap-y-3 pb-6 text-[13px] md:grid-cols-2">
                  {[
                    ["Variables", d.variables.join(", ")],
                    ["Units", d.units],
                    ["Format", d.format],
                    ["Region", d.region],
                    ["Size on disk", d.size],
                    ["Data type", d.dataType.replace(/_/g, " ")],
                    ["Used by", d.usedBy.length ? d.usedBy.join(", ") : "Not yet used by a model or the frontend"],
                    ["Provenance", d.provenance],
                  ].map(([k, v]) => (
                    <div key={k} className="grid grid-cols-[110px_1fr] gap-3">
                      <dt className="text-muted">{k}</dt>
                      <dd className="text-silver">{v}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
