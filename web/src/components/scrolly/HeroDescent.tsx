"use client";
import dynamic from "next/dynamic";
import { useLayoutEffect, useRef, useState } from "react";
import type { GlobeHandle } from "@/components/globe/CesiumGlobe";
import { getGsap, prefersReducedMotion } from "@/lib/animations/gsap";
import { ButtonLink } from "@/components/ui/primitives";
import { Magnetic, Starfield } from "@/components/ui/interactive";
import { SplitReveal } from "@/components/ui/Reveal";
import { cn } from "@/lib/utils";

const CesiumGlobe = dynamic(() => import("@/components/globe/CesiumGlobe").then((m) => m.CesiumGlobe), { ssr: false });

/** Verified Antarctic context. Each fact carries its source. */
const FACTS = [
  {
    k: "01",
    title: "A continent of ice",
    value: "≈ 14 million km²",
    body: "Antarctica is the fifth-largest continent, about 98 % covered by ice that averages close to 2 km in thickness.",
    src: "British Antarctic Survey",
  },
  {
    k: "02",
    title: "Earth's largest reservoir of fresh water",
    value: "58 m",
    body: "The Antarctic ice sheet holds ice equivalent to roughly 58 m of global sea-level rise if it all melted.",
    src: "Morlighem et al. (2020), Nature Geoscience — BedMachine Antarctica",
  },
  {
    k: "03",
    title: "The coldest place measured",
    value: "−89.2 °C",
    body: "The lowest surface air temperature ever recorded by a station: Vostok, 21 July 1983.",
    src: "World Meteorological Organization, weather & climate extremes archive",
  },
  {
    k: "04",
    title: "An ocean that freezes and thaws",
    value: "×6 seasonal swing",
    body: "Southern Ocean sea ice grows from roughly 3 million km² in February to about 18 million km² in September — one of the largest seasonal changes on Earth's surface.",
    src: "NSIDC Sea Ice Index (G02135)",
  },
];

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

