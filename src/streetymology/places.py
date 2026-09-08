"""A street name in ONE location: the real unit of etymology.

A core name is not a place. `boise` is a dozen unrelated streets; `mason creek`
is one alignment interrupted by farmland. Until now both were merged into a
single context blob, so a theme could be imported from four miles away.

Two thresholds, both AP's:

  LINK_M = 2000   Ada County's grid puts a mile between arterials, so a gap
                  under about 2 km is one alignment interrupted, not two
                  streets. Ways chained within this distance are one alignment.
  SPLIT_M = 5000  Alignments further apart than this are separate etymology
                  units -- different cities, different developers, the same
                  word chosen twice.

Alignments between 2 km and 5 km apart are therefore joined back into one unit:
separation alone is not evidence of a separate naming act.

ARTERIAL CONTAMINATION -- AP's Five Mile rule. Five Mile Road is a section-line
arterial whose dead-end remnants are tagged `residential`. Class is a property of
the WAY, so a filter on class alone would analyse those remnants as if a
developer had named them. If ANY way on an alignment is above tertiary, the whole
alignment is arterial and none of it is analysed.
"""
import math
from collections import defaultdict

LINK_M = 2000.0
SPLIT_M = 5000.0

# Classes a developer plausibly named. Anything above tertiary is a public road
# that predates the plats it crosses.
ANALYSED_CLASSES = {"residential", "unclassified", "tertiary", "living_street"}
# Thinning for the distance tests only; alignment linking is coarse by nature.
THIN_M = 100.0


def metres(a, b):
    dy = (a[0] - b[0]) * 111_320.0
    dx = (a[1] - b[1]) * 111_320.0 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def _thin(pts, spacing=THIN_M):
    if len(pts) <= 2:
        return list(pts)
    out, last = [pts[0]], pts[0]
    for p in pts[1:-1]:
        if metres(last, p) >= spacing:
            out.append(p)
            last = p
    out.append(pts[-1])
    return out


def bearing(a, b):
    """Compass-free direction of a->b in degrees, folded to 0-180."""
    dy = (b[0] - a[0]) * 111_320.0
    dx = (b[1] - a[1]) * 111_320.0 * math.cos(math.radians(a[0]))
    return math.degrees(math.atan2(dy, dx)) % 180.0


def _angle_gap(a, b):
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def _ends(pts):
    """Both endpoints, each with the bearing of the run leading to it."""
    if len(pts) < 2:
        return []
    return [(pts[0], bearing(pts[1], pts[0])), (pts[-1], bearing(pts[-2], pts[-1]))]


def continues(a_pts, b_pts, gap, max_angle=30.0):
    """True if b is the same road as a, resuming after an interruption.

    Proximity alone merged East Chester Lane with West Chester Drive, two
    unrelated streets 400 m apart in plats 47 years apart. A real interruption
    -- a canal, a school, a section line -- leaves the road pointing the same
    way and resuming ahead of itself, so require BOTH: endpoints within `gap`,
    and the gap collinear with the runs on either side of it.
    """
    for p, ba in _ends(a_pts):
        for q, bb in _ends(b_pts):
            d = metres(p, q)
            if d > gap:
                continue
            if d < 1.0:
                return True
            bg = bearing(p, q)
            if (_angle_gap(ba, bb) <= max_angle
                    and _angle_gap(ba, bg) <= max_angle
                    and _angle_gap(bb, bg) <= max_angle):
                return True
    return False


def _min_dist(a_pts, b_pts, stop_at):
    """Closest approach between two point sets, abandoning once under stop_at."""
    best = float("inf")
    for p in a_pts:
        for q in b_pts:
            d = metres(p, q)
            if d < best:
                best = d
                if best <= stop_at:
                    return best
    return best


def _components(items, pts_of, gap, test=None):
    """Single-linkage grouping of `items`.

    `test(pts, group_points, gap)` decides linkage; the default is closest
    approach, which is right for "are these the same PLACE" but wrong for "are
    these the same ROAD" -- see `continues`.
    """
    test = test or (lambda a, b, g: _min_dist(a, b, g) <= g)
    groups = []
    for it in items:
        pts = pts_of(it)
        hits = [g for g in groups if test(pts, g["parts"], gap)]
        if not hits:
            groups.append({"items": [it], "pts": list(pts), "parts": [list(pts)]})
            continue
        first = hits[0]
        first["items"].append(it)
        first["pts"].extend(pts)
        first["parts"].append(list(pts))
        for other in hits[1:]:
            first["items"].extend(other["items"])
            first["pts"].extend(other["pts"])
            first["parts"].extend(other["parts"])
            groups.remove(other)
    return groups


def _road_test(pts, parts, gap):
    """Same road: touching, or resuming collinearly after a gap."""
    return any(continues(pts, part, gap) for part in parts)


def _place_test(pts, parts, gap):
    """Same place: anything within `gap` of anything."""
    return any(_min_dist(pts, part, gap) <= gap for part in parts)


class Place:
    """One core name in one location, with every way that carries it."""

    __slots__ = ("core", "index", "ways", "points", "classes", "analysed")

    def __init__(self, core, index, ways, points):
        self.core = core
        self.index = index
        self.ways = ways
        self.points = points
        self.classes = {w["highway"] for w in ways}
        # Five Mile rule: contamination is a property of the alignment.
        self.analysed = bool(self.classes) and self.classes <= ANALYSED_CLASSES

    @property
    def id(self):
        return f"{self.core}#{self.index}"

    @property
    def name(self):
        return self.ways[0]["name"]

    def __repr__(self):
        return (f"<Place {self.id} {len(self.ways)} ways "
                f"{'analysed' if self.analysed else 'arterial'}>")


def build(ways_by_core, link_m=LINK_M, split_m=SPLIT_M):
    """core -> [Place]. `ways_by_core` maps core key to way dicts with points."""
    out = {}
    for core, ways in ways_by_core.items():
        thinned = {id(w): _thin(w["points"]) for w in ways}
        aligns = _components(ways, lambda w: thinned[id(w)], link_m, _road_test)
        # Alignments closer than split_m are one etymology unit after all.
        # Alignments closer than split_m are one etymology unit: the same
        # developer naming two nearby streets, not two coincidental choices.
        units = _components(aligns, lambda g: g["pts"], split_m, _place_test) \
            if len(aligns) > 1 else [{"items": aligns, "pts": aligns[0]["pts"]}]
        places = []
        for i, u in enumerate(units):
            ws = [w for g in u["items"] for w in g["items"]]
            places.append(Place(core, i, ws, u["pts"]))
        out[core] = places
    return out
