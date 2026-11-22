"use client";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

export const CHAPTERS = [
  { id: "earth", label: "Discover Earth" },
  { id: "cryosphere", label: "The cryosphere" },
  { id: "journey", label: "Journey south" },
  { id: "continent", label: "The continent" },
  { id: "data", label: "The data" },
  { id: "platform", label: "Machine intelligence" },
  { id: "research", label: "Research & method" },
] as const;

/** Documentary-style chapter index (desktop only). Native scrolling; clicking jumps to the chapter anchor. */
export function ChapterRail() {
  const [active, setActive] = useState(0);
  const [show, setShow] = useState(false);

  useEffect(() => {
    const els = CHAPTERS.map((c) => document.getElementById(c.id)).filter((e): e is HTMLElement => !!e);
    const on = () => {
      const mid = window.innerHeight * 0.5;
      let idx = 0;
      els.forEach((el, i) => {
        if (el.getBoundingClientRect().top <= mid) idx = i;
      });
      setActive(idx);
      setShow(window.scrollY > window.innerHeight * 0.35);
    };
    on();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => {
      window.removeEventListener("scroll", on);
      window.removeEventListener("resize", on);
    };
  }, []);

  return (
    <nav
      aria-label="Chapters"
      className={cn(
        "fixed left-5 top-1/2 z-40 hidden -translate-y-1/2 transition-opacity duration-500 2xl:block",
        show ? "opacity-100" : "pointer-events-none opacity-0",
      )}
    >
      <ol className="space-y-3">
        {CHAPTERS.map((c, i) => (
          <li key={c.id}>
            <a href={`#${c.id}`} className="group flex items-center gap-3" aria-current={i === active ? "step" : undefined}>
              <span className={cn("h-px transition-all duration-500", i === active ? "w-8 bg-cyan" : "w-4 bg-line-strong group-hover:w-6 group-hover:bg-ice-dim")} />
              <span
                className={cn(
                  "font-mono text-[10px] uppercase tracking-[0.18em] transition-all duration-500",
                  i === active ? "text-glacial opacity-100" : "text-muted opacity-0 group-hover:opacity-100",
                )}
              >
                {String(i + 1).padStart(2, "0")} {c.label}
              </span>
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
