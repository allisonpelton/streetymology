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

from .config import data_path, SUBDIVISIONS

FILE = "assessor_subdivisions.json"

# Assessor shorthand. SUB=subdivision, ADD=addition, AMD=amended plat.
# UNIT appears both as "UNIT NO 02" and bare, because the assessor writes
# "A T SORENSEN SUB UNIT NO 02": SUB and NO 02 came off and UNIT was left behind,
# so the naming act read as "A T Sorensen Unit". Both forms go.
# Phase numbers carry a letter suffix often enough to matter: "SUB NO 04A",
# "PHASE 01A1", "UNIT NO 02A". `\d+` followed by `\b` cannot match those --
# there is no boundary between "4" and "A" -- so the marker survived and every
# lettered phase read as its own naming act. "PHASE A" has no digits at all.
# A phase letter is written both ways -- "NO 04A" and "NO 03 A" -- so each
# marker accepts an adjacent suffix or a standalone letter token. The `\b` on
# the standalone branch is what stops it eating the S of a following SUB: in
# "NO 01 SUB" there is no boundary between S and U, so the branch fails and
# only "NO 01" comes off. AREA is the same kind of marker: "06TH ADD AREA C".
_TRAIL = re.compile(r"\s+(SUB(DIVISION)?|ADD(ITION)?|AMD|AMENDED|"
                    r"NO\s+\d+(?:\s+[A-Z]\b|[A-Z]?\d*)|"
                    r"#\s*\d+(?:\s+[A-Z]\b|[A-Z]?\d*)|"
                    r"PHASE\s+(?:\d+(?:\s+[A-Z]\b|[A-Z]?\d*)|[A-Z]\b)|"
                    r"AREA\s+(?:\d+(?:\s+[A-Z]\b|[A-Z]?\d*)|[A-Z]\b)|"
                    r"UNIT(\s+\d+(?:\s+[A-Z]\b|[A-Z]?\d*))?)\b", re.I)
# A trailing phase with no marker word in front of it: "PARKCENTER POINTE 01A",
# "CAMELBACK 02". Only zero-padded, which is how the assessor writes phases and
# is what separates them from a number that is part of the name -- CONCEPT 500,
# PINE 43, EDSONS LOT 18, CLOVERDALE RIDGE ESTATES BLOCK 1 all keep theirs.
_BARE_PHASE = re.compile(r"\s+0\d*[A-Z]?\d*$", re.I)
# "LANCASTER TERRACE SUB UNIT NO 01 AND 02 AMD" strips down to a dangling AND.
_STRAND = re.compile(r"\s+(AND|OR)$", re.I)
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
        out = _BARE_PHASE.sub("", out).strip()
        out = _STRAND.sub("", out).strip()
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


# ---------------------------------------------------------------- display ---
# `pretty` collapses a plat to its naming act. These render a plat as itself,
# phase and all, for a reader of the map. The two answer different questions:
# the merged name asserts a likely common etymology, the phase name says when
# specifically a street was named.

_AMD_ANY = re.compile(r"\s*\bAM(D|ENDED)\b(\s+NO\s+\d+)?", re.I)
_SUB_W = re.compile(r"\s*\bSUB(DIVISION)?\b", re.I)
# ADD is kept and spelled out, because "Stein's Addition" and "Stein's" are
# different filings and the map has to be able to say which.
_ADD_W = re.compile(r"\bADD(ITION)?\b(\s+TO\s+(?P<city>[A-Z ]+?))?(?=\s|$)", re.I)
_NO_N = re.compile(r"\bNO\s+(\d+)\s*([A-Z])?(?![A-Z])", re.I)
_PHASE_N = re.compile(r"\bPHASE\s+(\d+)\s*([A-Z])?(?![A-Z])|\bPHASE\s+([A-Z])(?![A-Z])", re.I)
_UNIT_N = re.compile(r"\bUNIT\b(\s+(\d+)\s*([A-Z])?(?![A-Z]))?", re.I)
_AREA_X = re.compile(r"\bAREA\s+(\d+|[A-Z])(?![A-Z])", re.I)
_BLOCK_N = re.compile(r"\bBLOCKS?\s+(\d+(?:\s+AND\s+\d+)?)", re.I)
_ROMAN = re.compile(r"^(?:I{1,3}|IV|VI{0,3}|IX|XI{0,3})$")

