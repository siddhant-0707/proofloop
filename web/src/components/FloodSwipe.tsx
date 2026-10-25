"use client";

// Before/after: the map as it was on the pass before the storm left of a draggable divider, and
// with the flooding the radar flagged on the pass after it to the right. Every other layer shows
// on both sides. Flooding is found from the change between the passes, so the map before has
// none of its own. Zoomed out, the flood surface is redrawn into a canvas cut at the divider;
// close in, `onDivider` gets the divider's longitude so the cells left of it can be filtered out.

import type maplibregl from "maplibre-gl";
import type { CanvasSource, PropertyValueSpecification } from "maplibre-gl";
import { useEffect, useRef } from "react";

import type { HazardLayerInfo } from "@/lib/api";

/** Drawn in place of the flood surface while comparing. */
export const SWIPE_LAYER = "flood-swipe";
const SURFACE_LAYER = "flood-surface";
// The divider stops short of the map's edges, so its handle stays in reach.
const MIN_SPLIT = 0.03;
const KEY_STEP = 0.02;

/** Draws the swipe on `map` while `on`; `split` is the divider's place across the map, 0 to 1.
 * `onDivider` gets its longitude when it or the map stops moving, and null once it is off. */
export function useFloodSwipe(
  map: maplibregl.Map | null,
  info: HazardLayerInfo | null,
  on: boolean,
  split: number,
  onDivider: (lng: number | null) => void,
) {
  const image = useRef<Promise<HTMLImageElement> | null>(null);
  const splitRef = useRef(split);
  splitRef.current = split;
  const onDividerRef = useRef(onDivider);
  onDividerRef.current = onDivider;
  const redraw = useRef<(() => void) | null>(null);

  const url = info?.surface_url;
  const bounds = info?.bounds;
  useEffect(() => {
    if (!map || !on || !url || !bounds || !map.getLayer(SURFACE_LAYER)) return;
    let cancelled = false;
    const { west, south, east, north } = bounds;
    const canvas = document.createElement("canvas");
    const dividerLng = () => map.unproject([map.getContainer().clientWidth * splitRef.current, 0]).lng;
    const draw = (surface: HTMLImageElement) => {
      const source = map.getSource<CanvasSource>(SWIPE_LAYER);
      const context = canvas.getContext("2d");
      if (!source || !context) return;
      // The image is evenly spaced in longitude, so the divider falls on one column.
      const share = (dividerLng() - west) / (east - west);
      const { width, height } = canvas;
      const col = Math.round(Math.min(1, Math.max(0, share)) * width);
      context.clearRect(0, 0, width, height);
      if (col < width) context.drawImage(surface, col, 0, width - col, height, col, 0, width - col, height);
      // Uploads the canvas once and repaints, rather than every frame.
      source.play();
      source.pause();
    };
    const settle = () => onDividerRef.current(dividerLng());

    image.current ??= loadImage(url);
    let onMove: (() => void) | null = null;
    image.current
      .then((surface) => {
        if (cancelled) return;
        canvas.width = surface.naturalWidth;
        canvas.height = surface.naturalHeight;
        map.addSource(SWIPE_LAYER, {
          type: "canvas",
          canvas,
          animate: false,
          coordinates: [
            [west, north],
            [east, north],
            [east, south],
            [west, south],
          ],
        });
        // Same look and zoom range as the flood surface, in its place in the layer order.
        const layers = map.getStyle().layers;
        const above = layers[layers.findIndex((l) => l.id === SURFACE_LAYER) + 1]?.id;
        const surfaceLayer = map.getLayer(SURFACE_LAYER);
        map.addLayer(
          {
            id: SWIPE_LAYER,
            type: "raster",
            source: SWIPE_LAYER,
            maxzoom: surfaceLayer?.maxzoom ?? 24,
            layout: {
              visibility: map.getLayoutProperty(SURFACE_LAYER, "visibility") ?? "visible",
            },
            paint: {
              "raster-fade-duration": 0,
              "raster-resampling": "linear",
              "raster-opacity": (map.getPaintProperty(SURFACE_LAYER, "raster-opacity") ??
                1) as PropertyValueSpecification<number>,
            },
          },
          above,
        );
        map.setLayoutProperty(SURFACE_LAYER, "visibility", "none");
        onMove = () => draw(surface);
        redraw.current = () => {
          draw(surface);
          settle();
        };
        redraw.current();
        map.on("move", onMove);
        map.on("resize", onMove);
        map.on("moveend", settle);
      })
      .catch(() => {
        image.current = null;
      });

    return () => {
      cancelled = true;
      redraw.current = null;
      if (onMove) {
        map.off("move", onMove);
        map.off("resize", onMove);
        map.off("moveend", settle);
      }
      try {
        if (map.getLayer(SWIPE_LAYER)) {
          map.setLayoutProperty(
            SURFACE_LAYER,
            "visibility",
            map.getLayoutProperty(SWIPE_LAYER, "visibility") ?? "visible",
          );
          map.removeLayer(SWIPE_LAYER);
        }
        if (map.getSource(SWIPE_LAYER)) map.removeSource(SWIPE_LAYER);
        onDividerRef.current(null);
      } catch {
        // The map was already removed with the page.
      }
    };
  }, [map, on, url, bounds]);

  useEffect(() => redraw.current?.(), [split]);
}

