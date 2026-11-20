"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, ChevronDown, Menu, X } from "lucide-react";
import { MODELS, NAV } from "@/config/site";
import { cn } from "@/lib/utils";

export function Nav() {
  const pathname = usePathname();
  const [solid, setSolid] = useState(false);
  const [open, setOpen] = useState(false);
  const [mega, setMega] = useState(false);
  const [hidden, setHidden] = useState(false);
  const closeT = useRef<number | undefined>(undefined);
  const megaRef = useRef<HTMLElement>(null);

  useEffect(() => {
    let last = window.scrollY;
    const on = () => {
      const y = window.scrollY;
      setSolid(y > 24);
      // hide on fast downward scroll deep in long pages, reveal on any upward scroll
      setHidden(y > 600 && y > last + 4);
      if (y < last - 2) setHidden(false);
      last = y;
    };
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  useEffect(() => {
    setOpen(false);
    setMega(false);
  }, [pathname]);
  useEffect(() => {
    if (!mega) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setMega(false);
    const out = (e: PointerEvent) => !megaRef.current?.contains(e.target as Node) && setMega(false);
    window.addEventListener("keydown", esc);
    window.addEventListener("pointerdown", out);
    return () => {
      window.removeEventListener("keydown", esc);
      window.removeEventListener("pointerdown", out);
    };
  }, [mega]);

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const onExplore = pathname.startsWith("/explore");
  const enter = () => {
    window.clearTimeout(closeT.current);
    setMega(true);
  };
  const leave = () => {
    closeT.current = window.setTimeout(() => setMega(false), 160);
  };

  return (
    <header
      ref={megaRef}
      className={cn(
        "fixed inset-x-0 top-0 z-50 transition-[background,border-color,transform] duration-500",
        solid || onExplore || open || mega ? "border-b border-line bg-polar/80 backdrop-blur-md" : "border-b border-transparent",
        hidden && !open && !mega && !onExplore ? "-translate-y-full" : "translate-y-0",
      )}
    >
      <div className="container-x flex h-16 items-center justify-between gap-6">
        <Link href="/" className="group flex items-center gap-3" aria-label="AETHENTRA home">
          <Logo />
          <span className="font-display text-[15px] font-medium tracking-[0.28em] text-glacial">AETHENTRA</span>
        </Link>
        <nav aria-label="Primary" className="hidden lg:block">
          <ul className="flex items-center gap-0.5">
            {NAV.map((n) =>
              "mega" in n ? (
                <li key={n.href} className="relative" onPointerEnter={enter} onPointerLeave={leave}>
                  <button
                    aria-expanded={mega}
                    aria-controls="mega-models"
                    onClick={() => setMega((m) => !m)}
                    className={cn(
                      "relative flex items-center gap-1 rounded px-3 py-2 text-[13px] transition-colors",
                      isActive(n.href) || mega ? "text-glacial" : "text-silver hover:text-glacial",
                    )}
                  >
                    {n.label}
                    <ChevronDown size={13} className={cn("transition-transform duration-300", mega && "rotate-180")} />
                    {isActive(n.href) && <span className="absolute inset-x-3 -bottom-[1px] h-px bg-cyan" />}
                  </button>
                </li>
              ) : (
                <li key={n.href}>
                  <Link
                    href={n.href}
                    aria-current={isActive(n.href) ? "page" : undefined}
                    className={cn("relative rounded px-3 py-2 text-[13px] transition-colors", isActive(n.href) ? "text-glacial" : "text-silver hover:text-glacial")}
                  >
                    {n.label}
                    {isActive(n.href) && <span className="absolute inset-x-3 -bottom-[1px] h-px bg-cyan" />}
                  </Link>
                </li>
              ),
            )}
          </ul>
        </nav>
        <div className="flex items-center gap-3">
          <span className="hidden items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-muted xl:flex">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan opacity-50" />
              <span className="relative h-1.5 w-1.5 rounded-full bg-cyan" />
            </span>
            Phase 1 · Antarctica
          </span>
          <Link href="/explore" className="hidden rounded-full border border-line-strong px-4 py-1.5 text-[12px] text-glacial transition-colors hover:border-cyan hover:text-cyan md:inline-flex lg:hidden xl:inline-flex">
            Launch explorer
          </Link>
          <button
            className="rounded p-2 text-silver hover:text-glacial lg:hidden"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            onClick={() => setOpen((o) => !o)}
          >
            {open ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      {/* Mega menu: ML modules */}
      <div
        id="mega-models"
        onPointerEnter={enter}
        onPointerLeave={leave}
        className={cn(
          "absolute inset-x-0 top-16 hidden border-b border-line bg-polar/95 backdrop-blur-xl transition-[opacity,transform] duration-300 lg:block",
          mega ? "pointer-events-auto translate-y-0 opacity-100" : "pointer-events-none -translate-y-2 opacity-0",
        )}
        aria-hidden={!mega}
      >
        <div className="container-x grid grid-cols-[1fr_3fr] gap-10 py-8">
          <div>
            <p className="t-meta">Machine-learning intelligence</p>
            <p className="mt-3 text-sm leading-relaxed text-silver">Four Antarctic models, each trained on a strictly time-ordered split and served through the AETHENTRA API.</p>
            <Link href="/models" tabIndex={mega ? 0 : -1} className="mt-5 inline-flex items-center gap-2 text-[13px] text-cyan hover:text-glacial">
              All models <ArrowUpRight size={14} />
            </Link>
          </div>
          <ul className="grid grid-cols-4 gap-3">
            {MODELS.map((m) => (
              <li key={m.slug}>
                <Link
                  href={`/models/${m.slug}`}
                  tabIndex={mega ? 0 : -1}
                  className={cn(
                    "group block h-full rounded-[var(--radius)] border border-line p-4 transition-colors hover:border-line-strong hover:bg-navy/50",
                    pathname === `/models/${m.slug}` && "border-line-strong bg-navy/40",
                  )}
                >
                  <span className="flex items-center justify-between font-mono text-[10px] tracking-[0.16em]" style={{ color: m.accent }}>
                    {m.code}
                    <ArrowUpRight size={13} className="text-muted transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-glacial" />
                  </span>
                  <span className="mt-3 block font-display text-[15px] leading-snug text-glacial">{m.name}</span>
                  <span className="mt-2 block text-[12px] leading-relaxed text-muted">{m.short}</span>
                  <span className="mt-4 block h-px w-full origin-left scale-x-0 transition-transform duration-500 group-hover:scale-x-100" style={{ background: m.accent }} />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {open && (
        <nav aria-label="Mobile" className="max-h-[calc(100dvh-4rem)] overflow-y-auto border-t border-line lg:hidden" data-lenis-prevent>
          <ul className="container-x flex flex-col py-3">
            {NAV.map((n) => (
              <li key={n.href}>
                <Link href={n.href} className={cn("block py-3 font-display text-2xl", isActive(n.href) ? "text-cyan" : "text-glacial")}>
                  {n.label}
                </Link>
                {"mega" in n && (
                  <ul className="mb-2 grid grid-cols-2 gap-2">
                    {MODELS.map((m) => (
                      <li key={m.slug}>
                        <Link href={`/models/${m.slug}`} className="block rounded border border-line px-3 py-2.5 text-[13px] text-silver">
                          <span className="font-mono text-[10px]" style={{ color: m.accent }}>
                            {m.code}
                          </span>
                          <span className="block text-glacial">{m.name}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </nav>
      )}
    </header>
  );
}

export function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="10.5" stroke="var(--ice)" strokeOpacity="0.55" />
      <ellipse cx="12" cy="12" rx="10.5" ry="4" stroke="var(--ice)" strokeOpacity="0.35" />
      <path d="M12 1.5 L12 22.5" stroke="var(--ice)" strokeOpacity="0.25" />
      <circle cx="12" cy="19.2" r="2.6" fill="var(--cyan)" />
    </svg>
  );
}