export function HeroDescent() {
  const section = useRef<HTMLElement>(null);
  const globe = useRef<GlobeHandle>(null);
  const hud = useRef<HTMLSpanElement>(null);
  const [ready, setReady] = useState(false);
  const [phase, setPhase] = useState(0);
  const [grid, setGrid] = useState(false);

  useLayoutEffect(() => {
    if (!section.current) return;
    const { gsap, ScrollTrigger } = getGsap();
    const reduced = prefersReducedMotion();
    const ctx = gsap.context(() => {
      // Camera path: Earth from the tropics -> over the Southern Ocean -> straight down onto the South Pole.
      ScrollTrigger.create({
        trigger: section.current,
        start: "top top",
        end: "bottom bottom",
        scrub: reduced ? false : 0.6,
        onUpdate: (st) => {
          const p = st.progress;
          const t = ease(Math.min(1, p / 0.62));
          const lat = lerp(-12, -89.99, t);
          const lon = lerp(25, 0, t);
          const h = lerp(19_500_000, 10_200_000, t);
          globe.current?.setView(lat, lon, h, -90);
          if (hud.current) hud.current.textContent = `${Math.abs(lat).toFixed(2)}° S · ${Math.abs(lon).toFixed(2)}° E · ALT ${Math.round(h / 1000).toLocaleString("en-US")} km`;
          setGrid(p > 0.45);
          setPhase(p < 0.12 ? 0 : Math.min(FACTS.length, 1 + Math.floor(((p - 0.18) / 0.78) * FACTS.length)));
        },
      });
      if (!reduced) {
        gsap.to(".hero-copy", {
          autoAlpha: 0,
          y: -80,
          ease: "none",
          scrollTrigger: { trigger: section.current, start: "top top", end: "12% top", scrub: true },
        });
        gsap.to(".hero-wordmark", {
          yPercent: 40,
          autoAlpha: 0,
          ease: "none",
          scrollTrigger: { trigger: section.current, start: "top top", end: "16% top", scrub: true },
        });
        gsap.fromTo(".hero-stars", { yPercent: 0 }, { yPercent: -12, ease: "none", scrollTrigger: { trigger: section.current, start: "top top", end: "bottom bottom", scrub: true } });
      }
    }, section);
    return () => ctx.revert();
  }, [ready]);

  return (
    <section ref={section} id="top" className="relative h-[520vh]" aria-label="From Earth to Antarctica">
      {/* chapter anchors for the narrative rail */}
      <span id="earth" className="absolute top-0 h-px w-px" aria-hidden />
      <span id="cryosphere" className="absolute top-[22%] h-px w-px" aria-hidden />
      <span id="journey" className="absolute top-[62%] h-px w-px" aria-hidden />

      <div className="sticky top-0 h-dvh w-full overflow-hidden bg-[radial-gradient(ellipse_at_70%_40%,#0b1f33_0%,#081321_35%,#05080d_75%)]">
        <div className="hero-stars absolute inset-0 h-[115%]">
          <Starfield className="h-full w-full" />
        </div>
        <CesiumGlobe
          ref={globe}
          className={cn("absolute inset-0 transition-opacity duration-[1600ms] md:-right-[6%] md:left-[30%]", ready ? "opacity-100" : "opacity-90")}
          interactive={false}
          transparent
          showGraticule={grid}
          initial={{ lat: -12, lon: 25, height: 19_500_000 }}
          onReady={() => setReady(true)}
        />
        {/* atmosphere / vignette */}
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_62%_50%,transparent_38%,rgba(5,8,13,0.5)_70%,#05080d_100%)]" />
        <div className="pointer-events-none absolute inset-y-0 left-0 hidden w-[55%] bg-gradient-to-r from-polar/90 via-polar/40 to-transparent md:block" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-48 bg-gradient-to-t from-polar to-transparent" />
        {/* phones: darken behind the copy so text stays readable over the globe */}
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-polar via-polar/75 to-polar/10 md:hidden" />

        {/* giant wordmark */}
        <p aria-hidden className="hero-wordmark pointer-events-none absolute inset-x-0 bottom-[-2.2vw] select-none whitespace-nowrap text-center font-display text-[14.5vw] font-medium leading-none tracking-[0.02em] text-transparent [-webkit-text-stroke:1px_rgba(141,220,244,0.16)]">
          AETHENTRA
        </p>

        {/* Hero copy */}
        <div className="hero-copy absolute inset-0 flex items-end pb-[16vh] md:items-center md:pb-0">
          <div className="container-x">
            <p className="t-meta mb-7 flex items-center gap-3">
              <span className="text-cyan">AETHENTRA</span>
              <span className="h-px w-10 bg-line-strong" /> Antarctic Scientific Intelligence · Phase 1
            </p>
            <SplitReveal
              as="h1"
              trigger="mount"
              className="max-w-[14ch] font-display text-[clamp(2.9rem,6vw,6.4rem)] font-medium leading-[0.95] tracking-[-0.035em] text-glacial"
              lines={["The intelligence", <span key="l2">of a <span className="t-serif text-ice">changing</span></span>, "planet."]}
            />
            <p className="t-lead mt-8 max-w-[34rem]">
              A scientific intelligence platform exploring Antarctica&apos;s cryosphere through satellite observations, climate data and machine learning.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-4">
              <Magnetic>
                <ButtonLink href="/explore">Explore Antarctica</ButtonLink>
              </Magnetic>
              <ButtonLink href="#platform" variant="ghost">
                Discover the platform
              </ButtonLink>
            </div>
          </div>
        </div>

        {/* Facts that appear during the descent */}
        <div className="absolute inset-0 flex items-center">
          <div className="container-x">
            <ol className="relative max-w-md">
              {FACTS.map((f, i) => (
                <li
                  key={f.k}
                  aria-hidden={phase !== i + 1}
                  className="glass absolute inset-x-0 top-1/2 -translate-y-1/2 rounded-[var(--radius-lg)] p-7 transition-all duration-700"
                  style={{ opacity: phase === i + 1 ? 1 : 0, transform: `translateY(calc(-50% + ${phase === i + 1 ? 0 : phase > i + 1 ? -24 : 24}px))` }}
                >
                  <p className="t-meta">
                    <span className="text-cyan">{f.k}</span> / 04 · {f.title}
                  </p>
                  <p className="t-num mt-4 text-5xl text-glacial">{f.value}</p>
                  <p className="t-body mt-4">{f.body}</p>
                  <p className="mt-5 border-t border-line pt-3 font-mono text-[0.625rem] uppercase tracking-[0.14em] text-muted">Source · {f.src}</p>
                </li>
              ))}
            </ol>
          </div>
        </div>

        {/* telemetry + scroll cue */}
        <div className="absolute inset-x-0 bottom-7 flex items-end justify-between px-[clamp(16px,4vw,40px)] font-mono text-[0.625rem] uppercase tracking-[0.2em] text-muted">
          <span className="hidden flex-col gap-1 md:flex">
            <span className="text-ice-dim">Camera · scroll-driven</span>
            <span ref={hud} className="text-silver">
              12.00° S · 25.00° E · ALT 19,500 km
            </span>
          </span>
          <span className="ml-auto flex items-center gap-3">
            {phase === 0 ? (
              <>
                Scroll to descend <span className="scroll-cue" aria-hidden />
              </>
            ) : (
              <span>{grid ? "Antarctic Circle · 66.56° S" : "Approaching the Southern Ocean"}</span>
            )}
          </span>
        </div>
      </div>
    </section>
  );
}
