"use client";

import maplibregl, { type ExpressionSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";

import {
  fetchExposure,
  fetchFloodCells,
  fetchHazard,
  type ExposureInfo,
  type FloodCells,
  type HazardLayerInfo,
  type Scenario,
} from "@/lib/api";
import type { Beat } from "@/lib/storyboard";

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
  ["Suwannee", -83.143, 29.326],
];

// Keep in sync with OPEN_WATER_SURFACE / CANOPY_SURFACE in hazard_image.py (deepest stop).
const KIND_COLORS: Record<number, string> = {
  0: "#2563eb", // flagged, kind unknown (SME2 fallback): drawn as open water when zoomed out
  1: "#1e3a8a", // open water
  2: "#0369a1", // under canopy
};
// Zoomed out, the smoothed flood surface; from here in, each flagged 60 m cell.
const CELLS_MINZOOM = 13.5;
// Fewer people than this rounds to 0 in the popups.
const SOMEONE_LIVES = 0.5;
// Shows a town's 4 km planning radius with some surroundings.
const SCOPE_ZOOM = 11.5;
const KIND_LABELS: Record<number, string> = {
  0: "Flagged as flooded",
  1: "Open water (radar darkened)",
  2: "Flooding under tree canopy (radar brightened)",
};
const SHELTER_COLOR = "#047857";
const TOWN_COLOR = "#0f172a";
// Behind every label on the light basemap.
const HALO = "#ffffff";
const TOWN_RADIUS = 3.5;
const PEOPLE_RING = "#f59e0b";
// Keep in sync with FEMA_ZONE_RGB / FEMA_ZONE_ALPHA in hazard_image.py.
const FEMA_ZONE_TINT = "rgba(20, 184, 166, 0.27)";
// The legend's version of the flood surface: faint canopy to deep open water.
// Keep in sync with OPEN_WATER_SURFACE / CANOPY_SURFACE in hazard_image.py.
const SURFACE_GRADIENT = "rgba(125, 211, 252, 0.45), rgba(3, 105, 161, 0.7), #60a5fa, #1e3a8a";
// The start card's height on a narrow screen, plus a gap.
const START_CARD_HEIGHT = 420;

type LayerGroup = "flooding" | "fema" | "population" | "shelters";
const GROUP_LAYERS: Record<LayerGroup, string[]> = {
  flooding: ["flood-surface", "flood-cells", "flood-people"],
  fema: ["fema-zones"],
  population: ["population"],
  shelters: ["shelter-dots", "shelter-labels"],
};

/** The study-area map. It fills its container; `quiet` hides the legend (while a run plays
 * over it), `compact` folds it (beside the report) and `beat` draws a moment of a run. */