/** The divider over the map: drag it (or its handle, or use the arrow keys) to move the split. */
export function SwipeDivider({ split, onSplit }: { split: number; onSplit: (split: number) => void }) {
  const area = useRef<HTMLDivElement>(null);
  const clamp = (s: number) => Math.min(1 - MIN_SPLIT, Math.max(MIN_SPLIT, s));
  const follow = (e: React.PointerEvent) => {
    const box = area.current?.getBoundingClientRect();
    if (box && e.currentTarget.hasPointerCapture(e.pointerId)) {
      onSplit(clamp((e.clientX - box.left) / box.width));
    }
  };
  const grab = {
    onPointerDown: (e: React.PointerEvent) => {
      e.currentTarget.setPointerCapture(e.pointerId);
      e.stopPropagation();
    },
    onPointerMove: follow,
  };
  return (
    // No z-index: it stays under the screens laid over the map and the map's own controls.
    <div ref={area} className="pointer-events-none absolute inset-0">
      {/* Each label stays on its own side of the map, shortened when that side is narrow. */}
      <div className="absolute inset-x-0 top-[62%] flex -translate-y-9 text-[11px] font-medium text-white">
        <div className="flex min-w-0 justify-end pr-6" style={{ width: `${split * 100}%` }}>
          <span className="truncate rounded-md bg-slate-900/85 px-2 py-0.5">Before · Sep 28</span>
        </div>
        <div className="flex min-w-0 flex-1 pl-6">
          <span className="truncate rounded-md bg-sky-800/90 px-2 py-0.5">After · Oct 10 · flooding</span>
        </div>
      </div>
      <div className="absolute inset-y-0" style={{ left: `${split * 100}%` }}>
        {/* A wider strip than the line, so it is easy to catch. */}
        <div {...grab} className="pointer-events-auto absolute inset-y-0 -left-3 w-6 cursor-ew-resize touch-none">
          <div className="mx-auto h-full w-0.5 bg-slate-900/70 shadow-[0_0_0_1px_rgba(255,255,255,0.8)]" />
        </div>
        <div className="absolute top-[62%] -translate-y-1/2">
          <div
            {...grab}
            role="slider"
            tabIndex={0}
            aria-label="Before and after the storm: drag to compare"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(split * 100)}
            onKeyDown={(e) => {
              if (e.key === "ArrowLeft") onSplit(clamp(split - KEY_STEP));
              if (e.key === "ArrowRight") onSplit(clamp(split + KEY_STEP));
            }}
            className="pointer-events-auto absolute flex size-10 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize touch-none items-center justify-center rounded-full bg-white text-slate-700 shadow-lg ring-1 ring-slate-300 focus:ring-2 focus:ring-sky-500 focus:outline-none"
          >
            <svg viewBox="0 0 20 20" className="size-5" aria-hidden>
              <path
                d="M7 5l-4 5 4 5M13 5l4 5-4 5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
}

function loadImage(url: string): Promise<HTMLImageElement> {
  const image = new Image();
  image.src = url;
  return image.decode().then(() => image);
}
