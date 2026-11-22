"use client";
import { useLayoutEffect, useRef, type ElementType, type ReactNode } from "react";
import { getGsap, prefersReducedMotion } from "@/lib/animations/gsap";
import { cn } from "@/lib/utils";

/**
 * Line-by-line masked text reveal. Each line of `lines` is wrapped in an overflow mask and slides up.
 * `trigger="scroll"` plays when the block enters the viewport; `"mount"` plays immediately.
 */
export function SplitReveal({
  lines,
  as: Tag = "h2",
  className,
  trigger = "scroll",
  delay = 0,
  stagger = 0.09,
}: {
  lines: ReactNode[];
  as?: ElementType;
  className?: string;
  trigger?: "scroll" | "mount";
  delay?: number;
  stagger?: number;
}) {
  const ref = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    if (!ref.current || prefersReducedMotion()) return;
    const { gsap } = getGsap();
    const ctx = gsap.context(() => {
      const inner = ref.current!.querySelectorAll(".split-inner");
      gsap.set(inner, { yPercent: 110 });
      gsap.to(inner, {
        yPercent: 0,
        duration: 1.15,
        ease: "expo.out",
        stagger,
        delay,
        scrollTrigger: trigger === "scroll" ? { trigger: ref.current, start: "top 85%", once: true } : undefined,
      });
    }, ref);
    return () => ctx.revert();
  }, [trigger, delay, stagger]);
  return (
    <Tag ref={ref} className={className}>
      {lines.map((l, i) => (
        <span key={i} className="split-line">
          <span className="split-inner">{l}</span>
        </span>
      ))}
    </Tag>
  );
}

/** Fade + rise on scroll for any block. Children with [data-reveal] are staggered. */
export function Reveal({ children, className, y = 28, stagger = 0.08 }: { children: ReactNode; className?: string; y?: number; stagger?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!ref.current || prefersReducedMotion()) return;
    const { gsap } = getGsap();
    const ctx = gsap.context(() => {
      const items = ref.current!.querySelectorAll("[data-reveal]");
      const targets = items.length ? items : [ref.current!];
      gsap.from(targets, {
        y,
        autoAlpha: 0,
        duration: 1,
        ease: "power3.out",
        stagger,
        scrollTrigger: { trigger: ref.current, start: "top 85%", once: true },
      });
    }, ref);
    return () => ctx.revert();
  }, [y, stagger]);
  return (
    <div ref={ref} className={cn(className)}>
      {children}
    </div>
  );
}

/** Number that counts up when scrolled into view. Displays the final value immediately without JS / reduced motion. */
export function CountUp({ value, decimals = 0, suffix = "", className }: { value: number; decimals?: number; suffix?: string; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const format = (v: number) => new Intl.NumberFormat("en-GB", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(v) + suffix;
  useLayoutEffect(() => {
    if (!ref.current || prefersReducedMotion()) return;
    const { gsap } = getGsap();
    const obj = { v: 0 };
    const el = ref.current;
    const tw = gsap.to(obj, {
      v: value,
      duration: 1.6,
      ease: "power2.out",
      onUpdate: () => {
        el.textContent = format(obj.v);
      },
      scrollTrigger: { trigger: el, start: "top 90%", once: true },
    });
    return () => {
      tw.scrollTrigger?.kill();
      tw.kill();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, decimals, suffix]);
  return (
    <span ref={ref} className={className}>
      {format(value)}
    </span>
  );
}
