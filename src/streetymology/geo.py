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

Two words, kept apart everywhere:

  plat          the recorded document and its polygon. What this code measures
                against, and what every identifier here is named for.
  subdivision   the development the plat records. Used only in text a person or
                a model reads, in `prompt.py`, because a reader should not have
                to know what a plat is.
"""
import datetime
import json
import math
import re
from collections import defaultdict

from pyproj import Transformer
from shapely.geometry import MultiPoint, MultiPolygon, Polygon
from shapely.ops import linemerge, transform as shapely_transform, unary_union
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


# Ada County sits in UTM zone 11N. Geometry is projected once, on the way in, so
# every length and distance below is metres straight from shapely rather than a
# formula written here. Lengths in degrees are not comparable across directions:
# a degree of longitude at this latitude is about 72% of a degree of latitude, so
# an east-west street and a north-south one were being measured on different
# scales.
_TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32611", always_xy=True)


def project(geom):
    """lon/lat geometry -> UTM 11N metres."""
    return shapely_transform(lambda xs, ys: _TO_UTM.transform(xs, ys), geom)


def to_utm(lon, lat):
    """A single lon/lat pair -> (x, y) in metres."""
    return _TO_UTM.transform(lon, lat)


def longest_run(pieces, bridge_m=0.0):
    """Longest chain of pieces, joining any two whose ends are within bridge_m.

    `pieces` are (length_m, end, end) tuples rather than geometry, so the
    measuring stage can write them to disk and the selecting stage can vary
    bridge_m without touching a polygon again.
    """
    if not pieces:
        return 0.0
    lens = [pc[0] for pc in pieces]
    if bridge_m <= 0 or len(pieces) == 1:
        return max(lens)
    ends = [(tuple(pc[1]), tuple(pc[2])) for pc in pieces]

    def gap(i, j):
        return min(math.dist(a, b) for a in ends[i] for b in ends[j])

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


def _strands(lines):
    """A place's ways merged into its continuous stretches.

    OSM splits a street wherever an editor stopped, so the ways are merged first
    and only genuine discontinuities survive. Three words are kept apart below:
    a STRAND is a continuous stretch of the street itself, a PIECE is the part of
    a strand lying inside one plat, and a RUN is a chain of pieces joined across
    short excursions outside it.
    """
    merged = linemerge(lines)
    return list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged]


class PlatIndex:
    """Every recorded plat, searchable by geometry."""

    def __init__(self, path=None):
        doc = json.loads((data_path(path or FILE)).read_text())
        self.plats = []
        for f in doc["features"]:
            g = _rings_to_geom(f.get("geometry", {}).get("rings", []))
            if g is None or g.is_empty:
                continue
            g = project(g)
            self.plats.append(Plat(f["attributes"], g))
        self.tree = STRtree([p.geom for p in self.plats])

    def __len__(self):
        return len(self.plats)

    def covering(self, geom):
        """Plats whose polygon intersects `geom`, nearest-in-time order unknown."""
        return [self.plats[i] for i in self.tree.query(geom)
                if self.plats[i].geom.intersects(geom)]

    def pieces_inside(self, lines):
        """plat -> (metres inside, [(length, end, end)] per unbroken piece).

        Pieces are returned rather than a single run length because whether two
        of them count as one run is a judgement -- a plat boundary detours
        around a park parcel or a phase line, and the street through it was
        still laid out by that plat. `longest_run` applies that judgement, in
        the stage that owns it.

        Takes every way of a place at once and merges them first, because OSM
        splits a street at arbitrary points -- a lane change, a bridge, an
        editing session. A "share of a way" therefore measures mapping accidents
        as much as geography. What a plat that LAID OUT a street produces is a
        long unbroken run of it inside the boundary, and that survives however
        the ways were split.
        """
        strands = _strands(lines)
        out = {}
        for p in self.covering(linemerge(lines)):
            total, pieces = 0.0, []
            for strand in strands:
                try:
                    inter = strand.intersection(p.geom)
                except Exception:                                 # noqa: BLE001
                    inter = strand.intersection(p.geom.buffer(0))
                if inter.is_empty:
                    continue
                for piece in (list(inter.geoms) if hasattr(inter, "geoms")
                              else [inter]):
                    if piece.geom_type != "LineString":
                        continue
                    total += piece.length
                    pieces.append((piece.length, piece.coords[0],
                                   piece.coords[-1]))
            if total > 0:
                out[p] = (total, pieces)
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
        strands = _strands(lines)
        total = sum(s.length for s in strands)
        covering = [p.geom for p in self.covering(linemerge(lines))]
        if not covering:
            return 0.0, total
        u = unary_union(covering)
        inside = 0.0
        for strand in strands:
            try:
                inter = strand.intersection(u)
            except Exception:                                     # noqa: BLE001
                inter = strand.intersection(u.buffer(0))
            if inter.is_empty:
                continue
            for piece in (list(inter.geoms) if hasattr(inter, "geoms") else [inter]):
                if piece.geom_type == "LineString":
                    inside += piece.length
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
# Ways, alignments, places, duplicates.
#
#   way         what OSM stores: a street cut into pieces at intersections,
#               bridges, or wherever an editor stopped.
#   alignment   ways that run along the same line and continue each other. A
#               purely geometric relation -- collinear, same heading -- with no
#               claim about who built the street or what it was named after.
#   place       alignments close enough together to be the same street in one
#               location. This is the unit everything downstream works in.
#   duplicate   alignments of the same name too far apart to be one street: the
#               same word chosen twice in different parts of the county. They
#               become separate places and share no context.
# ----------------------------------------------------------------------

# Ada County's grid puts a mile between arterials, so a break shorter than this
# is one street interrupted rather than two.
LINK_M = 2000.0
# Beyond this, two alignments of one name are duplicates, not one street.
SPLIT_M = 5000.0

# Classes a developer plausibly named. Anything above tertiary is a public road
# that predates the plats it crosses.
ANALYSED_CLASSES = {"residential", "unclassified", "tertiary", "living_street"}


def metres(a, b):
    """Distance between two projected (x, y) points, in metres."""
    return math.dist(a, b)


def bearing(a, b):
    """Direction of a->b in degrees, folded to 0-180 so it has no compass sense."""
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0


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


def _min_dist(a_pts, b_pts, stop_at=None):
    """Closest approach between two projected point sets, in metres.

    `stop_at` is accepted and ignored: shapely indexes both sets, which beats
    the early exit the hand-rolled double loop needed.
    """
    return MultiPoint(list(a_pts)).distance(MultiPoint(list(b_pts)))


def _components(items, pts_of, gap, test):
    """Single-linkage grouping of `items`.

    `test(pts, members, gap)` decides linkage, and there is no default: the two
    callers mean different things by "connected". `_same_location` is closest
    approach; `_same_alignment` also demands the pieces be collinear.
    """
    groups = []
    for it in items:
        pts = pts_of(it)
        hits = [g for g in groups if test(pts, g["members"], gap)]
        if not hits:
            groups.append({"items": [it], "pts": list(pts), "members": [list(pts)]})
            continue
        first = hits[0]
        first["items"].append(it)
        first["pts"].extend(pts)
        first["members"].append(list(pts))
        for other in hits[1:]:
            first["items"].extend(other["items"])
            first["pts"].extend(other["pts"])
            first["members"].extend(other["members"])
            groups.remove(other)
    return groups


def _same_alignment(pts, members, gap):
    """On one line: touching, or resuming collinearly after a break."""
    return any(continues(pts, m, gap) for m in members)


def _same_location(pts, members, gap):
    """Near each other, whatever their heading. Not a claim of alignment."""
    return any(_min_dist(pts, m, gap) <= gap for m in members)


class Place:
    """One core name in one location, with every way that carries it."""

    __slots__ = ("core", "index", "ways", "points", "classes", "analysed")

    def __init__(self, core, index, ways, points):
        self.core = core
        self.index = index
        self.ways = ways
        self.points = points
        self.classes = {w["highway"] for w in ways}
        # One arterial way disqualifies the whole place, not just that way: an
        # arterial predates the plats it crosses, and a place is one street.
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
    """core name -> [Place], in two steps.

    Ways carrying the name are grouped into alignments, then alignments within
    `split_m` of each other into places. Alignments left apart are duplicates and
    get a place each, so nothing is carried between them.
    """
    out = {}
    for core, ways in ways_by_core.items():
        alignments = _components(ways, lambda w: w["points"], link_m,
                                 _same_alignment)
        located = (_components(alignments, lambda g: g["pts"], split_m,
                               _same_location)
                   if len(alignments) > 1
                   else [{"items": alignments, "pts": alignments[0]["pts"]}])
        out[core] = [
            Place(core, i, [w for g in loc["items"] for w in g["items"]],
                  loc["pts"])
            for i, loc in enumerate(located)]
    return out
