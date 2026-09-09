"""Ada County Assessor subdivision plats — the authority on subdivisions.

Replaces OSM `landuse=residential`, which was a hand-traced proxy for exactly
this layer. Three things the assessor has that OSM cannot give:

  - `RecordedDate`, so when several plats cover one street the EARLIEST can be
    taken as the one that named it;
  - complete coverage, including plats that are not residential landuse today;
  - phase structure, since "SUTTERS MILL SUB NO 3" is phase 3 of one naming act,
    not a separate subdivision.

Names arrive in assessor shorthand: upper case, with `SUB`, `ADD`, `AMD` and a
`NO n` phase marker. `base_name()` strips those to the naming act; `pretty()`
produces something a prompt can show a model.
"""
import datetime
import json
import math
import re

from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import linemerge, unary_union
from shapely.strtree import STRtree

from .config import data_path

FILE = "assessor_subdivisions.json"

# Assessor shorthand. SUB=subdivision, ADD=addition, AMD=amended plat.
_TRAIL = re.compile(r"\s+(SUB(DIVISION)?|ADD(ITION)?|AMD|AMENDED|"
                    r"NO\s+\d+|#\s*\d+|PHASE\s+\d+|UNIT\s+\d+)\b", re.I)
# "EAST SIDE ADD TO BOISE" is an addition to a city: the naming act is "East
# Side", and the city is not part of it.
_ADD_TO = re.compile(r"\s+ADD(ITION)?\s+TO\s+.*$", re.I)
# "COUNTRY CLUB THE" is the assessor's filing order for "The Country Club".
_TRAILING_THE = re.compile(r"^(.*?),?\s+THE$", re.I)
_WS = re.compile(r"\s+")


def base_name(name: str) -> str:
    """The naming act behind a plat: phase and plat-type words removed.

    'SUTTERS MILL SUB NO 3' and 'SUTTERS MILL SUB NO 4' are one theme.
    """
    prev = None
    out = _ADD_TO.sub("", (name or "").strip())
    while out != prev:
        prev = out
        out = _TRAIL.sub("", out).strip()
    m = _TRAILING_THE.match(out)
    if m:
        out = f"THE {m.group(1)}"
    return _WS.sub(" ", out)


# "HIGHLANDS THE UNIT" is "The Highlands, Unit 1" in the assessor's filing
# order. _TRAIL removes "UNIT 01" but not a bare "UNIT", so THE is stranded
# mid-string and the trailing-THE rule below never fires. Only invert when THE
# is followed by a plat-type word: "LUCY IN THE SKY" and "LEXINGTON ON THE RIM"
# mean what they say.
_THE_PLAT_TYPE = re.compile(r"^(.*?)\s+THE\s+(?:UNIT|TRACTS?|CONDO)$", re.I)
# The assessor zero-pads ordinals and _TRAIL leaves them, so .title() produced
# "02Nd". Display-only: base_name still sees the original, so nothing regroups.
_ORDINAL = re.compile(r"\b0*(\d+)(st|nd|rd|th)\b", re.I)


def pretty(name: str) -> str:
    """Title-cased base name for showing to a model or a reader."""
    b = base_name(name)
    m = _THE_PLAT_TYPE.match(b)
    if m:
        b = f"THE {m.group(1)}"
    b = b.title()
    # Lower-case only INTERIOR articles: "The Highlands" keeps its capital.
    b = re.sub(r"(?<!^)\b(Of|The|And|At|In|On)\b", lambda m: m.group(1).lower(), b)
    # "02Nd" -> "2nd". Kept numeric: "52nd Street Condo" is a street name, and
    # "Fifty-Second Street" would be wrong.
    b = _ORDINAL.sub(lambda m: m.group(1) + m.group(2).lower(), b)
    return b


def _line_metres(line):
    """Length of a lon/lat LineString in metres."""
    cs = list(line.coords)
    t = 0.0
    for (x1, y1), (x2, y2) in zip(cs, cs[1:]):
        dy = (y2 - y1) * 111_320.0
        dx = (x2 - x1) * 111_320.0 * math.cos(math.radians(y1))
        t += math.hypot(dx, dy)
    return t


def _longest_run(pieces, bridge_m=0.0):
    """Longest chain of pieces, joining any two whose ends are within bridge_m."""
    lens = [_line_metres(p) for p in pieces]
    if not pieces:
        return 0.0
    if bridge_m <= 0 or len(pieces) == 1:
        return max(lens)
    ends = [(p.coords[0], p.coords[-1]) for p in pieces]

    def gap(i, j):
        best = float("inf")
        for a in ends[i]:
            for b in ends[j]:
                dy = (b[1] - a[1]) * 111_320.0
                dx = (b[0] - a[0]) * 111_320.0 * math.cos(math.radians(a[1]))
                best = min(best, math.hypot(dx, dy))
        return best

    seen, best = set(), 0.0
    for i in range(len(pieces)):
        if i in seen:
            continue
        stack, total = [i], 0.0
        seen.add(i)
        while stack:
            k = stack.pop()
            total += lens[k]
            for j in range(len(pieces)):
                if j not in seen and gap(k, j) <= bridge_m:
                    seen.add(j)
                    stack.append(j)
        best = max(best, total)
    return best


