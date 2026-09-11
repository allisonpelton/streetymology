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
import collections
from collections import defaultdict

from pyproj import Transformer
from shapely.geometry import MultiPoint, MultiPolygon, Polygon
from shapely.ops import linemerge, transform as shapely_transform, unary_union

from streetymology import normalize
from shapely.strtree import STRtree

from .config import data_path

FILE = "assessor_subdivisions.json"

# Assessor shorthand. SUB=subdivision, ADD=addition, AMD=amended plat.
# UNIT appears both as "UNIT NO 02" and bare, because the assessor writes
# "A T SORENSEN SUB UNIT NO 02": SUB and NO 02 came off and UNIT was left behind,
# so the naming act read as "A T Sorensen Unit". Both forms go.
_TRAIL = re.compile(r"\s+(SUB(DIVISION)?|ADD(ITION)?|AMD|AMENDED|"
                    r"NO\s+\d+|#\s*\d+|PHASE\s+\d+|UNIT(\s+\d+)?)\b", re.I)
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
    # .title() gives "Mcintyres"; the name is McIntyres.
    b = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), b)
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


def to_utm(lon, lat):
    """A single lon/lat pair -> (x, y) in metres."""
    return _TO_UTM.transform(lon, lat)


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
    __slots__ = ("oid", "name", "base", "family", "recorded", "tax_year", "geom")

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


def _clip(stretches, geom):
    """The LineString pieces of `stretches` that lie inside `geom`.

    A plat polygon from the assessor is sometimes self-intersecting, so a first
    attempt can raise; buffer(0) repairs it. Both callers need the same dance,
    and an intersection can come back as a point or a collection, neither of
    which has a length worth counting.
    """
    out = []
    for stretch in stretches:
        try:
            inter = stretch.intersection(geom)
        except Exception:                                         # noqa: BLE001
            inter = stretch.intersection(geom.buffer(0))
        if inter.is_empty:
            continue
        parts = list(inter.geoms) if hasattr(inter, "geoms") else [inter]
        out.extend(p for p in parts if p.geom_type == "LineString")
    return out


def _stretches(lines):
    """A place's ways merged into its continuous stretches.

    OSM splits a street wherever an editor stopped, so the ways are merged first
    and only genuine discontinuities survive. Three words are kept apart below:
    a STRETCH is an unbroken run of road surface, a PIECE is the part of a
    stretch lying inside one plat, and a RUN is a chain of pieces joined across
    short excursions outside it.
    """
    merged = linemerge(lines)
    return list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged]


# Two plats of one name are one naming act only if they are in one place. Home
# Acres is ten polygons scattered over 7 km and Randall Acres seventeen over 15,
# one landowner's name reused across the city rather than one development. Left
# ungrouped, every street in any Randall Acres parcel was a peer of every other,
# 44 of them spanning 15 km.
FAMILY_M = 1000.0


def _families(plats, gap=FAMILY_M):
    """Split each base name into geographically connected families."""
    out = {}
    by_base = defaultdict(list)
    for p in plats:
        by_base[p.base].append(p)
    for base, group in by_base.items():
        if len(group) == 1:
            out[group[0].oid] = base
            continue
        clusters = []
        for p in group:
            hit = [c for c in clusters
                   if any(p.geom.distance(q.geom) <= gap for q in c)]
            if not hit:
                clusters.append([p])
                continue
            first = hit[0]
            first.append(p)
            for other in hit[1:]:
                first.extend(other)
                clusters.remove(other)
        for i, c in enumerate(sorted(clusters, key=lambda c: -len(c))):
            for p in c:
                out[p.oid] = base if i == 0 else f"{base} #{i + 1}"
    return out


