"""Named residential landuse polygons, used to group streets by subdivision.

Ada County has no machine-readable plat metadata -- nothing states "this street
was first named as part of this subdivision". OSM's named `landuse=residential`
polygons are the closest available proxy, and in Ada County they are unusually
complete because the author mapped them from plat scans.

The subdivision NAME is itself strong evidence: streets inside "Celestial
Village" are constellations; inside "Sutter's Mil" they are gold-rush mining
terms; inside "Sportsman Pointe" they are gundog breeds.
"""
import json
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
from shapely.strtree import STRtree
from .config import DATA_DIR

WAYS_FILE = "osm_landuse_geom.json"     # ways, with inline geometry
RELS_FILE = "osm_landuse_rel.json"      # relations + member ways/nodes


def _ring(coords):
    return Polygon(coords) if len(coords) >= 4 else None


def load_polygons() -> tuple[list, list[str]]:
    """Return (geometries, names) for every named residential polygon."""
    polys, names = [], []

    for e in json.loads((DATA_DIR / WAYS_FILE).read_text())["elements"]:
        if e["type"] != "way" or "geometry" not in e:
            continue
        p = _ring([(c["lon"], c["lat"]) for c in e["geometry"]])
        if p is not None and p.is_valid and not p.is_empty:
            polys.append(p); names.append(e["tags"]["name"])

    rel_doc = json.loads((DATA_DIR / RELS_FILE).read_text())["elements"]
    nodes = {e["id"]: (e["lon"], e["lat"]) for e in rel_doc if e["type"] == "node"}
    ways = {e["id"]: e.get("nodes", []) for e in rel_doc if e["type"] == "way"}
    for e in rel_doc:
        if e["type"] != "relation" or not e.get("members"):
            continue
        parts = []
        for mem in e["members"]:
            if mem.get("role") != "outer" or mem["type"] != "way":
                continue
            coords = [nodes[n] for n in ways.get(mem["ref"], []) if n in nodes]
            p = _ring(coords)
            if p is not None:
                parts.append(p.buffer(0))
        if parts:
            u = unary_union(parts)
            if u.is_valid and not u.is_empty:
                polys.append(u); names.append(e["tags"]["name"])
    return polys, names


class SubdivisionIndex:
    def __init__(self):
        self.polys, self.names = load_polygons()
        self.tree = STRtree(self.polys)

    def containing(self, lat: float, lon: float) -> list[str]:
        """Subdivision names whose polygon contains this point."""
        pt = Point(lon, lat)
        return [self.names[i] for i in self.tree.query(pt) if self.polys[i].contains(pt)]

    def nearest(self, lat: float, lon: float, max_m: float = 150.0) -> list[str]:
        """Subdivisions within max_m of the point.

        Needed because streets frequently run ALONG a subdivision boundary
        rather than through the interior, so their centroid falls outside every
        polygon. Degrees are converted crudely; adequate at this latitude.
        """
        pt = Point(lon, lat)
        deg = max_m / 111_320.0
        out = []
        for i in self.tree.query(pt.buffer(deg)):
            if self.polys[i].distance(pt) * 111_320.0 <= max_m:
                out.append(self.names[i])
        return out

    def __len__(self):
        return len(self.polys)
