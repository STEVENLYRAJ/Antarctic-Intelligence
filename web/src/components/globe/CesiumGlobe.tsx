"use client";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import type * as CesiumNS from "cesium";

import { loadCesium, type Cesium } from "@/lib/cesium/load";

export interface CameraState {
  lat: number;
  lon: number;
  height: number;
  heading: number;
  pitch: number;
}

export interface Overlay {
  id: string;
  url: string;
  bounds: { west: number; south: number; east: number; north: number };
  alpha?: number;
}

export interface GlobeHandle {
  flyTo: (lat: number, lon: number, height: number, duration?: number) => void;
  setView: (lat: number, lon: number, height: number, pitchDeg?: number) => void;
  zoom: (factor: number) => void;
  resetNorth: () => void;
}

interface Props {
  className?: string;
  interactive?: boolean;
  overlays?: Overlay[];
  /** NASA GIBS daily true-colour date (YYYY-MM-DD) or null to hide. */
  trueColorDate?: string | null;
  showGraticule?: boolean;
  initial?: { lat: number; lon: number; height: number };
  onCamera?: (c: CameraState) => void;
  /** Geographic position under the mouse pointer (null when the pointer is off the globe). */
  onPointer?: (p: { lat: number; lon: number } | null) => void;
  onReady?: () => void;
  onFallback?: (reason: string) => void;
  autoRotate?: boolean;
}

const GIBS = "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best";

/**
 * GIBS EPSG:4326 pyramid: 512 px tiles anchored at (-180, 90); a level-0 tile spans 288 deg, so level n has
 * ceil(1.25 * 2^n) x ceil(0.625 * 2^n) real tiles. Equivalent to a doubling scheme over (-180..396, -198..90).
 */
function gibsScheme(C: Cesium) {
  return new C.GeographicTilingScheme({
    rectangle: C.Rectangle.fromDegrees(-180, -198, 396, 90),
    numberOfLevelZeroTilesX: 2,
    numberOfLevelZeroTilesY: 1,
  });
}

function hasWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

/**
 * Single CesiumJS viewer. Imagery: NASA GIBS Blue Marble (public domain, no token) over Cesium's bundled
 * Natural Earth II (offline fallback). Terrain: Cesium World Terrain only when NEXT_PUBLIC_CESIUM_ION_TOKEN is set.
 */
