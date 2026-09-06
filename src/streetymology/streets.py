"""Load Ada County street names from the cached Overpass extract."""
import json
from .config import data_path
from .normalize import key

EXCLUDED_HIGHWAYS = {"trunk"}


def osm_cores() -> dict[str, str]:
    """Map core-name key -> a representative original OSM name."""
    els = json.loads((data_path("osm_named_ways.json")).read_text())["elements"]
    cores: dict[str, str] = {}
    for e in els:
        if e["tags"].get("highway") in EXCLUDED_HIGHWAYS:
            continue
        cores.setdefault(key(e["tags"]["name"]), e["tags"]["name"])
    cores.pop("", None)
    return cores