class PlatIndex:
    """Every recorded plat, searchable by geometry."""

    def __init__(self, path=None):
        doc = json.loads((data_path(path or FILE)).read_text())
        self.plats = []
        for f in doc["features"]:
            g = _rings_to_geom(f.get("geometry", {}).get("rings", []))
            if g is None or g.is_empty:
                continue
            g = shapely_transform(_TO_UTM.transform, g)
            self.plats.append(Plat(f["attributes"], g))
        self.tree = STRtree([p.geom for p in self.plats])
        fams = _families(self.plats)
        for p in self.plats:
            p.family = fams[p.oid]

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
        still laid out by that plat. build_context applies that judgement, in
        the stage that owns it.

        Takes every way of a place at once and merges them first, because OSM
        splits a street at arbitrary points -- a lane change, a bridge, an
        editing session. A "share of a way" therefore measures mapping accidents
        as much as geography. What a plat that LAID OUT a street produces is a
        long unbroken run of it inside the boundary, and that survives however
        the ways were split.
        """
        stretches = _stretches(lines)
        out = {}
        for p in self.covering(linemerge(lines)):
            pieces = [(x.length, x.coords[0], x.coords[-1])
                      for x in _clip(stretches, p.geom)]
            if pieces:
                out[p] = (sum(m for m, _, _ in pieces), pieces)
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
        stretches = _stretches(lines)
        total = sum(s.length for s in stretches)
        covering = [p.geom for p in self.covering(linemerge(lines))]
        if not covering:
            return 0.0, total
        inside = sum(x.length for x in _clip(stretches, unary_union(covering)))
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


# Ada County's grid puts a mile between arterials, so a break shorter than this
# is one street interrupted rather than two.
LINK_M = 2000.0
# Proximity alone, no alignment required. AP ruled on every case between 500 m
# and 5 km: the closest confirmed duplicate is 2,028 m and the widest confirmed
# single street is 1,916 m, which brackets this to 112 metres. Equal to LINK_M
# by coincidence, not by definition -- that one is a gap between COLLINEAR runs.
SPLIT_M = 2000.0
# Ada County is on a section grid, so an east-west street holds one latitude for
# its whole length: two runs of one name in the same band are the same street at
# any separation. Widening this does nothing -- 94% of runs sit inside 150 m and
# the rest wander past 400 m -- so the streets it misses are the ones aligned to
# the Boise River rather than to the grid, which no band width reaches.
GRID_BAND_M = 150.0

# Classes a developer plausibly named. Anything above tertiary is a public road
# that predates the plats it crosses.
ANALYSED_CLASSES = {"residential", "unclassified", "tertiary", "living_street"}


def _length(pts):
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


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
            d = math.dist(p, q)
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


def _components(items, pts_of, gap, test):
    """Group `items` into connected components.

    Graph sense: each item is a node, `test` decides whether two are joined, and
    a component is a maximal set where every member is reachable from every
    other. Reachability is the point -- a way joins another it never touches, so
    long as something links them -- which is how a street that bends around a
    corner stays one thing.

    There is no default `test`, because the two callers mean different things by
    joined: `_same_location` is closest approach, `_same_alignment` also demands
    the two run along one line.
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
    here = MultiPoint(list(pts))
    return any(here.distance(MultiPoint(list(m))) <= gap for m in members)


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
        """Every post-type the place carries, in order of importance.

        Was `ways[0]["name"]`, i.e. whichever way happened to sort first, which
        showed the Ustick arterial as "North Ustick Court" after a short
        offshoot. A place that is part Drive and part Court is both, so it says
        both: "West Largo Drive/Court". Order is POST_RANK, never alphabetical.

        The directional is dropped when the place carries more than one, since
        "East Carol Street" is a claim about a street that also runs north.
        """
        run = collections.Counter()
        for w in self.ways:
            run[w["name"]] += _length(w["points"])
        longest = max(run, key=run.get)

        posts, seen = [], set()
        for w in sorted(self.ways, key=lambda w: -run[w["name"]]):
            post = normalize.parts(w["name"])[2]
            bare = normalize._bare(post)
            if post and bare not in seen:
                seen.add(bare)
                posts.append(post)
        posts.sort(key=normalize.post_rank_token)

        direction, core, _ = normalize.parts(longest)
        dirs = {normalize.parts(w["name"])[0] for w in self.ways}
        dirs.discard("")
        if len(dirs) != 1:
            direction = ""
        return " ".join(x for x in (direction, core, "/".join(posts)) if x)

    def __repr__(self):
        return (f"<Place {self.id} {len(self.ways)} ways "
                f"{'analysed' if self.analysed else 'arterial'}>")


