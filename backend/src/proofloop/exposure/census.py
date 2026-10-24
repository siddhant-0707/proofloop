"""2020 Census block populations for Dixie and Taylor counties, from TIGERweb.

Each block carries its population, area, interior point and polygon rings, so
the World builder can spread people over the cells the block covers.

uv run python -m proofloop.exposure.census
"""

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from proofloop.paths import CENSUS_DIR

# State and county FIPS codes.
COUNTIES = {"12029": "Dixie", "12123": "Taylor"}
_QUERY = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/2/query"
)


@dataclass(frozen=True)
class Block:
    geoid: str
    population: float
    area_m2: float  # land plus water
    point: tuple[float, float]  # interior point, (lon, lat)
    rings: tuple[tuple[tuple[float, float], ...], ...]  # polygon rings of (lon, lat)


def block_files(dest_dir: Path = CENSUS_DIR) -> list[Path]:
    return [dest_dir / f"blocks-{fips}.json" for fips in COUNTIES]


def download_blocks(dest_dir: Path = CENSUS_DIR) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for fips, path in zip(COUNTIES, block_files(dest_dir), strict=True):
        params = {
            "where": f"STATE='{fips[:2]}' AND COUNTY='{fips[2:]}'",
            "outFields": "GEOID,POP100,AREALAND,AREAWATER,INTPTLAT,INTPTLON",
            "returnGeometry": "true",
            "outSR": "4326",
            "geometryPrecision": "5",
            "f": "json",
        }
        with urllib.request.urlopen(f"{_QUERY}?{urllib.parse.urlencode(params)}") as response:
            data = json.load(response)
        if "error" in data or data.get("exceededTransferLimit"):
            raise RuntimeError(f"TIGERweb query for {COUNTIES[fips]} County failed: {data}")
        path.write_text(json.dumps(data))
        print(f"ok    {path.name} ({len(data['features'])} blocks)")
    return block_files(dest_dir)


def load_blocks(path: Path) -> list[Block]:
    blocks = []
    for feature in json.loads(path.read_text())["features"]:
        a = feature["attributes"]
        blocks.append(
            Block(
                geoid=a["GEOID"],
                population=float(a["POP100"]),
                area_m2=float(a["AREALAND"]) + float(a["AREAWATER"]),
                point=(float(a["INTPTLON"]), float(a["INTPTLAT"])),
                rings=tuple(
                    tuple((float(x), float(y)) for x, y in ring)
                    for ring in feature.get("geometry", {}).get("rings", [])
                ),
            )
        )
    return blocks


if __name__ == "__main__":
    download_blocks()
