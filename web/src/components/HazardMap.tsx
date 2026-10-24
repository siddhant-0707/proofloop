"use client";

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";

import { fetchExposure, fetchHazard, type ExposureInfo, type HazardLayerInfo } from "@/lib/api";

const BASEMAP = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

// Shown only if the hazard layer, which defines the study area, cannot be loaded.
const FLORIDA: [[number, number], [number, number]] = [
  [-87.6, 24.5],
  [-80.0, 31.0],
];

const TOWNS: [string, number, number][] = [
  ["Steinhatchee", -83.388, 29.672],
  ["Horseshoe Beach", -83.287, 29.441],
  ["Cross City", -83.125, 29.635],
  ["Keaton Beach", -83.591, 29.82],
  ["Perry", -83.582, 30.117],
];

const SHELTER_COLOR = "#047857";

export default function HazardMap() {
  const container = useRef<HTMLDivElement>(null);
  const [info, setInfo] = useState<HazardLayerInfo | null>(null);
  const [exposure, setExposure] = useState<ExposureInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let map: maplibregl.Map | null = null;
    let cancelled = false;

    (async () => {
      let hazard: HazardLayerInfo | null = null;
      let people: ExposureInfo | null = null;
      try {
        [hazard, people] = await Promise.all([fetchHazard(), fetchExposure()]);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
      if (cancelled || !container.current) return;
      setInfo(hazard);
      setExposure(people);

      const b = hazard?.bounds;
      const created = new maplibregl.Map({
        container: container.current,
        style: BASEMAP,
        bounds: b
          ? [
              [b.west, b.south],
              [b.east, b.north],
            ]
          : FLORIDA,
        fitBoundsOptions: { padding: 16 },
        attributionControl: { compact: true },
      });
      created.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      if (hazard) {
        const layer = hazard;
        created.on("load", () => addLayers(created, layer, people));
      }
      map = created;
    })();

    return () => {
      cancelled = true;
      map?.remove();
    };
  }, []);

  return (
    <div className="relative h-full min-h-[420px] overflow-hidden rounded-xl border border-slate-200 bg-slate-100">
      {/* Sized directly: maplibre-gl.css forces position: relative on the map container. */}
      <div ref={container} className="h-full w-full" />
      <div className="pointer-events-none absolute left-3 top-3 max-w-[18rem] rounded-lg bg-white/95 p-3 text-xs text-slate-700 shadow-sm ring-1 ring-slate-200">
        <p className="font-semibold text-slate-900">Radar-observed water change</p>
        <p className="mt-0.5 text-slate-500">
          NISAR L-band, Sep 28 vs Oct 10, 2026
          {info && ` · ${info.method.toUpperCase()} · ${info.flagged_cells.toLocaleString()} cells flagged`}
        </p>
        {info?.open_water_cells != null && info.under_canopy_cells != null ? (
          <div className="mt-2 space-y-1.5">
            <FloodKindRamp
              label="Open water"
              detail="radar darkened"
              cells={info.open_water_cells}
              gradient="from-[#74a9cf] to-[#08519c]"
            />
            <FloodKindRamp
              label="Under tree canopy"
              detail="radar brightened"
              cells={info.under_canopy_cells}
              gradient="from-[#bc96e6] to-[#54278f]"
            />
            <p className="text-slate-500">Darker colour = higher confidence</p>
          </div>
        ) : (
          <div className="mt-2 flex items-center gap-2">
            <span className="text-slate-500">Lower</span>
            <span className="h-2 flex-1 rounded-full bg-gradient-to-r from-[#fdae61] to-[#d7191c]" />
            <span className="text-slate-500">Higher confidence</span>
          </div>
        )}
        {exposure && (
          <div className="mt-2 space-y-1.5 border-t border-slate-100 pt-2">
            <div className="flex items-center gap-2">
              <span className="h-2 w-10 shrink-0 rounded-full bg-gradient-to-r from-[#33415522] to-[#334155cc]" />
              <span className="text-slate-900">People per km²</span>
              <span className="text-slate-500">2020 Census blocks</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="flex w-10 shrink-0 justify-center">
                <span className="h-2.5 w-2.5 rounded-full ring-2 ring-white" style={{ background: SHELTER_COLOR }} />
              </span>
              <span className="text-slate-900">Public shelter</span>
              <span className="text-slate-500">spaces</span>
            </div>
            <p className="text-slate-500">
              {Math.round(exposure.people_in_flooded_cells).toLocaleString()} of{" "}
              {Math.round(exposure.total_population).toLocaleString()} people live in flagged cells
            </p>
          </div>
        )}
        {error && <p className="mt-2 text-red-600">Map layers unavailable: {error}</p>}
      </div>
    </div>
  );
}