export default function HazardMap({
  scenario,
  quiet = false,
  compact = false,
  beat = null,
}: {
  scenario: Scenario;
  quiet?: boolean;
  compact?: boolean;
  beat?: Beat | null;
}) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [info, setInfo] = useState<HazardLayerInfo | null>(null);
  const [exposure, setExposure] = useState<ExposureInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState<Record<LayerGroup, boolean>>({
    flooding: true,
    fema: true,
    population: false,
    shelters: true,
  });
  const [legendOpen, setLegendOpen] = useState(true);
  const [peopleOnly, setPeopleOnly] = useState(false);
  const [lived, setLived] = useState<{ cells: number; withPeople: number } | null>(null);
  const visibleRef = useRef(visible);
  const peopleOnlyRef = useRef(peopleOnly);
  const scenarioRef = useRef(scenario);
  const exposureRef = useRef<ExposureInfo | null>(null);
  const compactRef = useRef(compact);
  compactRef.current = compact;
  const beatRef = useRef(beat);
  beatRef.current = beat;
  // The places the camera last framed for a beat, so repeated beats do not refit.
  const framedRef = useRef<string | undefined>(undefined);
  // When the current beat appeared, so a strike plays once at its start.
  const beatShownAt = useRef(0);

  useEffect(() => {
    let map: maplibregl.Map | null = null;
    let cancelled = false;

    (async () => {
      let hazard: HazardLayerInfo | null = null;
      let people: ExposureInfo | null = null;
      let cells: FloodCells | null = null;
      try {
        [hazard, people, cells] = await Promise.all([
          fetchHazard(),
          fetchExposure(),
          fetchFloodCells(),
        ]);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
      if (cancelled || !container.current) return;
      if (container.current.clientWidth < 640) setLegendOpen(false);
      setInfo(hazard);
      setExposure(people);
      exposureRef.current = people;
      if (cells) {
        setLived({
          cells: cells.cells.length,
          withPeople: cells.cells.filter(([, , , , p]) => p >= SOMEONE_LIVES).length,
        });
      }

      const b = hazard?.bounds;
      const pad = 2.5;
      const created = new maplibregl.Map({
        container: container.current,
        style: BASEMAP,
        bounds: b
          ? [
              [b.west, b.south],
              [b.east, b.north],
            ]
          : FLORIDA,
        fitBoundsOptions: { padding: fitPadding(container.current, compactRef.current) },
        maxBounds: b
          ? [
              [b.west - pad, b.south - pad],
              [b.east + pad, b.north + pad],
            ]
          : undefined,
        minZoom: 5.5,
        maxZoom: 16.5,
        dragRotate: false,
        pitchWithRotate: false,
        touchPitch: false,
        hash: true,
        attributionControl: { compact: true },
        // Lets the PDF download copy the map's pixels.
        canvasContextAttributes: { preserveDrawingBuffer: true },
      });
      created.touchZoomRotate.disableRotation();
      created.scrollZoom.setWheelZoomRate(1 / 200);
      created.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      created.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
      if (hazard) {
        const layer = hazard;
        created.on("load", () => {
          addLayers(created, layer, people, cells);
          applyVisibility(created, visibleRef.current);
          applyPeopleOnly(created, peopleOnlyRef.current);
          applyScenario(created, scenarioRef.current, people);
          if (people) applyBeat(created, beatRef.current, people, framedRef);
        });
      }
      map = created;
      mapRef.current = created;
    })();

    // The container changes size between the start, run and report screens.
    const resize = new ResizeObserver(() => mapRef.current?.resize());
    if (container.current) resize.observe(container.current);

    return () => {
      cancelled = true;
      resize.disconnect();
      mapRef.current = null;
      map?.remove();
    };
  }, []);

  // Switching between the full-screen and report layouts: refit the area being planned.
  useEffect(() => {
    if (compact) setLegendOpen(false);
    const timer = setTimeout(() => {
      mapRef.current?.resize();
      const town = exposureRef.current?.communities.find((c) => c.id === scenarioRef.current.scope);
      goTo(town ? { center: [town.longitude, town.latitude], zoom: SCOPE_ZOOM } : {});
    }, 50);
    return () => clearTimeout(timer);
    // goTo only reads refs and `info`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compact]);

  useEffect(() => {
    beatShownAt.current = performance.now();
    const map = mapRef.current;
    if (map?.getSource(BEAT_ARCS) && exposureRef.current) {
      applyBeat(map, beat, exposureRef.current, framedRef);
    }
  }, [beat]);

  // Arcs flow and opened shelters pulse while a beat is drawn; a shelter knocked offline sends
  // out shock rings in red, then settles grey.
  const drawing = beat != null;
  useEffect(() => {
    if (!drawing) return;
    let frame = 0;
    let last = -1;
    const tick = (t: number) => {
      const map = mapRef.current;
      const step = Math.floor(t / 60) % DASHES.length;
      if (map?.getLayer("beat-arc-flow") && step !== last) {
        last = step;
        map.setPaintProperty("beat-arc-flow", "line-dasharray", DASHES[step]);
        const pulse = 0.55 + 0.45 * Math.sin(t / 260) ** 2;
        map.setPaintProperty("beat-rings", "circle-stroke-opacity", ["case", OPEN, pulse, 0.9]);
        const since = t - beatShownAt.current;
        const striking = since < STRIKES * STRIKE_MS;
        const k = (since % STRIKE_MS) / STRIKE_MS;
        map.setPaintProperty("beat-strike", "circle-radius", 8 + 52 * k);
        map.setPaintProperty("beat-strike", "circle-stroke-opacity", striking ? 0.9 * (1 - k) : 0);
        map.setPaintProperty("beat-rings", "circle-stroke-color", ringColor(striking));
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [drawing]);

  useEffect(() => {
    visibleRef.current = visible;
    if (mapRef.current) applyVisibility(mapRef.current, visible);
  }, [visible]);

  useEffect(() => {
    peopleOnlyRef.current = peopleOnly;
    if (mapRef.current) applyPeopleOnly(mapRef.current, peopleOnly);
  }, [peopleOnly]);

  useEffect(() => {
    const scopeChanged = scenario.scope !== scenarioRef.current.scope;
    scenarioRef.current = scenario;
    if (mapRef.current) applyScenario(mapRef.current, scenario, exposureRef.current);
    if (scopeChanged) {
      const town = exposureRef.current?.communities.find((c) => c.id === scenario.scope);
      goTo(town ? { center: [town.longitude, town.latitude], zoom: SCOPE_ZOOM } : {});
    }
    // goTo only reads refs and `info`, which is set before any scope change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario]);

  function goTo(view: { center?: [number, number]; zoom?: number }) {
    const map = mapRef.current;
    if (!map) return;
    if (view.center) {
      map.flyTo({ center: view.center, zoom: view.zoom, duration: 1200 });
    } else if (info) {
      const { west, south, east, north } = info.bounds;
      map.fitBounds(
        [
          [west, south],
          [east, north],
        ],
        { padding: fitPadding(map.getContainer(), compactRef.current), duration: 1200 },
      );
    }
  }

  const toggle = (group: LayerGroup) => setVisible((v) => ({ ...v, [group]: !v[group] }));

  return (
    <div className="relative h-full w-full overflow-hidden bg-slate-100">
      {/* Sized directly: maplibre-gl.css forces position: relative on the map container. */}
      <div ref={container} className="h-full w-full" />

      {!quiet && (
        <div className="absolute right-3 bottom-8 w-[17rem] rounded-lg bg-white/95 text-xs text-slate-700 shadow-sm ring-1 ring-slate-200">
          <button
            type="button"
            onClick={() => setLegendOpen((o) => !o)}
            className="flex w-full items-center justify-between px-3 py-2 text-left"
          >
            <span className="font-semibold text-slate-900">Layers</span>
            <span className="text-slate-400">{legendOpen ? "Hide" : "Show"}</span>
          </button>
          {legendOpen && (
            <div className="space-y-2.5 border-t border-slate-100 px-3 pb-3 pt-2">
              <LayerToggle
                checked={visible.flooding}
                onChange={() => toggle("flooding")}
                title="Radar-observed flooding"
                detail={`NISAR ${info ? info.method.toUpperCase() + " " : ""}· Sep 28 vs Oct 10`}
              >
                <label className="flex cursor-pointer items-start gap-2 pb-1">
                  <input
                    type="checkbox"
                    checked={peopleOnly}
                    onChange={() => setPeopleOnly((on) => !on)}
                    className="mt-0.5 accent-slate-900"
                  />
                  <span>
                    <span className="block font-medium text-slate-900">
                      Zoomed in, hide cells where nobody lives
                    </span>
                    {lived && (
                      <span className="block text-slate-500">
                        {lived.withPeople.toLocaleString()} of {lived.cells.toLocaleString()}{" "}
                        flagged cells have an estimated 1 or more residents
                      </span>
                    )}
                  </span>
                </label>
                <p className="text-slate-500">
                  Zoomed out, where flagged cells cluster, smoothed for display (lone cells fade
                  out):
                </p>
                <div
                  className="h-2 rounded-full"
                  style={{ background: `linear-gradient(to right, ${SURFACE_GRADIENT})` }}
                />
                <p className="pt-1 text-slate-500">Zoomed in, each 60 m cell:</p>
                {info?.open_water_cells != null && info.under_canopy_cells != null ? (
                  <>
                    <Swatch color={KIND_COLORS[2]}>
                      Under tree canopy · {info.under_canopy_cells.toLocaleString()}
                    </Swatch>
                    <Swatch color={KIND_COLORS[1]}>
                      Open water · {info.open_water_cells.toLocaleString()}
                    </Swatch>
                  </>
                ) : (
                  <Swatch color={KIND_COLORS[0]}>Flagged cell</Swatch>
                )}
                <Swatch color="transparent" ring={PEOPLE_RING}>
                  People live there
                </Swatch>
              </LayerToggle>

              {exposure && (
                <>
                  <LayerToggle
                    checked={visible.fema}
                    onChange={() => toggle("fema")}
                    title="FEMA flood zones"
                    detail="Special Flood Hazard Area · context only; plans count everyone the same"
                  >
                    <Swatch color={FEMA_ZONE_TINT}>In a FEMA flood zone</Swatch>
                  </LayerToggle>
                  <LayerToggle
                    checked={visible.population}
                    onChange={() => toggle("population")}
                    title="People per km²"
                    detail={`2020 Census · ${Math.round(exposure.people_in_flooded_cells).toLocaleString()} of ${Math.round(exposure.total_population).toLocaleString()} in flagged cells`}
                  />
                  <LayerToggle
                    checked={visible.shelters}
                    onChange={() => toggle("shelters")}
                    title="Public shelters"
                    detail={`${exposure.shelters.length} sites · zoom in and click a cell or shelter for details`}
                  />
                </>
              )}
              {error && <p className="text-red-600">Map layers unavailable: {error}</p>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Full screen, keep the area clear of the start card. */
function fitPadding(element: HTMLElement, compact: boolean) {
  if (compact) return { top: 24, bottom: 24, right: 24, left: 24 };
  // Wide, the card sits on the left; narrower, it spans the top.
  return element.clientWidth >= 1024
    ? { top: 24, bottom: 24, right: 24, left: 420 }
    : { top: START_CARD_HEIGHT, bottom: 48, right: 24, left: 24 };
}



const BEAT_ARCS = "beat-arcs";
const BEAT_SHELTERS = "beat-shelters";
const BEAT_UNREACHED = "beat-unreached";
const BEAT_CUT_RINGS = "beat-cut-rings";
const ARC_COLOR = "#f59e0b";
const TRANSPORT_ARC_COLOR = "#c084fc";
const RING_COLOR = "#10b981";
const ATTACK_COLOR = "#dc2626";
const LOST_COLOR = "#64748b";
const OPEN: ExpressionSpecification = ["==", ["get", "state"], "open"];
// A struck shelter sends out this many shock rings, one every STRIKE_MS.
const STRIKES = 2;
const STRIKE_MS = 1400;

/** Rings: open green, offline red while it is struck then grey, unfunded grey. */
function ringColor(striking: boolean): ExpressionSpecification {
  return [
    "match",
    ["get", "state"],
    "open",
    RING_COLOR,
    "offline",
    striking ? ATTACK_COLOR : LOST_COLOR,
    LOST_COLOR,
  ];
}

// Clear of the counter above and the caption bar below.
const BEAT_PADDING = { top: 190, bottom: 170, left: 80, right: 80 };
const NARROW_BEAT_PADDING = { top: 160, bottom: 160, left: 40, right: 40 };
// Dash and gap lengths, stepped each frame so the dashes run from town to shelter.
const DASHES: number[][] = [
  [0, 4, 3],
  [0.5, 4, 2.5],
  [1, 4, 2],
  [1.5, 4, 1.5],
  [2, 4, 1],
  [2.5, 4, 0.5],
  [3, 4, 0],
  [0, 0.5, 3, 3.5],
  [0, 1, 3, 3],
  [0, 1.5, 3, 2.5],
  [0, 2, 3, 2],
  [0, 2.5, 3, 1.5],
  [0, 3, 3, 1],
  [0, 3.5, 3, 0.5],
];

/** Layers a run's beats draw into: rings on opened shelters, and arcs from towns to them. */
function addBeatLayers(map: maplibregl.Map) {
  const empty: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
  map.addSource(BEAT_ARCS, { type: "geojson", data: empty });
  map.addSource(BEAT_SHELTERS, { type: "geojson", data: empty });
  map.addSource(BEAT_UNREACHED, { type: "geojson", data: empty });
  map.addSource(BEAT_CUT_RINGS, { type: "geojson", data: empty });
  map.addLayer({
    id: "beat-cut-rings",
    type: "line",
    source: BEAT_CUT_RINGS,
    paint: { "line-color": ATTACK_COLOR, "line-width": 3, "line-dasharray": [2, 1.5] },
  });
  const width: ExpressionSpecification = [
    "interpolate",
    ["linear"],
    ["get", "people"],
    1,
    2,
    50,
    3.5,
    300,
    7,
  ];
  const color: ExpressionSpecification = ["case", [">", ["get", "carried"], 0], TRANSPORT_ARC_COLOR, ARC_COLOR];
  const broken: ExpressionSpecification = ["get", "broken"];
  map.addLayer({
    id: "beat-arc-glow",
    type: "line",
    source: BEAT_ARCS,
    layout: { "line-cap": "round" },
    paint: {
      "line-color": ["case", broken, ATTACK_COLOR, color],
      "line-width": ["*", width, 3],
      "line-opacity": 0.18,
      "line-blur": 4,
    },
  });
  map.addLayer({
    id: "beat-arc-flow",
    type: "line",
    source: BEAT_ARCS,
    filter: ["!", broken],
    paint: { "line-color": color, "line-width": width, "line-dasharray": DASHES[0] },
  });
  // People an attack stops: the arc stays, red and still.
  map.addLayer({
    id: "beat-arc-broken",
    type: "line",
    source: BEAT_ARCS,
    filter: broken,
    paint: { "line-color": ATTACK_COLOR, "line-width": width, "line-dasharray": [1, 1.5], "line-opacity": 0.85 },
  });
  map.addLayer({
    id: "beat-rings",
    type: "circle",
    source: BEAT_SHELTERS,
    paint: {
      // Area grows with capacity: 1,500 spaces is about 20 px across at zoom 9.
      "circle-radius": [
        "interpolate",
        ["linear"],
        ["zoom"],
        7,
        ["*", ["sqrt", ["get", "capacity"]], 0.3],
        9,
        ["*", ["sqrt", ["get", "capacity"]], 0.52],
        13,
        ["*", ["sqrt", ["get", "capacity"]], 0.9],
      ],
      "circle-color": ["case", OPEN, RING_COLOR, LOST_COLOR],
      "circle-opacity": ["case", OPEN, 0.16, 0.3],
      "circle-stroke-color": ringColor(true),
      "circle-stroke-width": 2.5,
    },
  });
  map.addLayer({
    id: "beat-strike",
    type: "circle",
    source: BEAT_SHELTERS,
    filter: ["==", ["get", "state"], "offline"],
    paint: {
      "circle-radius": 8,
      "circle-color": "transparent",
      "circle-stroke-color": ATTACK_COLOR,
      "circle-stroke-width": 3,
    },
  });
  map.addLayer({
    id: "beat-shelter-states",
    type: "symbol",
    source: BEAT_SHELTERS,
    filter: ["!", OPEN],
    layout: {
      "text-field": ["match", ["get", "state"], "offline", "OFFLINE", "NO FUNDS"],
      "text-font": ["Montserrat Medium"],
      "text-size": 12,
      "text-letter-spacing": 0.08,
      "text-offset": [0, -2.2],
      "text-allow-overlap": true,
    },
    paint: {
      "text-color": ["match", ["get", "state"], "offline", ATTACK_COLOR, LOST_COLOR],
      "text-halo-color": HALO,
      "text-halo-width": 2,
    },
  });
  map.addLayer({
    id: "beat-unreached",
    type: "symbol",
    source: BEAT_UNREACHED,
    layout: {
      "text-field": ["get", "label"],
      "text-font": ["Montserrat Medium"],
      "text-size": 12,
      "text-anchor": "top",
      "text-offset": [0, 1.6],
      "text-allow-overlap": true,
    },
    paint: { "text-color": ATTACK_COLOR, "text-halo-color": HALO, "text-halo-width": 2 },
  });
  map.addLayer({
    id: "beat-arc-labels",
    type: "symbol",
    source: BEAT_ARCS,
    filter: ["all", [">=", ["get", "people"], 5], ["!", broken]],
    layout: {
      "symbol-placement": "line-center",
      "text-field": ["get", "label"],
      "text-font": ["Montserrat Medium"],
      "text-size": 11,
      "text-rotation-alignment": "viewport",
      "text-allow-overlap": true,
    },
    paint: { "text-color": "#78350f", "text-halo-color": "#fffbeb", "text-halo-width": 2 },
  });
}

/** Draw a beat (or clear the map of one) and frame the places it involves. */
function applyBeat(
  map: maplibregl.Map,
  beat: Beat | null,
  exposure: ExposureInfo,
  framed: { current: string | undefined },
) {
  const shelters = new Map(exposure.shelters.map((s) => [s.id, s]));
  const towns = new Map(exposure.communities.map((c) => [c.id, c]));
  const arcs = (beat?.arcs ?? []).flatMap((arc) => {
    const town = towns.get(arc.from);
    const shelter = shelters.get(arc.to);
    if (!town || !shelter) return [];
    const riders = arc.carried > 0 ? `, ${Math.round(arc.carried).toLocaleString()} by bus` : "";
    return [
      {
        type: "Feature" as const,
        geometry: curve(lonLat(town), lonLat(shelter)),
        properties: {
          people: arc.people,
          carried: arc.carried,
          broken: arc.broken,
          label: `${Math.round(arc.people).toLocaleString()} people${riders}`,
        },
      },
    ];
  });
  const opened = Object.entries(beat?.shelters ?? {}).flatMap(([id, state]) => {
    const s = shelters.get(id);
    return s ? [{ place: s, state }] : [];
  });
  const cut = (beat?.cutTowns ?? []).flatMap((id) => towns.get(id) ?? []);
  const unreached = Object.entries(beat?.unreached ?? {}).flatMap(([id, people]) => {
    const town = towns.get(id);
    const label = `${Math.round(people).toLocaleString()} not reached`;
    return town ? [{ lon: town.longitude, lat: town.latitude, props: { label } }] : [];
  });
  (map.getSource(BEAT_ARCS) as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features: arcs });
  (map.getSource(BEAT_SHELTERS) as maplibregl.GeoJSONSource).setData(
    points(
      opened.map(({ place, state }) => ({
        lon: place.longitude,
        lat: place.latitude,
        props: { id: place.id, state, capacity: place.capacity },
      })),
    ),
  );
  (map.getSource(BEAT_UNREACHED) as maplibregl.GeoJSONSource).setData(points(unreached));
  const rings = cut.map((town) => ring(lonLat(town), town.radius_km));
  (map.getSource(BEAT_CUT_RINGS) as maplibregl.GeoJSONSource).setData({
    type: "FeatureCollection",
    features: rings.map((geometry) => ({ type: "Feature", properties: {}, geometry })),
  });

  // A cut town is framed by its whole ring.
  const ringPoints = rings.flatMap((r) => r.coordinates as [number, number][]);
  const all = [
    ...opened.map(({ place }) => lonLat(place)),
    ...ringPoints,
    ...(beat?.arcs ?? []).flatMap((a) => {
      const town = towns.get(a.from);
      return town ? [lonLat(town)] : [];
    }),
  ];
  // An attack beat moves in on what it hit: the shelters lost, the towns cut off and both ends
  // of every arc it broke.
  const hit = [
    ...opened.filter(({ state }) => state !== "open").map(({ place }) => lonLat(place)),
    ...ringPoints,
    ...(beat?.arcs ?? [])
      .filter((a) => a.broken)
      .flatMap((a) => [towns.get(a.from), shelters.get(a.to)].flatMap((p) => (p ? [lonLat(p)] : []))),
  ];
  const focus = beat?.kind === "attack" && hit.length ? hit : all;
  if (!beat) framed.current = undefined;
  if (focus.length === 0) return;
  const key = focus.map((p) => p.join()).sort().join(";");
  if (key === framed.current) return;
  framed.current = key;
  const bounds = focus.reduce(
    (b, p) => b.extend(p),
    new maplibregl.LngLatBounds(focus[0], focus[0]),
  );
  const padding = map.getContainer().clientWidth < 640 ? NARROW_BEAT_PADDING : BEAT_PADDING;
  map.fitBounds(bounds, { padding, maxZoom: 11, duration: 1600 });
}

function lonLat(place: { longitude: number; latitude: number }): [number, number] {
  return [place.longitude, place.latitude];
}

/** A circle of `km` around `center`, as a closed line. */
function ring(center: [number, number], km: number): GeoJSON.LineString {
  const [lon, lat] = center;
  const dLat = km / 111.32;
  const dLon = dLat / Math.cos((lat * Math.PI) / 180);
  const coordinates: [number, number][] = [];
  for (let i = 0; i <= 64; i++) {
    const a = (i / 64) * 2 * Math.PI;
    coordinates.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)]);
  }
  return { type: "LineString", coordinates };
}

/** A gentle arc from `a` to `b`, bowed to the left of travel. */
function curve(a: [number, number], b: [number, number]): GeoJSON.LineString {
  const [dx, dy] = [b[0] - a[0], b[1] - a[1]];
  const control: [number, number] = [(a[0] + b[0]) / 2 - dy * 0.2, (a[1] + b[1]) / 2 + dx * 0.2];
  const coordinates: [number, number][] = [];
  for (let i = 0; i <= 32; i++) {
    const t = i / 32;
    const u = 1 - t;
    coordinates.push([
      u * u * a[0] + 2 * u * t * control[0] + t * t * b[0],
      u * u * a[1] + 2 * u * t * control[1] + t * t * b[1],
    ]);
  }
  return { type: "LineString", coordinates };
}

const OFFLINE_COLOR = "#94a3b8";
const CLOSED_ROAD_COLOR = "#dc2626";

/** Grey out offline shelters and mark towns whose road is closed. */
function applyScenario(map: maplibregl.Map, scenario: Scenario, exposure: ExposureInfo | null) {
  if (map.getLayer("shelter-dots")) {
    const offline: ExpressionSpecification = [
      "in",
      ["get", "id"],
      ["literal", scenario.offline_shelters],
    ];
    map.setPaintProperty("shelter-dots", "circle-color", ["case", offline, OFFLINE_COLOR, SHELTER_COLOR]);
    map.setPaintProperty("shelter-labels", "text-color", ["case", offline, OFFLINE_COLOR, SHELTER_COLOR]);
    map.setLayoutProperty("shelter-labels", "text-field", [
      "case",
      offline,
      ["concat", ["get", "label"], "\noffline"],
      ["get", "label"],
    ]);
  }
  if (map.getLayer("town-dots") && exposure) {
    const closedNames = exposure.communities
      .filter((c) => scenario.closed_communities.includes(c.id))
      .map((c) => c.name);
    const closed: ExpressionSpecification = ["in", ["get", "name"], ["literal", closedNames]];
    map.setPaintProperty("town-dots", "circle-color", ["case", closed, CLOSED_ROAD_COLOR, TOWN_COLOR]);
    map.setPaintProperty("town-dots", "circle-radius", ["case", closed, 6, TOWN_RADIUS]);
    // Closed towns move to their own label layer, which may overlap other labels.
    map.setFilter("town-labels", ["!", closed]);
    map.setFilter("town-closed-labels", closed);
  }
}

function applyVisibility(map: maplibregl.Map, visible: Record<LayerGroup, boolean>) {
  for (const [group, layers] of Object.entries(GROUP_LAYERS)) {
    for (const id of layers) {
      if (map.getLayer(id)) {
        map.setLayoutProperty(id, "visibility", visible[group as LayerGroup] ? "visible" : "none");
      }
    }
  }
}

/** Show only flagged cells with an estimated resident, or every flagged cell. */
function applyPeopleOnly(map: maplibregl.Map, peopleOnly: boolean) {
  if (map.getLayer("flood-cells")) {
    map.setFilter("flood-cells", peopleOnly ? [">=", ["get", "p"], SOMEONE_LIVES] : null);
  }
}

function LayerToggle(props: {
  checked: boolean;
  onChange: () => void;
  title: string;
  detail: string;
  children?: React.ReactNode;
}) {
  return (
    <div>
      <label className="flex cursor-pointer items-start gap-2">
        <input
          type="checkbox"
          checked={props.checked}
          onChange={props.onChange}
          className="mt-0.5 accent-slate-900"
        />
        <span>
          <span className="block font-medium text-slate-900">{props.title}</span>
          <span className="block text-slate-500">{props.detail}</span>
        </span>
      </label>
      {props.children && props.checked && (
        <div className="mt-1.5 space-y-1 pl-5">{props.children}</div>
      )}
    </div>
  );
}

function Swatch(props: { color: string; ring?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="h-2.5 w-2.5 shrink-0"
        style={{ background: props.color, boxShadow: props.ring ? `inset 0 0 0 2px ${props.ring}` : undefined }}
      />
      <span>{props.children}</span>
    </div>
  );
}

function addLayers(
  map: maplibregl.Map,
  hazard: HazardLayerInfo,
  exposure: ExposureInfo | null,
  cells: FloodCells | null,
) {
  const { west, south, east, north } = hazard.bounds;
  const layers = map.getStyle().layers;
  const firstLabel = layers.find((l) => l.type === "symbol")?.id;
  // Flagged cells go over roads and buildings, which would otherwise slice through them,
  // but under the place and road names.
  const lastShape = layers.findLastIndex((l) => l.type !== "symbol");
  const namesAbove = layers.slice(lastShape + 1).find((l) => l.type === "symbol")?.id;

  // Population shares the hazard grid's corners and sits beneath everything else.
  if (exposure) {
    map.addSource("population", {
      type: "image",
      url: exposure.population_image_url,
      coordinates: [
        [west, north],
        [east, north],
        [east, south],
        [west, south],
      ],
    });
    map.addLayer(
      {
        id: "population",
        type: "raster",
        source: "population",
        paint: {
          "raster-resampling": "nearest",
          "raster-opacity": ["interpolate", ["linear"], ["zoom"], 8, 0.55, 12, 0.3, 14, 0.12, 16, 0],
        },
      },
      firstLabel,
    );
    map.addSource("fema-zones", {
      type: "image",
      url: exposure.fema_zones_image_url,
      coordinates: [
        [west, north],
        [east, north],
        [east, south],
        [west, south],
      ],
    });
    map.addLayer(
      { id: "fema-zones", type: "raster", source: "fema-zones", paint: { "raster-resampling": "nearest" } },
      firstLabel,
    );
  }

  const popups: [string, (p: Record<string, unknown>) => string][] = [];

  if (cells) {
    const grid = gridOf(hazard);
    const cellM = Math.round((grid.dlat * 111_320) / 10) * 10;
    // A cell is only a few pixels wide below CELLS_MINZOOM, so further out the flagged cells
    // are drawn as the backend's smoothed surface.
    map.addSource("flood-surface", {
      type: "image",
      url: hazard.surface_url,
      coordinates: [
        [west, north],
        [east, north],
        [east, south],
        [west, south],
      ],
    });
    map.addLayer(
      {
        id: "flood-surface",
        type: "raster",
        source: "flood-surface",
        maxzoom: CELLS_MINZOOM + 0.5,
        paint: {
          "raster-resampling": "linear",
          "raster-fade-duration": 0,
          // Fades out as the cells take over.
          "raster-opacity": ["interpolate", ["linear"], ["zoom"], CELLS_MINZOOM - 0.5, 1, CELLS_MINZOOM + 0.5, 0],
        },
      },
      // Under the basemap's water, which hides any blur that spills off land onto the Gulf,
      // rivers and lakes (permanent water carries no evidence of its own).
      layers.find((l) => l.id.startsWith("water"))?.id ?? namesAbove,
    );

    map.addSource("flood-cells", { type: "geojson", data: floodCellSquares(cells, grid) });
    map.addLayer(
      {
        id: "flood-cells",
        type: "fill",
        source: "flood-cells",
        minzoom: CELLS_MINZOOM,
        paint: {
          "fill-color": ["match", ["get", "k"], 1, KIND_COLORS[1], 2, KIND_COLORS[2], KIND_COLORS[0]],
          "fill-opacity": 0.85,
        },
      },
      namesAbove,
    );
    map.addLayer(
      {
        id: "flood-people",
        type: "line",
        source: "flood-cells",
        minzoom: CELLS_MINZOOM,
        filter: [">=", ["get", "p"], 0.5],
        paint: {
          "line-color": PEOPLE_RING,
          "line-width": ["interpolate", ["linear"], ["zoom"], 14, 1.5, 16, 3],
        },
      },
      namesAbove,
    );
    popups.push(["flood-cells", (p) => cellPopup(p, cellM)]);
  }

  addBeatLayers(map);

  map.addSource("towns", {
    type: "geojson",
    data: points(TOWNS.map(([name, lon, lat]) => ({ lon, lat, props: { name } }))),
  });
  map.addLayer({
    id: "town-dots",
    type: "circle",
    source: "towns",
    paint: {
      "circle-radius": TOWN_RADIUS,
      "circle-color": TOWN_COLOR,
      "circle-stroke-color": HALO,
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
      "text-size": ["interpolate", ["linear"], ["zoom"], 8, 11, 13, 14],
      "text-variable-anchor": ["top", "bottom", "right", "left"],
      "text-radial-offset": 0.7,
    },
    paint: {
      "text-color": TOWN_COLOR,
      "text-halo-color": HALO,
      "text-halo-width": 1.5,
    },
  });
  map.addLayer({
    id: "town-closed-labels",
    type: "symbol",
    source: "towns",
    filter: ["==", ["get", "name"], ""],
    layout: {
      "text-field": ["concat", ["get", "name"], "\nroad closed"],
      "text-font": ["Montserrat Medium"],
      "text-size": ["interpolate", ["linear"], ["zoom"], 8, 11, 13, 14],
      // Below-left of the dot: shelter labels sit to the right, so this side is usually free.
      "text-anchor": "top-right",
      "text-justify": "right",
      "text-offset": [-0.4, 0.4],
      "text-allow-overlap": true,
    },
    paint: {
      "text-color": CLOSED_ROAD_COLOR,
      "text-halo-color": HALO,
      "text-halo-width": 1.5,
    },
  });

  if (exposure) addShelters(map, exposure, popups);
  // Over the shelter's own dot: a shelter a beat's attack took out is drawn grey.
  map.addLayer({
    id: "beat-lost-dots",
    type: "circle",
    source: BEAT_SHELTERS,
    filter: ["!", OPEN],
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 5, 14, 9],
      "circle-color": LOST_COLOR,
      "circle-stroke-color": HALO,
      "circle-stroke-width": 2,
    },
  });
  // Shelters first: the topmost layer under the pointer wins.
  showPopups(map, popups.reverse());
}

function addShelters(
  map: maplibregl.Map,
  exposure: ExposureInfo,
  popups: [string, (p: Record<string, unknown>) => string][],
) {
  map.addSource("shelters", {
    type: "geojson",
    data: points(
      exposure.shelters.map((s) => ({
        lon: s.longitude,
        lat: s.latitude,
        props: {
          id: s.id,
          name: s.name,
          label: `${s.name}\n${Math.round(s.capacity).toLocaleString()} spaces`,
          capacity: s.capacity,
          cost: s.cost,
        },
      })),
    ),
  });
  map.addLayer({
    id: "shelter-dots",
    type: "circle",
    source: "shelters",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 5, 14, 9],
      "circle-color": SHELTER_COLOR,
      "circle-stroke-color": HALO,
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
      "text-variable-anchor": ["left", "right", "top", "bottom"],
      "text-radial-offset": 0.9,
      "text-justify": "auto",
    },
    paint: {
      "text-color": SHELTER_COLOR,
      "text-halo-color": HALO,
      "text-halo-width": 1.5,
    },
  });
  popups.push([
    "shelter-dots",
    (p) => `<strong>${p.name}</strong><br/>
      ${Math.round(Number(p.capacity)).toLocaleString()} spaces<br/>
      Cost to open: $${Math.round(Number(p.cost)).toLocaleString()} (assumed $25 per space)`,
  ]);
}

type GridShape = { west: number; north: number; dlon: number; dlat: number; rows: number; cols: number };

function gridOf(hazard: HazardLayerInfo): GridShape {
  const { west, south, east, north } = hazard.bounds;
  return {
    west,
    north,
    dlon: (east - west) / hazard.cols,
    dlat: (north - south) / hazard.rows,
    rows: hazard.rows,
    cols: hazard.cols,
  };
}

function cellIndex(grid: GridShape, lon: number, lat: number): [row: number, col: number] {
  return [Math.floor((grid.north - lat) / grid.dlat), Math.floor((lon - grid.west) / grid.dlon)];
}

/** `size` cells square from (row, col), clipped to the grid. */
function square(grid: GridShape, row: number, col: number, size: number): GeoJSON.Polygon {
  const w = grid.west + col * grid.dlon;
  const e = grid.west + Math.min(col + size, grid.cols) * grid.dlon;
  const n = grid.north - row * grid.dlat;
  const s = grid.north - Math.min(row + size, grid.rows) * grid.dlat;
  return {
    type: "Polygon",
    coordinates: [
      [
        [w, n],
        [e, n],
        [e, s],
        [w, s],
        [w, n],
      ],
    ],
  };
}

function floodCellSquares(cells: FloodCells, grid: GridShape): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: cells.cells.map(([lon, lat, k, , p]) => {
      const [row, col] = cellIndex(grid, lon, lat);
      return { type: "Feature", properties: { k, p }, geometry: square(grid, row, col, 1) };
    }),
  };
}

function cellPopup(p: Record<string, unknown>, metres: number): string {
  const people = Math.round(Number(p.p));
  return `<strong>${KIND_LABELS[Number(p.k)] ?? KIND_LABELS[0]}</strong><br/>
    ${people > 0 ? `About ${people} ${people === 1 ? "person lives" : "people live"} in this ${metres} m cell` : "Nobody lives in this cell"}`;
}

function points(
  items: { lon: number; lat: number; props: Record<string, unknown> }[],
): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: items.map(({ lon, lat, props }) => ({
      type: "Feature",
      properties: props,
      geometry: { type: "Point", coordinates: [lon, lat] },
    })),
  };
}

function showPopups(
  map: maplibregl.Map,
  handlers: [string, (props: Record<string, unknown>) => string][],
) {
  const layers = handlers.map(([id]) => id);
  const topFeature = (point: maplibregl.PointLike) => {
    const hits = map.queryRenderedFeatures(point, { layers });
    for (const [id, html] of handlers) {
      const hit = hits.find((f) => f.layer.id === id);
      if (hit) return { hit, html };
    }
    return null;
  };
  map.on("click", (e) => {
    const found = topFeature(e.point);
    if (!found) return;
    const { hit, html } = found;
    const at = hit.geometry.type === "Point" ? (hit.geometry.coordinates as [number, number]) : e.lngLat;
    new maplibregl.Popup({ closeButton: true, maxWidth: "280px" })
      .setLngLat(at)
      .setHTML(`<div style="font-size:12px;line-height:1.5">${html(hit.properties)}</div>`)
      .addTo(map);
  });
  map.on("mousemove", (e) => {
    map.getCanvas().style.cursor = topFeature(e.point) ? "pointer" : "";
  });
}
