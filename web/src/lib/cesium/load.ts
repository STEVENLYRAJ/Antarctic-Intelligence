"use client";
import type * as CesiumNS from "cesium";

export type Cesium = typeof CesiumNS;

let promise: Promise<Cesium> | null = null;

/**
 * Loads the prebuilt CesiumJS bundle (public/cesium/Cesium.js, copied from node_modules on install) once per page.
 * Using the prebuilt bundle keeps Cesium out of the Next.js compile and avoids its ESM dependency conflicts.
 */
export function loadCesium(): Promise<Cesium> {
  if (typeof window === "undefined") return Promise.reject(new Error("Cesium is browser-only"));
  const w = window as unknown as { Cesium?: Cesium; CESIUM_BASE_URL?: string };
  if (w.Cesium) return Promise.resolve(w.Cesium);
  if (promise) return promise;
  w.CESIUM_BASE_URL = "/cesium";
  promise = new Promise<Cesium>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "/cesium/Cesium.js";
    s.async = true;
    s.onload = () => (w.Cesium ? resolve(w.Cesium) : reject(new Error("Cesium failed to load")));
    s.onerror = () => {
      promise = null;
      reject(new Error("Could not load /cesium/Cesium.js"));
    };
    document.head.appendChild(s);
  });
  return promise;
}
