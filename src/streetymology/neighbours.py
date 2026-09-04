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
from .config import DATA_DIR
from .normalize import key

RADIUS_M = 200.0
CENTERS_FILE = "osm_ways_center.json"
EXCLUDED_HIGHWAYS = {"trunk"}


def _metres(a, b):
    dy = (a[0] - b[0]) * 111_320.0
    dx = (a[1] - b[1]) * 111_320.0 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


class NeighbourIndex:
    """Grid-bucketed lookup of street names near a point."""

    def __init__(self, radius_m: float = RADIUS_M):
        self.radius = radius_m
        self.segments = defaultdict(list)      # core key -> [(lat, lon), ...]
        self.names = {}
        els = json.loads((DATA_DIR / CENTERS_FILE).read_text())["elements"]
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
        """Core names with any segment within radius of any segment of `core`."""
        out = set()
        for p in self.segments.get(core, ()):
            gy, gx = int(p[0] / self.cell), int(p[1] / self.cell)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    for k2, p2 in self.grid.get((gy + dy, gx + dx), ()):
                        if k2 != core and _metres(p, p2) <= self.radius:
                            out.add(k2)
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
    extra = [k for k in sorted(nidx.near(core)) if k not in peers and k != core]
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