# Type words, so "Alscott Rocking A Ranch" and "B Bar B Acres" keep their bare
# letter: a single letter sitting in front of one of these is part of the name,
# not an initial.
_TYPE_WORDS = {"RANCH", "RANCHES", "ACRES", "TOWNHOUSES", "ESTATES", "ESTATE",
               "TRACT", "TRACTS", "HAVEN", "PARK", "PLACE", "ADDITION", "SUB",
               "CONDO", "VILLAS", "MANOR", "GARDENS", "HEIGHTS", "VIEW",
               "VILLAGE", "COURT", "ANNEX", "HOME", "HOMES"}

# Names where the initials rule is wrong and no general rule saves it. Ada
# County only; this list would mean nothing on another dataset.
_NOT_INITIALS = ("TOYS R US", "L AND W", "R AND A LEWIS SURVEY",
                 "CHARLES P O RORKE", "VIGNE D AQUILA")


def _dot_initials(s):
    """A. T. Sorensen, not A T Sorensen. Leading runs and middle runs only."""
    if s.startswith(_NOT_INITIALS):
        return s
    w = s.split()
    i = 0
    while i < len(w) and len(w[i]) == 1 and w[i].isalpha():
        i += 1
    if i >= 2:                      # a lone leading letter is too ambiguous
        w[:i] = [x + "." for x in w[:i]]
    j = 0
    while j < len(w):
        if (len(w[j]) == 1 and w[j].isalpha() and j > 0
                and len(w[j - 1].rstrip(".")) > 1):
            k = j
            while k < len(w) and len(w[k]) == 1 and w[k].isalpha():
                k += 1
            # a trailing letter is not an initial: Circle C, Bobs Point A
            if k < len(w) and w[k].upper() not in _TYPE_WORDS:
                w[j:k] = [x + "." for x in w[j:k]]
                j = k
                continue
        j += 1
    return " ".join(w)


def _titlecase(s):
    m = _TRAILING_THE.match(s)
    if m:
        s = "THE " + m.group(1)
    s = _ORDINAL.sub(lambda m: m.group(1) + m.group(2).lower(), s)
    out = [w if (len(w) > 1 and w.isupper() and _ROMAN.match(w)) else
           (w.title() if w.isupper() else w) for w in s.split()]
    s = " ".join(out)
    s = re.sub(r"(?<!^)\b(Of|The|And|At|In|On|To)\b",
               lambda m: m.group(1).lower(), s)
    return re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), s)


def designation(name):
    """The phase levels of a recorded name, outermost first. ["13","B","3"]."""
    s = _AMD_ANY.sub(" ", " " + (name or "").upper().strip() + " ")
    out = []
    m = _NO_N.search(s)
    u = _UNIT_N.search(s)
    if m:
        out.append(m.group(1).lstrip("0") or "0")
        if m.group(2):
            out.append(m.group(2).upper())
    elif u and u.group(2):
        out.append(u.group(2).lstrip("0") or "0")
        if u.group(3):
            out.append(u.group(3).upper())
    p = _PHASE_N.search(s)
    if p:
        if p.group(3):
            out.append(p.group(3).upper())
        else:
            out.append(p.group(1).lstrip("0") or "0")
            if p.group(2):
                out.append(p.group(2).upper())
    return out


