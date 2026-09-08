"""Theme context for a street: subdivision members PLUS physically near streets.

Subdivision membership alone is not adjacency. AP found the case: South Ringtail
Avenue sits in 'Willa Fields' with one other street, while Circinae Way -- the
street that identifies the theme -- is 102 m away inside a different landuse
polygon. Boundaries cut between obviously related streets.

Context is therefore the union of:
  - every street sharing a subdivision polygon, and
  - every street whose centroid is within RADIUS_M.

Distances use per-segment centroids, never the mean centroid of a whole name:
6.7% of names have segments over 1 km from their own mean, and some names repeat
in unrelated parts of the county.
"""
import json
import math
from collections import defaultdict
from .config import data_path
from .normalize import key

RADIUS_M = 200.0
CENTERS_FILE = "osm_ways_center.json"
GEOM_FILE = "osm_ways_geom.json"
EXCLUDED_HIGHWAYS = {"trunk"}

# Way geometry is thinned to this spacing before indexing. Overpass returns a
# node wherever the road bends, so a curved cul-de-sac carries far more points
# than a straight arterial of the same length; thinning evens that out and keeps
# the neighbour scan roughly linear in road length rather than in mapping detail.
THIN_M = 40.0


def _thin(geometry, spacing_m):
    """Keep the first and last node, and one roughly every `spacing_m` between.

    Overpass gives a node per bend, so detail tracks curvature rather than
    length. Endpoints are always kept: a junction is at the end of a way, and
    that is the point most likely to be near another street.
    """
    pts = [(g["lat"], g["lon"]) for g in geometry]
    if len(pts) <= 2:
        return pts
    out, last = [pts[0]], pts[0]
    for p in pts[1:-1]:
        if _metres(last, p) >= spacing_m:
            out.append(p)
            last = p
    out.append(pts[-1])
    return out


def _metres(a, b):
    dy = (a[0] - b[0]) * 111_320.0
    dx = (a[1] - b[1]) * 111_320.0 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


class NeighbourIndex:
    """Grid-bucketed lookup of street names near a point."""

    def __init__(self, radius_m: float = RADIUS_M, use_geometry: bool = True):
        self.radius = radius_m
        self.segments = defaultdict(list)      # core key -> [(lat, lon), ...]
        self.names = {}
        geom_path = data_path(GEOM_FILE)
        self.source = "geometry" if (use_geometry and geom_path.exists()) else "centres"

        if self.source == "geometry":
            # Every node of every way, thinned. A way centroid is not a position
            # for a road: a 1 km way's midpoint is 500 m from the junction it
            # meets, so a street and the street it branches off registered as
            # 500 m apart and never became neighbours.
            els = json.loads(geom_path.read_text())["elements"]
            for e in els:
                if e.get("tags", {}).get("highway") in EXCLUDED_HIGHWAYS:
                    continue
                name = e.get("tags", {}).get("name")
                k = key(name) if name else None
                if not k or not e.get("geometry"):
                    continue
                self.segments[k].extend(_thin(e["geometry"], THIN_M))
                self.names.setdefault(k, name)
        else:
            els = json.loads((data_path(CENTERS_FILE)).read_text())["elements"]
            for e in els:
                if "center" not in e or e["tags"].get("highway") in EXCLUDED_HIGHWAYS:
                    continue
                k = key(e["tags"]["name"])
                if not k:
                    continue
                self.segments[k].append((e["center"]["lat"], e["center"]["lon"]))
                self.names.setdefault(k, e["tags"]["name"])
        self.cell = radius_m / 111_320.0
        self.grid = defaultdict(list)
        for k, pts in self.segments.items():
            for p in pts:
                self.grid[(int(p[0] / self.cell), int(p[1] / self.cell))].append((k, p))

    def near(self, core: str) -> set[str]:
        """Core names with any point within radius of any point of `core`."""
        return set(self.near_distances(core))

    def near_distances(self, core: str) -> dict[str, float]:
        """Core name -> closest approach in metres, for everything in radius.

        Distance is what decides which neighbours survive truncation. Ordering
        alphabetically, as this once did, discards evidence at random once a
        street has more neighbours than the prompt can carry.
        """
        out: dict[str, float] = {}
        for p in self.segments.get(core, ()):
            gy, gx = int(p[0] / self.cell), int(p[1] / self.cell)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    for k2, p2 in self.grid.get((gy + dy, gx + dx), ()):
                        if k2 == core:
                            continue
                        d = _metres(p, p2)
                        if d <= self.radius and d < out.get(k2, float("inf")):
                            out[k2] = d
        return out


def context(core: str, assignments: dict, theme_model, nidx: NeighbourIndex,
            limit: int = 25) -> tuple[str, list[str]]:
    """Return (subdivision name, neighbouring street names) for prompting.

    Subdivision peers come first — they are the stronger signal — then nearby
    streets that the polygon missed.
    """
    subs = theme_model.subdivisions_of(core, assignments)
    sub = max(subs, key=lambda s: len(theme_model.members.get(s, ())), default="")
    peers = [p for p in sorted(theme_model.members.get(sub, set())) if p != core]
    # Nearest first. Subdivision peers still lead, but which non-peers survive
    # the limit is now decided by proximity rather than by the alphabet.
    dists = nidx.near_distances(core)
    extra = [k for k in sorted(dists, key=lambda k: (dists[k], k))
             if k not in peers and k != core]
    names, seen = [], set()
    for k in peers + extra:
        n = nidx.names.get(k) or assignments.get(k, {}).get("name", k)
        n = n.split(" ", 1)[1] if n.split()[0] in ("North", "South", "East", "West") \
            and len(n.split(" ", 1)) > 1 else n
        if n not in seen:
            seen.add(n); names.append(n)
        if len(names) >= limit:
            break
    return sub, names
