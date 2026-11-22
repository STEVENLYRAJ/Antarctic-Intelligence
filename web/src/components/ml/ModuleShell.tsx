import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { MODELS } from "@/config/site";
import { cn } from "@/lib/utils";
import { Footer } from "@/components/layout/Footer";
import { SplitReveal } from "@/components/ui/Reveal";
import { SectionIndex } from "./SectionIndex";

export interface ModuleSection {
  id: string;
  title: string;
  content: ReactNode;
}

/** Shared layout for the four ML module pages: hero, module switcher, scroll-spy index, 9 standard sections, prev/next. */
export function ModuleShell({ slug, headline, lead, sections, heroAside }: { slug: string; headline: ReactNode[]; lead: string; sections: ModuleSection[]; heroAside?: ReactNode }) {
  const i = MODELS.findIndex((m) => m.slug === slug);
  const m = MODELS[i];
  const prev = MODELS[(i + MODELS.length - 1) % MODELS.length];
  const next = MODELS[(i + 1) % MODELS.length];
  return (
    <main id="main" className="pt-16">
      <header className="relative overflow-hidden border-b border-line">
        <div className="grid-lines absolute inset-0 opacity-50" />
        <div className="absolute -right-40 -top-40 h-[520px] w-[520px] rounded-full opacity-[0.12] blur-3xl" style={{ background: m.accent }} />
        <div className="container-x relative grid gap-12 py-24 md:py-32 lg:grid-cols-[1.3fr_1fr] lg:items-end">
          <div>
            <p className="t-meta flex items-center gap-3">
              <Link href="/models" className="hover:text-glacial">
                ML Models
              </Link>
              <span className="h-px w-8 bg-line-strong" />
              <span style={{ color: m.accent }}>{m.code}</span>
            </p>
            <SplitReveal as="h1" trigger="mount" className="t-h1 mt-8 text-glacial" lines={headline} />
            <p className="t-lead mt-8 max-w-2xl">{lead}</p>
          </div>
          {heroAside}
        </div>
      </header>

      <nav aria-label="ML modules" className="sticky top-16 z-30 border-b border-line bg-polar/[0.97] backdrop-blur-md">
        <ul className="container-x flex gap-1 overflow-x-auto [scrollbar-width:none]">
          {MODELS.map((x) => {
            const on = x.slug === slug;
            return (
              <li key={x.slug} className="shrink-0">
                <Link
                  href={`/models/${x.slug}`}
                  aria-current={on ? "page" : undefined}
                  className={cn("relative flex items-center gap-2.5 px-3 py-3.5 text-[12.5px] transition-colors", on ? "text-glacial" : "text-muted hover:text-silver")}
                >
                  <span className="font-mono text-[10px]" style={{ color: x.accent }}>
                    {x.code}
                  </span>
                  <span className="hidden sm:inline">{x.name}</span>
                  {on && <span className="absolute inset-x-3 bottom-0 h-px" style={{ background: x.accent }} />}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="container-x grid gap-12 py-16 lg:grid-cols-[210px_1fr]">
        <nav aria-label="On this page" className="hidden lg:block">
          <SectionIndex sections={sections.map(({ id, title }) => ({ id, title }))} accent={m.accent} />
        </nav>
        <div className="min-w-0 space-y-24">
          {sections.map((s, k) => (
            <section key={s.id} id={s.id} className="scroll-mt-36">
              <p className="t-meta flex items-center gap-3">
                <span style={{ color: m.accent }}>{String(k + 1).padStart(2, "0")}</span>
                <span className="h-px w-8 bg-line-strong" />
                {s.title}
              </p>
              <div className="mt-8">{s.content}</div>
            </section>
          ))}
        </div>
      </div>

      <nav aria-label="Other models" className="border-t border-line">
        <div className="container-x grid md:grid-cols-2">
          <Link href={`/models/${prev.slug}`} className="group flex items-center gap-4 border-line py-10 md:border-r md:pr-8">
            <ArrowLeft className="text-muted transition-transform group-hover:-translate-x-1" />
            <span>
              <span className="t-meta block">{prev.code}</span>
              <span className="t-h3 text-glacial">{prev.name}</span>
            </span>
          </Link>
          <Link href={`/models/${next.slug}`} className="group flex items-center justify-end gap-4 py-10 text-right md:pl-8">
            <span>
              <span className="t-meta block">{next.code}</span>
              <span className="t-h3 text-glacial">{next.name}</span>
            </span>
            <ArrowRight className="text-muted transition-transform group-hover:translate-x-1" />
          </Link>
        </div>
      </nav>
      <Footer />
    </main>
  );
}

export function Prose({ children }: { children: ReactNode }) {
  return <div className="t-body max-w-3xl space-y-4 [&_strong]:font-medium [&_strong]:text-glacial">{children}</div>;
}

export function BulletList({ items }: { items: ReactNode[] }) {
  return (
    <ul className="max-w-3xl space-y-3">
      {items.map((t, i) => (
        <li key={i} className="flex gap-3 text-[14px] leading-relaxed text-silver">
          <span className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-ice/70" />
          <span>{t}</span>
        </li>
      ))}
    </ul>
  );
}

/** Sub-heading inside a module section. */
export function Sub({ title, children, note }: { title: string; children: ReactNode; note?: ReactNode }) {
  return (
    <div className="mt-12 first:mt-0">
      <h3 className="font-display text-lg text-glacial">{title}</h3>
      {note && <p className="mt-1 text-[12.5px] text-muted">{note}</p>}
      <div className="mt-5">{children}</div>
    </div>
  );
}
