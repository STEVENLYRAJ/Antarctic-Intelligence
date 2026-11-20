"use client";
import { useEffect } from "react";
import Lenis from "lenis";
import { usePathname } from "next/navigation";
import { getGsap, prefersReducedMotion } from "@/lib/animations/gsap";

/**
 * Lenis smooth scrolling driven by the GSAP ticker so ScrollTrigger and Lenis share one clock.
 * Disabled for reduced-motion users and on the /explore route (the globe owns wheel input there).
 */
export function SmoothScroll() {
  const pathname = usePathname();
  useEffect(() => {
    if (prefersReducedMotion() || pathname.startsWith("/explore")) return;
    const { gsap, ScrollTrigger } = getGsap();
    const lenis = new Lenis({ duration: 1.1, smoothWheel: true, wheelMultiplier: 0.9 });
    lenis.on("scroll", ScrollTrigger.update);
    const tick = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);
    const onAnchor = (e: MouseEvent) => {
      const a = (e.target as HTMLElement).closest("a[href^='#']") as HTMLAnchorElement | null;
      if (!a) return;
      const el = document.querySelector(a.getAttribute("href")!);
      if (el) {
        e.preventDefault();
        lenis.scrollTo(el as HTMLElement, { offset: -64 });
      }
    };
    document.addEventListener("click", onAnchor);
    return () => {
      document.removeEventListener("click", onAnchor);
      gsap.ticker.remove(tick);
      lenis.destroy();
    };
  }, [pathname]);
  return null;
}