export const CesiumGlobe = forwardRef<GlobeHandle, Props>(function CesiumGlobe(
  { className, interactive = true, overlays = [], trueColorDate = null, showGraticule = false, initial, onCamera, onPointer, onReady, onFallback, autoRotate = false },
  ref,
) {
  const host = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<CesiumNS.Viewer | null>(null);
  const CRef = useRef<Cesium | null>(null);
  const overlayLayers = useRef<Map<string, CesiumNS.ImageryLayer>>(new Map());
  const trueColorLayer = useRef<CesiumNS.ImageryLayer | null>(null);
  const gridRef = useRef<CesiumNS.Entity[]>([]);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const cbs = useRef({ onCamera, onPointer, onReady, onFallback });
  cbs.current = { onCamera, onPointer, onReady, onFallback };

  /* ---------- init / dispose ---------- */
  useEffect(() => {
    let disposed = false;
    const layers = overlayLayers.current;
    if (!hasWebGL()) {
      setFailed("WebGL is not available in this browser");
      cbs.current.onFallback?.("webgl");
      return;
    }
    if (!document.getElementById("cesium-widgets-css")) {
      const l = document.createElement("link");
      l.id = "cesium-widgets-css";
      l.rel = "stylesheet";
      l.href = "/cesium/Widgets/widgets.css";
      document.head.appendChild(l);
    }
    (async () => {
      const C = await loadCesium();
      if (disposed || !host.current) return;
      CRef.current = C;
      const token = process.env.NEXT_PUBLIC_CESIUM_ION_TOKEN;
      C.Ion.defaultAccessToken = token || "";
      try {
        const ne = await C.TileMapServiceImageryProvider.fromUrl(C.buildModuleUrl("Assets/Textures/NaturalEarthII"));
        if (disposed || !host.current) return;
        const viewer = new C.Viewer(host.current, {
          baseLayer: new C.ImageryLayer(ne),
          baseLayerPicker: false,
          geocoder: false,
          homeButton: false,
          sceneModePicker: false,
          navigationHelpButton: false,
          animation: false,
          timeline: false,
          fullscreenButton: false,
          infoBox: false,
          selectionIndicator: false,
          requestRenderMode: true,
          maximumRenderTimeChange: Infinity,
          msaaSamples: 4,
        });
        viewerRef.current = viewer;
        const blue = new C.WebMapTileServiceImageryProvider({
          url: `${GIBS}/BlueMarble_ShadedRelief_Bathymetry/default/{TileMatrixSet}/{TileMatrix}/{TileRow}/{TileCol}.jpeg`,
          layer: "BlueMarble_ShadedRelief_Bathymetry",
          style: "default",
          format: "image/jpeg",
          tileMatrixSetID: "500m",
          maximumLevel: 7, // 500m matrix set: levels 0-7
          tilingScheme: gibsScheme(C),
          rectangle: C.Rectangle.fromDegrees(-180, -90, 180, 90),
          tileWidth: 512, // GIBS EPSG:4326 tiles are 512 px
          tileHeight: 512,
          credit: new C.Credit("NASA Blue Marble · GIBS"),
        });
        viewer.imageryLayers.addImageryProvider(blue);

        if (token) {
          try {
            viewer.terrainProvider = await C.createWorldTerrainAsync();
          } catch {
            /* ellipsoid fallback */
          }
        }
        const scene = viewer.scene;
        scene.backgroundColor = C.Color.fromCssColorString("#05080d");
        if (scene.skyAtmosphere) scene.skyAtmosphere.show = true;
        scene.globe.showGroundAtmosphere = true;
        scene.globe.enableLighting = false;
        scene.globe.baseColor = C.Color.fromCssColorString("#0b1f33");
        scene.fog.enabled = true;
        if (scene.skyBox) scene.skyBox.show = false;
        if (scene.sun) scene.sun.show = false;
        if (scene.moon) scene.moon.show = false;
        scene.globe.maximumScreenSpaceError = 1.5;
        const ctl = scene.screenSpaceCameraController;
        ctl.enableInputs = interactive;
        ctl.minimumZoomDistance = 50_000;
        ctl.maximumZoomDistance = 40_000_000;
        (viewer.cesiumWidget.creditContainer as HTMLElement).style.display = interactive ? "" : "none";

        const init = initial ?? { lat: -15, lon: 20, height: 24_000_000 };
        viewer.camera.setView({ destination: C.Cartesian3.fromDegrees(init.lon, init.lat, init.height) });

        const report = () => {
          const c = viewer.camera.positionCartographic;
          cbs.current.onCamera?.({
            lat: C.Math.toDegrees(c.latitude),
            lon: C.Math.toDegrees(c.longitude),
            height: c.height,
            heading: C.Math.toDegrees(viewer.camera.heading),
            pitch: C.Math.toDegrees(viewer.camera.pitch),
          });
        };
        viewer.camera.changed.addEventListener(report);
        viewer.camera.percentageChanged = 0.01;
        report();
        // requestRenderMode only redraws on demand: force the first frames while imagery streams in.
        scene.requestRender();
        const kick = window.setInterval(() => !viewer.isDestroyed() && viewer.scene.requestRender(), 500);
        window.setTimeout(() => window.clearInterval(kick), 8000);
        viewer.scene.globe.tileLoadProgressEvent.addEventListener(() => viewer.scene.requestRender());
        const handler = new C.ScreenSpaceEventHandler(viewer.scene.canvas);
        handler.setInputAction((m: { endPosition: CesiumNS.Cartesian2 }) => {
          if (!cbs.current.onPointer) return;
          const cart = viewer.camera.pickEllipsoid(m.endPosition, viewer.scene.globe.ellipsoid);
          if (!cart) return cbs.current.onPointer(null);
          const g = C.Cartographic.fromCartesian(cart);
          cbs.current.onPointer({ lat: C.Math.toDegrees(g.latitude), lon: C.Math.toDegrees(g.longitude) });
        }, C.ScreenSpaceEventType.MOUSE_MOVE);
        setReady(true);
        cbs.current.onReady?.();
      } catch (e) {
        setFailed(e instanceof Error ? e.message : "Globe failed to initialise");
        cbs.current.onFallback?.("init");
      }
    })();
    return () => {
      disposed = true;
      layers.clear();
      trueColorLayer.current = null;
      gridRef.current = [];
      if (viewerRef.current && !viewerRef.current.isDestroyed()) viewerRef.current.destroy();
      viewerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---------- interactivity toggle ---------- */
  useEffect(() => {
    const v = viewerRef.current;
    if (v) v.scene.screenSpaceCameraController.enableInputs = interactive;
  }, [interactive, ready]);

  /* ---------- auto rotate (hero only) ---------- */
  useEffect(() => {
    const v = viewerRef.current;
    const C = CRef.current;
    if (!v || !C || !autoRotate) return;
    const remove = v.clock.onTick.addEventListener(() => v.scene.camera.rotate(C.Cartesian3.UNIT_Z, 0.0006));
    v.clock.shouldAnimate = true;
    v.scene.requestRenderMode = false;
    return () => {
      remove();
      if (!v.isDestroyed()) v.scene.requestRenderMode = true;
    };
  }, [autoRotate, ready]);

  /* ---------- data overlays ---------- */
  useEffect(() => {
    const v = viewerRef.current;
    const C = CRef.current;
    if (!v || !C) return;
    const want = new Map(overlays.map((o) => [o.id + o.url, o]));
    for (const [k, layer] of overlayLayers.current) {
      if (!want.has(k)) {
        v.imageryLayers.remove(layer, true);
        overlayLayers.current.delete(k);
      }
    }
    let cancelled = false;
    (async () => {
      for (const [k, o] of want) {
        if (overlayLayers.current.has(k)) {
          overlayLayers.current.get(k)!.alpha = o.alpha ?? 0.9;
          continue;
        }
        try {
          const p = await C.SingleTileImageryProvider.fromUrl(o.url, {
            rectangle: C.Rectangle.fromDegrees(o.bounds.west, o.bounds.south, o.bounds.east, o.bounds.north),
          });
          if (cancelled || v.isDestroyed()) return;
          const layer = v.imageryLayers.addImageryProvider(p);
          layer.alpha = o.alpha ?? 0.9;
          overlayLayers.current.set(k, layer);
        } catch {
          /* missing layer: ignored; the panel shows the error state */
        }
      }
      if (!v.isDestroyed()) v.scene.requestRender();
    })();
    return () => {
      cancelled = true;
    };
  }, [overlays, ready]);

  /* ---------- GIBS daily true colour ---------- */
  useEffect(() => {
    const v = viewerRef.current;
    const C = CRef.current;
    if (!v || !C) return;
    if (trueColorLayer.current) {
      v.imageryLayers.remove(trueColorLayer.current, true);
      trueColorLayer.current = null;
    }
    if (trueColorDate) {
      const p = new C.WebMapTileServiceImageryProvider({
        url: `${GIBS}/MODIS_Terra_CorrectedReflectance_TrueColor/default/${trueColorDate}/{TileMatrixSet}/{TileMatrix}/{TileRow}/{TileCol}.jpg`,
        layer: "MODIS_Terra_CorrectedReflectance_TrueColor",
        style: "default",
        format: "image/jpeg",
        tileMatrixSetID: "250m",
        maximumLevel: 8,
        tilingScheme: gibsScheme(C),
          rectangle: C.Rectangle.fromDegrees(-180, -90, 180, 90),
          tileWidth: 512, // GIBS EPSG:4326 tiles are 512 px
          tileHeight: 512,
        credit: new C.Credit(`NASA MODIS Terra true colour ${trueColorDate} · GIBS`),
      });
      const layer = v.imageryLayers.addImageryProvider(p, 2);
      trueColorLayer.current = layer;
    }
    v.scene.requestRender();
  }, [trueColorDate, ready]);

  /* ---------- graticule ---------- */
  useEffect(() => {
    const v = viewerRef.current;
    const C = CRef.current;
    if (!v || !C) return;
    gridRef.current.forEach((e) => v.entities.remove(e));
    gridRef.current = [];
    if (showGraticule) {
      const mat = C.Color.fromCssColorString("#8ddcf4").withAlpha(0.28);
      for (const lat of [-50, -60, -66.5633, -70, -80]) {
        const pts: number[] = [];
        for (let lon = -180; lon <= 180; lon += 2) pts.push(lon, lat);
        gridRef.current.push(
          v.entities.add({
            polyline: { positions: C.Cartesian3.fromDegreesArray(pts), width: lat === -66.5633 ? 1.6 : 1, material: lat === -66.5633 ? C.Color.fromCssColorString("#48c8e8").withAlpha(0.6) : mat, arcType: C.ArcType.RHUMB },
          }),
        );
      }
      for (let lon = -180; lon < 180; lon += 30) {
        gridRef.current.push(
          v.entities.add({ polyline: { positions: C.Cartesian3.fromDegreesArray([lon, -50, lon, -89.9]), width: 1, material: mat } }),
        );
      }
    }
    v.scene.requestRender();
  }, [showGraticule, ready]);

  /* ---------- imperative API ---------- */
  useImperativeHandle(
    ref,
    () => ({
      flyTo: (lat, lon, height, duration = 2.6) => {
        const v = viewerRef.current;
        const C = CRef.current;
        if (!v || !C) return;
        const polar = lat <= -85;
        v.camera.flyTo({
          destination: C.Cartesian3.fromDegrees(lon, polar ? -89.99 : lat - Math.min(14, height / 400_000), height),
          orientation: { heading: 0, pitch: C.Math.toRadians(polar ? -90 : -62), roll: 0 },
          duration,
          easingFunction: C.EasingFunction.QUINTIC_IN_OUT,
        });
      },
      setView: (lat, lon, height, pitchDeg = -90) => {
        const v = viewerRef.current;
        const C = CRef.current;
        if (!v || !C) return;
        v.camera.setView({
          destination: C.Cartesian3.fromDegrees(lon, lat, height),
          orientation: { heading: 0, pitch: C.Math.toRadians(pitchDeg), roll: 0 },
        });
        v.scene.requestRender();
      },
      zoom: (factor) => {
        const v = viewerRef.current;
        if (!v) return;
        const h = v.camera.positionCartographic.height;
        if (factor > 1) v.camera.zoomIn(h * (1 - 1 / factor));
        else v.camera.zoomOut(h * (1 / factor - 1));
        v.scene.requestRender();
      },
      resetNorth: () => {
        const v = viewerRef.current;
        const C = CRef.current;
        if (!v || !C) return;
        const c = v.camera.positionCartographic;
        v.camera.flyTo({ destination: C.Cartesian3.fromRadians(c.longitude, c.latitude, c.height), orientation: { heading: 0, pitch: C.Math.toRadians(-90), roll: 0 }, duration: 1 });
      },
    }),
    [],
  );

  if (failed) {
    return (
      <div className={className}>
        <div className="flex h-full w-full flex-col items-center justify-center gap-4 bg-[radial-gradient(circle_at_50%_60%,#12304d,#05080d_70%)] p-8 text-center">
          <p className="t-meta">3D globe unavailable</p>
          <p className="max-w-md text-sm text-silver">{failed}. The scientific layers are still available as 2D maps on each model page.</p>
        </div>
      </div>
    );
  }
  return (
    <div className={className}>
      <div ref={host} className="h-full w-full" />
      {!ready && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">Initialising globe…</span>
        </div>
      )}
    </div>
  );
});