// Colours match KIND_RAMPS in the backend's hazard_image.py.
function FloodKindRamp(props: { label: string; detail: string; cells: number; gradient: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className={`h-2 w-10 shrink-0 rounded-full bg-gradient-to-r ${props.gradient}`} />
      <span className="text-slate-900">{props.label}</span>
      <span className="text-slate-500">
        {props.detail} · {props.cells.toLocaleString()} cells
      </span>
    </div>
  );
}

function addLayers(map: maplibregl.Map, hazard: HazardLayerInfo, exposure: ExposureInfo | null) {
  const { west, south, east, north } = hazard.bounds;
  const corners: [[number, number], [number, number], [number, number], [number, number]] = [
    [west, north],
    [east, north],
    [east, south],
    [west, south],
  ];
  const firstLabel = map.getStyle().layers.find((l) => l.type === "symbol")?.id;

  // Population shares the hazard layer's grid, so the same corners; drawn beneath it.
  if (exposure) {
    map.addSource("population", {
      type: "image",
      url: exposure.population_image_url,
      coordinates: corners,
    });
    map.addLayer(
      {
        id: "population",
        type: "raster",
        source: "population",
        paint: { "raster-resampling": "nearest", "raster-opacity": 0.7 },
      },
      firstLabel,
    );
  }

  map.addSource("hazard", { type: "image", url: hazard.image_url, coordinates: corners });
  map.addLayer(
    {
      id: "hazard",
      type: "raster",
      source: "hazard",
      paint: { "raster-resampling": "nearest", "raster-opacity": 0.85 },
    },
    firstLabel,
  );

  map.addSource("towns", {
    type: "geojson",
    data: {
      type: "FeatureCollection",
      features: TOWNS.map(([name, lon, lat]) => ({
        type: "Feature",
        properties: { name },
        geometry: { type: "Point", coordinates: [lon, lat] },
      })),
    },
  });
  map.addLayer({
    id: "town-dots",
    type: "circle",
    source: "towns",
    paint: {
      "circle-radius": 4,
      "circle-color": "#0f172a",
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 1.5,
    },
  });
  map.addLayer({
    id: "town-labels",
    type: "symbol",
    source: "towns",
    layout: {
      "text-field": ["get", "name"],
      "text-font": ["Montserrat Medium"],
      "text-size": 12,
      "text-offset": [0, 1.1],
      "text-anchor": "top",
    },
    paint: {
      "text-color": "#0f172a",
      "text-halo-color": "#ffffff",
      "text-halo-width": 1.5,
    },
  });

  if (!exposure) return;
  map.addSource("shelters", {
    type: "geojson",
    data: {
      type: "FeatureCollection",
      features: exposure.shelters.map((s) => ({
        type: "Feature",
        properties: { label: `${s.name}\n${Math.round(s.capacity).toLocaleString()} spaces` },
        geometry: { type: "Point", coordinates: [s.longitude, s.latitude] },
      })),
    },
  });
  map.addLayer({
    id: "shelter-dots",
    type: "circle",
    source: "shelters",
    paint: {
      "circle-radius": 6,
      "circle-color": SHELTER_COLOR,
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 2,
    },
  });
  map.addLayer({
    id: "shelter-labels",
    type: "symbol",
    source: "shelters",
    layout: {
      "text-field": ["get", "label"],
      "text-font": ["Montserrat Medium"],
      "text-size": 11,
      "text-offset": [0.9, 0],
      "text-anchor": "left",
      "text-justify": "left",
    },
    paint: {
      "text-color": SHELTER_COLOR,
      "text-halo-color": "#ffffff",
      "text-halo-width": 1.5,
    },
  });
}