def _rings_to_geom(rings):
    """ESRI rings -> shapely. Clockwise rings are outer, counter-clockwise holes.

    Shoelace sign decides; ESRI writes outer rings clockwise in screen order,
    which is a NEGATIVE signed area in standard orientation.
    """
    outers, holes = [], []
    for r in rings:
        if len(r) < 4:
            continue
        area = sum((r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1])
                   for i in range(len(r) - 1)) / 2.0
        (holes if area > 0 else outers).append(r)
    polys = []
    for o in outers:
        shell = Polygon(o)
        if not shell.is_valid:
            shell = shell.buffer(0)
        inner = [h for h in holes if shell.contains(Polygon(h).representative_point())]
        p = Polygon(o, inner) if inner else shell
        polys.append(p if p.is_valid else p.buffer(0))
    if not polys:
        return None
    g = polys[0] if len(polys) == 1 else MultiPolygon(
        [q for p in polys for q in (p.geoms if p.geom_type == "MultiPolygon" else [p])])
    return g if g.is_valid else g.buffer(0)


class Plat:
    __slots__ = ("oid", "name", "base", "recorded", "tax_year", "geom")

    def __init__(self, attrs, geom):
        self.oid = attrs["OBJECTID"]
        self.name = (attrs.get("SubdivisionName") or "").strip()
        self.base = base_name(self.name)
        ms = attrs.get("RecordedDate")
        self.recorded = (datetime.datetime.utcfromtimestamp(ms / 1000).date()
                         if ms is not None else None)
        self.tax_year = attrs.get("InitialTaxYear")
        self.geom = geom

    @property
    def year(self):
        return self.recorded.year if self.recorded else self.tax_year

    def __repr__(self):
        return f"<Plat {self.name!r} {self.year}>"


class PlatIndex:
    """Every recorded plat, searchable by geometry."""

    def __init__(self, path=None):
        doc = json.loads((data_path(path or FILE)).read_text())
        self.plats = []
        for f in doc["features"]:
            g = _rings_to_geom(f.get("geometry", {}).get("rings", []))
            if g is None or g.is_empty:
                continue
            self.plats.append(Plat(f["attributes"], g))
        self.tree = STRtree([p.geom for p in self.plats])

    def __len__(self):
        return len(self.plats)

    def covering(self, geom):
        """Plats whose polygon intersects `geom`, nearest-in-time order unknown."""
        return [self.plats[i] for i in self.tree.query(geom)
                if self.plats[i].geom.intersects(geom)]

    def runs_inside(self, lines, bridge_m=0.0):
        """plat -> (metres inside, longest run, number of separate pieces).

        `bridge_m` tolerates a street leaving the plat and coming straight back:
        two pieces whose ends are within that distance count as one run. A plat
        boundary detours around a park parcel, a school site or a phase line,
        and the street that runs through it was still laid out by that plat.

        Takes every way of a place at once and merges them first, because OSM
        splits a street at arbitrary points -- a lane change, a bridge, an
        editing session. A "share of a way" therefore measures mapping accidents
        as much as geography. What a plat that LAID OUT a street produces is a
        long unbroken run of it inside the boundary, and that survives however
        the ways were split.
        """
        merged = linemerge(lines)
        parts = list(merged.geoms) if merged.geom_type == "MultiLineString" \
            else [merged]
        out = {}
        for p in self.covering(merged):
            total, pieces = 0.0, []
            for part in parts:
                try:
                    inter = part.intersection(p.geom)
                except Exception:                                 # noqa: BLE001
                    inter = part.intersection(p.geom.buffer(0))
                if inter.is_empty:
                    continue
                for piece in (list(inter.geoms) if hasattr(inter, "geoms")
                              else [inter]):
                    if piece.geom_type != "LineString":
                        continue
                    m = _line_metres(piece)
                    total += m
                    pieces.append(piece)
            if total > 0:
                out[p] = (total, _longest_run(pieces, bridge_m), len(pieces))
        return out

    def covered_metres(self, lines):
        """Metres of street lying inside ANY plat, and the merged street length.

        Plats overlap -- an amended plat sits on its original, phases abut -- so
        summing per-plat metres double counts. The union is what says whether a
        street was platted at all. A grid street laid out by a town, with
        additions filed piecemeal along it decades later, is mostly NOT inside
        any plat, and that is what distinguishes it from a street a developer
        built.
        """
        merged = linemerge(lines)
        parts = list(merged.geoms) if merged.geom_type == "MultiLineString" \
            else [merged]
        total = sum(_line_metres(p) for p in parts)
        covering = [p.geom for p in self.covering(merged)]
        if not covering:
            return 0.0, total
        u = unary_union(covering)
        inside = 0.0
        for part in parts:
            try:
                inter = part.intersection(u)
            except Exception:                                     # noqa: BLE001
                inter = part.intersection(u.buffer(0))
            if inter.is_empty:
                continue
            for piece in (list(inter.geoms) if hasattr(inter, "geoms") else [inter]):
                if piece.geom_type == "LineString":
                    inside += _line_metres(piece)
        return inside, total

    def share_inside(self, line):
        """plat -> fraction of `line`'s length inside that plat.

        Membership is a matter of degree: a street can run along a boundary, be
        cut by one, or lie wholly inside. AP's constraint is that the prompt must
        not assert membership at full confidence, so the share is what gets
        reported rather than a yes/no.
        """
        out = {}
        total = line.length
        if total <= 0:
            return out
        for p in self.covering(line):
            try:
                inside = line.intersection(p.geom).length
            except Exception:                                 # noqa: BLE001
                inside = line.intersection(p.geom.buffer(0)).length
            if inside > 0:
                out[p] = inside / total
        return out


# ----------------------------------------------------------------------
# Places: a street name in ONE location, built on the plats above.
# ----------------------------------------------------------------------

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
