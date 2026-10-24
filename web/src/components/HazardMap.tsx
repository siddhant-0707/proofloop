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
} from "@/lib/api";

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

// Jump-to views; the first fits the whole study area.
const VIEWS: { label: string; center?: [number, number]; zoom?: number }[] = [
  { label: "Whole area" },
  { label: "Steinhatchee", center: [-83.385, 29.67], zoom: 13 },
  { label: "Horseshoe Beach", center: [-83.29, 29.44], zoom: 13.5 },
  { label: "Suwannee", center: [-83.14, 29.325], zoom: 13.5 },
  { label: "Cross City", center: [-83.12, 29.635], zoom: 12.5 },
  { label: "Perry", center: [-83.575, 30.115], zoom: 12.5 },
];

// Keep in sync with KIND_RAMPS in the backend's hazard_image.py (darkest stop).
const KIND_COLORS: Record<number, string> = {
  0: "#d7191c", // flagged, kind unknown (SME2 fallback)
  1: "#1e3a8a", // open water
  2: "#0284c7", // under canopy
};
// Nearly every block has a flagged cell or two; below this share they are left blank.
const MIN_DRAWN_SHARE = 0.02;
const SHARE_STOPS: [number, string][] = [
  [MIN_DRAWN_SHARE, "#7dd3fc"],
  [0.1, "#0ea5e9"],
  [0.25, "#0369a1"],
  [0.5, "#1e3a8a"],
];
const SHARE_RAMP: ExpressionSpecification = [
  "interpolate",
  ["linear"],
  ["get", "share"],
  ...SHARE_STOPS.flat(),
];
// A block's square grows with the share of its cells flagged, filling the block (less a
// gap) from FULL_SHARE up.
const FULL_SHARE = 0.4;
const MIN_SIDE = 0.25;
const MAX_SIDE = 0.86;
// Each level is drawn only where its blocks are roughly 6 to 13 px wide, so squares stay crisp.
const BLOCK_LEVELS = [
  { factor: 40, minzoom: 0, maxzoom: 9.5 },
  { factor: 20, minzoom: 9.5, maxzoom: 10.5 },
  { factor: 10, minzoom: 10.5, maxzoom: 11.5 },
  { factor: 5, minzoom: 11.5, maxzoom: 12.5 },
  { factor: 3, minzoom: 12.5, maxzoom: 13.5 },
].map((level) => ({ ...level, id: `flood-blocks-${level.factor}` }));
const CELLS_MINZOOM = 13.5;
const KIND_LABELS: Record<number, string> = {
  0: "Flagged as flooded",
  1: "Open water (radar darkened)",
  2: "Flooding under tree canopy (radar brightened)",
};
const SHELTER_COLOR = "#047857";
const PEOPLE_RING = "#f59e0b";

type LayerGroup = "flooding" | "population" | "shelters";
const GROUP_LAYERS: Record<LayerGroup, string[]> = {
  flooding: [...BLOCK_LEVELS.map((l) => l.id), "flood-cells", "flood-people"],
  population: ["population"],
  shelters: ["shelter-dots", "shelter-labels"],
};

// The legend card is 18rem wide at the top left; on wide maps, keep the study area clear of it.
const LEGEND_CLEARANCE = 18 * 16 + 12 + 16;

function fitPadding(element: HTMLElement) {
  const wide = element.clientWidth >= 2.5 * LEGEND_CLEARANCE;
  // Shelter labels extend right of their markers, so leave room on the right too.
  return { top: 16, right: wide ? 120 : 16, bottom: 16, left: wide ? LEGEND_CLEARANCE : 16 };
}

