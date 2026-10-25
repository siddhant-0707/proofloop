"""FEMA National Flood Hazard Layer (NFHL) flood zones over the Big Bend.

Only Special Flood Hazard Area polygons (SFHA_TF = 'T'; in the Big Bend, zones A,
AE, AH and VE) are kept: everything else, zone X or unmapped, is "outside the flood
zone", where people are least likely to expect flooding or to carry flood insurance.

uv run python -m proofloop.exposure.fema
"""

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from proofloop.nisar.sme2 import BBox
from proofloop.paths import FEMA_DIR

_QUERY = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
_PAGE = 1000
# Simplify polygons to about 20 m, a third of a 60 m World cell.
_SIMPLIFY_DEGREES = 0.0002
_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class FloodZone:
    """One Special Flood Hazard Area polygon."""

    zone: str  # FEMA FLD_ZONE, e.g. "AE"
    rings: tuple[tuple[tuple[float, float], ...], ...]  # polygon rings of (lon, lat)


def zones_file(dest_dir: Path = FEMA_DIR) -> Path:
    return dest_dir / "nfhl-sfha.json"


def download_zones(bbox: BBox, dest_dir: Path = FEMA_DIR) -> Path:
    """Fetch every SFHA polygon intersecting the bounding box, page by page."""
    features: list[dict] = []
    while True:
        params = {
            "where": "SFHA_TF='T'",
            "geometry": f"{bbox.west},{bbox.south},{bbox.east},{bbox.north}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "FLD_ZONE,SFHA_TF",
            "returnGeometry": "true",
            "outSR": "4326",
            "maxAllowableOffset": str(_SIMPLIFY_DEGREES),
            "geometryPrecision": "5",
            "orderByFields": "OBJECTID",
            "resultOffset": str(len(features)),
            "resultRecordCount": str(_PAGE),
            "f": "json",
        }
        url = f"{_QUERY}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as response:
            data = json.load(response)
        if "error" in data:
            raise RuntimeError(f"NFHL query failed: {data['error']}")
        features += data["features"]
        if not data.get("exceededTransferLimit"):
            break

    path = zones_file(dest_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"bbox": _bbox_list(bbox), "features": features}))
    print(f"ok    {path.name} ({len(features)} flood hazard polygons)")
    return path


def cached_for(bbox: BBox, dest_dir: Path = FEMA_DIR) -> bool:
    """Whether the cached zones were downloaded for exactly this bounding box."""
    path = zones_file(dest_dir)
    return path.exists() and json.loads(path.read_text()).get("bbox") == _bbox_list(bbox)


def load_zones(path: Path) -> list[FloodZone]:
    zones = []
    for feature in json.loads(path.read_text())["features"]:
        attributes = feature["attributes"]
        if attributes["SFHA_TF"] != "T":
            continue
        zones.append(
            FloodZone(
                zone=attributes["FLD_ZONE"],
                rings=tuple(
                    tuple((float(x), float(y)) for x, y in ring)
                    for ring in feature.get("geometry", {}).get("rings", [])
                ),
            )
        )
    return zones


def _bbox_list(bbox: BBox) -> list[float]:
    return [bbox.west, bbox.south, bbox.east, bbox.north]


if __name__ == "__main__":
    from proofloop.world.build import BIG_BEND

    download_zones(BIG_BEND)
