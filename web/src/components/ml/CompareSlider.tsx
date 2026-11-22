"use client";
import { useCallback, useRef, useState } from "react";
import { MoveHorizontal } from "lucide-react";

/** Accessible before/after slider: drag, click or use arrow keys. Both images must share the same grid. */
export function CompareSlider({ before, after, beforeLabel, afterLabel, aspect }: { before: string; after: string; beforeLabel: string; afterLabel: string; aspect: number }) {
  const [pos, setPos] = useState(50);
  const box = useRef<HTMLDivElement>(null);
  const drag = useRef(false);
  const move = useCallback((clientX: number) => {
    const r = box.current?.getBoundingClientRect();
    if (!r) return;
    setPos(Math.max(0, Math.min(100, ((clientX - r.left) / r.width) * 100)));
  }, []);
  return (
    <div
      ref={box}
      className="relative w-full cursor-ew-resize select-none overflow-hidden rounded-[var(--radius)] border border-line bg-[#0a1220]"
      style={{ aspectRatio: aspect }}
      onPointerDown={(e) => {
        drag.current = true;
        (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
        move(e.clientX);
      }}
      onPointerMove={(e) => drag.current && move(e.clientX)}
      onPointerUp={() => (drag.current = false)}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={after} alt={afterLabel} className="absolute inset-0 h-full w-full object-contain" draggable={false} />
      <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={before} alt={beforeLabel} className="absolute inset-0 h-full w-full object-contain" draggable={false} />
      </div>
      <div className="pointer-events-none absolute inset-y-0 w-px bg-cyan" style={{ left: `${pos}%` }} />
      <button
        role="slider"
        aria-label="Comparison position"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pos)}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") setPos((p) => Math.max(0, p - 5));
          if (e.key === "ArrowRight") setPos((p) => Math.min(100, p + 5));
        }}
        className="absolute top-1/2 flex h-10 w-10 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-cyan bg-polar/90 text-cyan"
        style={{ left: `${pos}%` }}
      >
        <MoveHorizontal size={16} />
      </button>
      <span className="pointer-events-none absolute left-3 top-3 rounded-sm bg-polar/80 px-2 py-1 font-mono text-[0.625rem] uppercase tracking-[0.14em] text-glacial">{beforeLabel}</span>
      <span className="pointer-events-none absolute right-3 top-3 rounded-sm bg-warn px-2 py-1 font-mono text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-polar">{afterLabel}</span>
    </div>
  );
}