export default function HazardMap() {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [info, setInfo] = useState<HazardLayerInfo | null>(null);
  const [exposure, setExposure] = useState<ExposureInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState<Record<LayerGroup, boolean>>({
    flooding: true,
    population: false,
    shelters: true,
  });
  const [legendOpen, setLegendOpen] = useState(true);
  const visibleRef = useRef(visible);

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

      const b = hazard?.bounds;
      const pad = 0.35;
      const created = new maplibregl.Map({
        container: container.current,
        style: BASEMAP,
        bounds: b
          ? [
              [b.west, b.south],
              [b.east, b.north],
            ]
          : FLORIDA,
<<<<<<< Updated upstream
        fitBoundsOptions: { padding: fitPadding(container.current) },
=======
        fitBoundsOptions: { padding: 24 },
        maxBounds: b
          ? [
              [b.west - pad, b.south - pad],
              [b.east + pad, b.north + pad],
            ]
          : undefined,
        minZoom: 7,
        maxZoom: 16.5,
        dragRotate: false,
        pitchWithRotate: false,
        touchPitch: false,
        hash: true,
>>>>>>> Stashed changes
        attributionControl: { compact: true },
      });
      created.touchZoomRotate.disableRotation();
      created.scrollZoom.setWheelZoomRate(1 / 200);
      created.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      created.addControl(new maplibregl.FullscreenControl(), "top-right");
      created.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
      if (hazard) {
        const layer = hazard;
        created.on("load", () => {
          addLayers(created, layer, people, cells);
          applyVisibility(created, visibleRef.current);
        });
      }
      map = created;
      mapRef.current = created;
    })();

    return () => {
      cancelled = true;
      mapRef.current = null;
      map?.remove();
    };
  }, []);

  useEffect(() => {
    visibleRef.current = visible;
    if (mapRef.current) applyVisibility(mapRef.current, visible);
  }, [visible]);

  function goTo(view: (typeof VIEWS)[number]) {
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
        { padding: 24, duration: 1200 },
      );
    }
  }

  const toggle = (group: LayerGroup) => setVisible((v) => ({ ...v, [group]: !v[group] }));

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className="mr-1 text-slate-500">Go to</span>
        {VIEWS.map((view) => (
          <button
            key={view.label}
            type="button"
            onClick={() => goTo(view)}
            className="rounded-full bg-white px-2.5 py-1 font-medium text-slate-700 ring-1 ring-slate-200 transition hover:bg-slate-900 hover:text-white"
          >
            {view.label}
          </button>
        ))}
      </div>

      <div className="relative min-h-[480px] flex-1 overflow-hidden rounded-xl border border-slate-200 bg-slate-100">
        {/* Sized directly: maplibre-gl.css forces position: relative on the map container. */}
        <div ref={container} className="h-full w-full" />

        <div className="absolute bottom-8 left-3 w-[17rem] rounded-lg bg-white/95 text-xs text-slate-700 shadow-sm ring-1 ring-slate-200">
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
                <p className="text-slate-500">
                  Zoomed out, share of each block flagged (under {MIN_DRAWN_SHARE * 100}% left
                  blank):
                </p>
                <div className="flex items-end gap-3">
                  {[MIN_DRAWN_SHARE, 0.1, FULL_SHARE].map((share) => (
                    <div key={share} className="flex items-center gap-1.5">
                      <span className="flex h-3.5 w-3.5 items-center justify-center">
                        <span
                          style={{
                            width: `${blockSide(share) * 100}%`,
                            height: `${blockSide(share) * 100}%`,
                            background: shareColor(share),
                          }}
                        />
                      </span>
                      <span className="text-slate-500">
                        {Math.round(share * 100)}%{share === FULL_SHARE ? "+" : ""}
                      </span>
                    </div>
                  ))}
                </div>
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
                    checked={visible.population}
                    onChange={() => toggle("population")}
                    title="People per km²"
                    detail={`2020 Census · ${Math.round(exposure.people_in_flooded_cells).toLocaleString()} of ${Math.round(exposure.total_population).toLocaleString()} in flagged cells`}
                  />
                  <LayerToggle
                    checked={visible.shelters}
                    onChange={() => toggle("shelters")}
                    title="Public shelters"
                    detail={`${exposure.shelters.length} sites · click any square or shelter for details`}
                  />
                </>
              )}
              {error && <p className="text-red-600">Map layers unavailable: {error}</p>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
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
  // Flood squares go over roads and buildings, which would otherwise slice through them,
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
  }

  const popups: [string, (p: Record<string, unknown>) => string][] = [];

  if (cells) {
    const grid = gridOf(hazard);
    const cellM = Math.round((grid.dlat * 111_320) / 10) * 10;
    // A cell is only a few pixels wide below CELLS_MINZOOM, so further out each block of
    // cells is drawn as one square showing the share of its cells that are flagged.
    for (const level of BLOCK_LEVELS) {
      const metres = cellM * level.factor;
      map.addSource(level.id, { type: "geojson", data: floodBlocks(cells, grid, level.factor) });
      map.addLayer(
        {
          id: level.id,
          type: "fill",
          source: level.id,
          minzoom: level.minzoom,
          maxzoom: level.maxzoom,
          filter: [">=", ["get", "share"], MIN_DRAWN_SHARE],
          paint: { "fill-color": SHARE_RAMP, "fill-opacity": 0.95 },
        },
        namesAbove,
      );
      popups.push([level.id, (p) => blockPopup(p, metres)]);
    }

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

  map.addSource("towns", {
    type: "geojson",
    data: points(TOWNS.map(([name, lon, lat]) => ({ lon, lat, props: { name } }))),
  });
  map.addLayer({
    id: "town-dots",
    type: "circle",
    source: "towns",
    paint: {
      "circle-radius": 3.5,
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
      "text-size": ["interpolate", ["linear"], ["zoom"], 8, 11, 13, 14],
      "text-variable-anchor": ["top", "bottom", "right", "left"],
      "text-radial-offset": 0.7,
    },
    paint: {
      "text-color": "#0f172a",
      "text-halo-color": "#ffffff",
      "text-halo-width": 1.5,
    },
  });

  if (exposure) addShelters(map, exposure, popups);
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
      "text-variable-anchor": ["left", "right", "top", "bottom"],
      "text-radial-offset": 0.9,
      "text-justify": "auto",
    },
    paint: {
      "text-color": SHELTER_COLOR,
      "text-halo-color": "#ffffff",
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

/** `size` cells square from (row, col), clipped to the grid, then shrunk about its centre by `scale`. */
function square(grid: GridShape, row: number, col: number, size: number, scale = 1): GeoJSON.Polygon {
  const west = grid.west + col * grid.dlon;
  const east = grid.west + Math.min(col + size, grid.cols) * grid.dlon;
  const north = grid.north - row * grid.dlat;
  const south = grid.north - Math.min(row + size, grid.rows) * grid.dlat;
  const inset = (1 - scale) / 2;
  const [w, e] = [west + (east - west) * inset, east - (east - west) * inset];
  const [n, s] = [north - (north - south) * inset, south + (north - south) * inset];
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
    features: cells.cells.map(([lon, lat, k, c, p]) => {
      const [row, col] = cellIndex(grid, lon, lat);
      return { type: "Feature", properties: { k, c, p }, geometry: square(grid, row, col, 1) };
    }),
  };
}