def _band(pts):
    """The grid band a run sits in, or None if it wanders out of one.

    Distance may only ever join two runs, never separate them, so this is a
    third way to be the same street and not a test anything can fail. A run that
    meanders across more than `GRID_BAND_M` has no band, and is left to the
    distance rules that already handle it.
    """
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    dx, dy = max(xs) - min(xs), max(ys) - min(ys)
    axis, lo, hi = ("EW", min(ys), max(ys)) if dx >= dy else ("NS", min(xs), max(xs))
    return None if hi - lo > GRID_BAND_M else (axis, lo, hi)


def _overlap(a, b, band_m):
    return (a and b and a[0] == b[0]
            and a[1] - band_m <= b[2] and b[1] - band_m <= a[2])


def _merge_bands(groups, band_m=GRID_BAND_M):
    """Join groups of one name where ANY of their runs share a grid band.

    Per run, not per group. A section-line arterial jogs at section corners, so
    twenty kilometres of it has no single band; each of its runs does, and one
    of them matching an isolated piece is enough to say they are one street.
    """
    out = []
    for g in groups:
        bands = [b for b in (_band(m) for m in g["members"]) if b]
        hits = [o for o in out
                if any(_overlap(x, y, band_m) for x in bands for y in o["bands"])]
        if not hits:
            out.append({**g, "bands": bands})
            continue
        first = hits[0]
        for other in hits[1:] + [g]:
            first["items"].extend(other["items"])
            first["pts"].extend(other["pts"])
            first["members"].extend(other["members"])
            first["bands"].extend(other.get("bands", bands))
            if other is not g:
                out.remove(other)
    return out


def _split_axes(places, core):
    """Separate a place that holds both north-south and east-west ways.

    On a grid these are different streets that share a word. Joining them made
    Broadway one place spanning East, South and West, and put Garden City's
    West 41st Street with the numbered streets of the other grid. 109 of 8,567
    places were affected.

    Ways with no directional belong to no axis, so they follow the longer half
    rather than forcing a third place.
    """
    out = []
    for place in places:
        groups = collections.defaultdict(list)
        for w in place.ways:
            groups[normalize.axis(w["name"])].append(w)
        if not ({"NS", "EW"} <= set(groups)):
            out.append(place)
            continue
        loose = groups.pop("", [])
        longer = max(("NS", "EW"), key=lambda a: sum(_length(w["points"])
                                                     for w in groups[a]))
        groups[longer].extend(loose)
        for axis in sorted(groups):
            ways = groups[axis]
            if ways:
                out.append(Place(core, 0, ways,
                                 [pt for w in ways for pt in w["points"]]))
    for i, place in enumerate(out):
        place.index = i
    return out


def build(ways_by_core, link_m=LINK_M, split_m=SPLIT_M):
    """core name -> [Place], in two steps.

    Ways carrying the name are grouped into alignments; alignments sharing a
    grid band become one however far apart; what remains is joined by proximity.
    Every step only ever joins, and the band step runs on alignments rather than
    on the blobs proximity makes, because an alignment is collinear and so has a
    band to compare.

    Distance is allowed to prove two runs are the same street, never to prove
    they are not.

    What is left over are duplicates, one place each, sharing no context.
    """
    out = {}
    for core, ways in ways_by_core.items():
        alignments = _components(ways, lambda w: w["points"], link_m,
                                 _same_alignment)
        if len(alignments) > 1:
            alignments = _merge_bands(alignments)
        located = (_components(alignments, lambda g: g["pts"], split_m,
                               _same_location)
                   if len(alignments) > 1
                   else [{"items": alignments, "pts": alignments[0]["pts"]}])
        out[core] = _split_axes(
            [Place(core, i, [w for g in loc["items"] for w in g["items"]],
                   loc["pts"])
             for i, loc in enumerate(located)], core)
    return out
