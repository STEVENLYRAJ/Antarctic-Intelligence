import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { MODELS } from "@/config/site";
import { Footer } from "@/components/layout/Footer";
import { SplitReveal } from "@/components/ui/Reveal";

export interface ModuleSection {
  id: string;
  title: string;
  content: ReactNode;
}

/** Shared layout for the four ML module pages: hero, sticky section index, 10 standard sections, prev/next. */
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

      <div className="container-x grid gap-12 py-16 lg:grid-cols-[200px_1fr]">
        <nav aria-label="On this page" className="hidden lg:block">
          <ol className="sticky top-28 space-y-2 border-l border-line pl-4 text-[13px]">
            {sections.map((s, k) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className="flex gap-2 text-muted transition-colors hover:text-glacial">
                  <span className="font-mono text-[10px] leading-5 text-ice-dim">{String(k + 1).padStart(2, "0")}</span>
                  {s.title}
                </a>
              </li>
            ))}
          </ol>
        </nav>
        <div className="min-w-0 space-y-24">
          {sections.map((s, k) => (
            <section key={s.id} id={s.id} className="scroll-mt-28">
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
