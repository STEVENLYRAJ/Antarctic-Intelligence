"use client";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

/** Sticky "on this page" index with scroll-spy (native scrolling; no hijacking). */
export function SectionIndex({ sections, accent }: { sections: { id: string; title: string }[]; accent: string }) {
  const [active, setActive] = useState(sections[0]?.id);
  useEffect(() => {
    const els = sections.map((s) => document.getElementById(s.id)).filter((e): e is HTMLElement => !!e);
    const on = () => {
      let cur = els[0]?.id;
      for (const el of els) if (el.getBoundingClientRect().top < window.innerHeight * 0.35) cur = el.id;
      setActive(cur);
    };
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, [sections]);
  return (
    <ol className="sticky top-36 space-y-1 border-l border-line text-[0.8125rem]">
      {sections.map((s, k) => {
        const on = s.id === active;
        return (
          <li key={s.id} className="relative">
            {on && <span className="absolute -left-px top-0 h-full w-px" style={{ background: accent }} />}
            <a href={`#${s.id}`} aria-current={on ? "location" : undefined} className={cn("flex gap-2 py-1 pl-4 transition-colors", on ? "text-glacial" : "text-muted hover:text-silver")}>
              <span className="font-mono text-[0.625rem] leading-5" style={{ color: on ? accent : undefined }}>
                {String(k + 1).padStart(2, "0")}
              </span>
              {s.title}
            </a>
          </li>
        );
      })}
    </ol>
  );
}