function floodBlocks(cells: FloodCells, grid: GridShape, factor: number): GeoJSON.FeatureCollection {
  const blocks = new Map<string, { row: number; col: number; open: number; canopy: number; other: number; people: number }>();
  for (const [lon, lat, k, , p] of cells.cells) {
    const [cellRow, cellCol] = cellIndex(grid, lon, lat);
    const row = Math.floor(cellRow / factor) * factor;
    const col = Math.floor(cellCol / factor) * factor;
    const key = `${row}/${col}`;
    const block = blocks.get(key) ?? { row, col, open: 0, canopy: 0, other: 0, people: 0 };
    if (k === 1) block.open += 1;
    else if (k === 2) block.canopy += 1;
    else block.other += 1;
    block.people += p;
    blocks.set(key, block);
  }
  return {
    type: "FeatureCollection",
    features: [...blocks.values()].map((b) => {
      const size = (Math.min(b.row + factor, grid.rows) - b.row) * (Math.min(b.col + factor, grid.cols) - b.col);
      const flagged = b.open + b.canopy + b.other;
      const share = flagged / size;
      return {
        type: "Feature",
        properties: { share, flagged, open: b.open, canopy: b.canopy, people: b.people },
        geometry: square(grid, b.row, b.col, factor, blockSide(share)),
      };
    }),
  };
}

/** The legend's version of SHARE_RAMP: the colour of the nearest stop at or below `share`. */
function shareColor(share: number): string {
  return SHARE_STOPS.filter(([at]) => at <= share).at(-1)?.[1] ?? SHARE_STOPS[0][1];
}

/** Side of a block's square as a fraction of the block; area tracks the flagged share. */
function blockSide(share: number): number {
  return Math.min(MAX_SIDE, Math.max(MIN_SIDE, MAX_SIDE * Math.sqrt(share / FULL_SHARE)));
}

function blockPopup(p: Record<string, unknown>, metres: number): string {
  const kinds = [
    Number(p.canopy) > 0 && `${Number(p.canopy).toLocaleString()} under tree canopy`,
    Number(p.open) > 0 && `${Number(p.open).toLocaleString()} open water`,
  ].filter(Boolean);
  const people = Math.round(Number(p.people));
  return `<strong>${Math.max(1, Math.round(Number(p.share) * 100))}% of this ${metres.toLocaleString()} m square flagged as flooded</strong><br/>
    ${Number(p.flagged).toLocaleString()} cells${kinds.length ? `: ${kinds.join(", ")}` : ""}<br/>
    ${people > 0 ? `${people.toLocaleString()} ${people === 1 ? "person lives" : "people live"} in them` : "Nobody lives in them"}<br/>
    <span style="color:#64748b">Zoom in to see each cell</span>`;
}

function cellPopup(p: Record<string, unknown>, metres: number): string {
  const people = Math.round(Number(p.p));
  return `<strong>${KIND_LABELS[Number(p.k)] ?? KIND_LABELS[0]}</strong><br/>
    Confidence ${Math.round(Number(p.c) * 100)}%<br/>
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