def display_name(name, scattered=False):
    """A recorded plat name as a reader should see it.

    `scattered` comes from the contiguity test: where a name's numbered plats
    sit in one family they are phases of one development and read as "Phase n";
    where they are spread across families the name was simply reused, and
    "Randall Acres #15" is the fifteenth subdivision called that, not its
    fifteenth phase.

    Levels join with a dot, so a spaced letter and an attached one render the
    same -- the assessor writes both "NO 03 A" and "NO 04A" and means one thing.
    """
    s = " " + (name or "").upper().strip() + " "
    s = _AMD_ANY.sub(" ", s)
    levels = designation(name)
    s = _NO_N.sub(" ", s)
    s = _PHASE_N.sub(" ", s)
    s = _UNIT_N.sub(" ", s)
    area = _AREA_X.search(s)
    block = _BLOCK_N.search(s)
    s = _AREA_X.sub(" ", s)
    s = _BLOCK_N.sub(" ", s)
    s = _ADD_W.sub(lambda m: " ADDITION" + (" TO " + m.group("city").strip()
                                            if m.group("city") else "") + " ", s)
    s = _SUB_W.sub(" ", s)
    prev = None
    while s != prev:                 # "UNIT NO 01 AND 02" strands an "AND 02"
        prev = s
        s = _BARE_PHASE.sub("", s.strip())
        s = _STRAND.sub("", s.strip())
    s = _WS.sub(" ", s).strip()
    out = _titlecase(_dot_initials(s))
    if levels:
        joined = ".".join(levels)
        # No comma before "#": "Randall Acres, #15" reads worse than without.
        out += (" #" + joined) if scattered else (", Phase " + joined)
    if block:
        out += " Block " + _WS.sub(" ", block.group(1).strip()).lower().replace(" and ", " and ")
    if area:
        out += " Area " + area.group(1).upper()
    return _WS.sub(" ", out).strip()


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


def _cluster(plats, gap=FAMILY_M):
    """Single-linkage grouping of plats within `gap`, biggest cluster first."""
    clusters = []
    for p in plats:
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
    return sorted(clusters, key=lambda c: -len(c))


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
        for i, c in enumerate(_cluster(group, gap)):
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
        # Contiguity, for the display name. A name whose numbered plats sit in
        # one family is a phased development; one spread across families is a
        # name that was reused -- Randall Acres over four, Home Acres over three.
        self._apply_merges()
        numbered = defaultdict(set)
        for p in self.plats:
            if _NO_N.search(p.name):
                numbered[p.base].add(p.family)
        self.scattered = {b for b, f in numbered.items() if len(f) > 1}


    def _apply_merges(self):
        """Fold hand-judged merges into the families computed above.

        Judgement joins names; geometry still splits them. A merge lists base
        names that are one naming act, and the family distance is re-applied
        across the union -- so a listed base sitting far from the rest comes out
        on its own anyway. That is why Seamans 02nd stays out of Seaman's
        without anyone having to say so twice.
        """
        self.merged_label = {}
        doc = {}
        if SUBDIVISIONS.exists():
            doc = json.loads(SUBDIVISIONS.read_text())
        present = {p.base for p in self.plats}
        groups = [(e["label"], [b for b in e["bases"] if b in present])
                  for e in doc.get("merge", ())]
        d = doc.get("directional", {})
        if d.get("enabled"):
            skip = set(d.get("skip", ()))
            for b in sorted(present):
                for w in ("NORTH", "SOUTH", "EAST", "WEST"):
                    if b.endswith(" " + w):
                        stem = b[:-(len(w) + 1)]
                        if stem in present and stem not in skip:
                            groups.append((None, [stem, b]))
        if not groups:
            return

        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for _, bs in groups:
            for b in bs[1:]:
                parent[find(bs[0])] = find(b)
        label_of = {}
        for lab, bs in groups:
            if lab and bs:
                label_of[find(bs[0])] = lab

        members = defaultdict(list)
        for p in self.plats:
            if p.base in parent:
                members[find(p.base)].append(p)
        for root, ps in members.items():
            # Name the family for its shortest base, not the union-find root,
            # which is whichever name the merge list happened to start from.
            stem = min((q.base for q in ps), key=len)
            for i, cluster in enumerate(_cluster(ps)):
                fam = f"{stem} MERGED" + (f" #{i + 1}" if i else "")
                label = label_of.get(root) or pretty(min((q.base for q in cluster), key=len))
                for q in cluster:
                    q.family = fam
                self.merged_label[fam] = label

    def merged_label_for(self, plat):
        """The judged label for a merged family, or None if it was not judged."""
        return self.merged_label.get(plat.family)

    def label(self, plat):
        """A plat as a reader should see it: phase preserved, not collapsed."""
        return display_name(plat.name, plat.base in self.scattered)

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
