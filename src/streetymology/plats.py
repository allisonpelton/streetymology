"""Recorded plats: their polygons, and which of them are one naming act.

The Ada County Assessor is the authority on subdivisions, in place of OSM
`landuse=residential`, a hand-traced proxy for this layer. It carries three
things OSM cannot: `RecordedDate`, so the earliest of several plats covering a
street can be taken as the one that named it; complete coverage, including
plats that are not residential landuse today; and phase structure.

`PlatIndex` builds the polygons, groups them into families, names each family,
and answers geometric questions about how much of a street falls inside what.

Geometry is projected to UTM 11N on the way in, so every length and distance is
metres straight from shapely. How a plat name is read is not here; that is
`platnames`.
"""
import collections
import datetime
import json
import logging

import pyproj
import shapely
import shapely.ops

from streetymology.grouping import single_linkage
from streetymology.platnames import ORD_BASE, ORDINAL, base_name, display_name, excluded, judgement
from streetymology.platparse import ADD_W, AMD_ANY

from .config import data_path

log = logging.getLogger(__name__)

FILE = "assessor_subdivisions.json"

# Ada County is in UTM zone 11N. Geometry is projected once, on the way in, so
# every length and distance below is metres straight from shapely rather than a
# formula written here. Lengths in degrees are not comparable across directions:
# a degree of longitude at this latitude is about 72% of a degree of latitude, so
# an east-west street and a north-south one would be measured on different
# scales.
_TO_UTM = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32611", always_xy=True)


def to_utm(lon, lat):
    """A single lon/lat pair -> (x, y) in metres."""
    return _TO_UTM.transform(lon, lat)


def _rings_to_geom(rings):
    """ESRI rings -> shapely. Clockwise rings are outer, counter-clockwise holes.

    The shoelace formula gives a polygon's area from its vertices alone: sum
    x1*y2 - x2*y1 over each adjacent pair, then halve. Only the sign is wanted
    here. Walking a ring counter-clockwise gives a positive number, clockwise a
    negative one, and ESRI writes outer rings clockwise in screen order.

    `shapely.LinearRing.is_ccw` answers the same question and is worse on this
    data. The two disagree on 23 of 8,986 rings, every one self-intersecting.
    A figure-eight winds one way in each lobe, so the areas nearly cancel and
    the sign near zero is arbitrary. `is_ccw` calls those counter-clockwise,
    which makes them holes punched into their own plat. Harris Ranch No 09 then
    takes Sawmill from a platted share of 1.0 to 0.568, and 112 places move.
    The sign test keeps them as outer rings and buffer(0) below repairs them.
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
        shell = shapely.Polygon(o)
        if not shell.is_valid:
            shell = shell.buffer(0)
        inner = [h for h in holes if shell.contains(shapely.Polygon(h).representative_point())]
        p = shapely.Polygon(o, inner) if inner else shell
        polys.append(p if p.is_valid else p.buffer(0))
    if not polys:
        return None
    g = polys[0] if len(polys) == 1 else shapely.MultiPolygon(
        [q for p in polys for q in shapely.get_parts(p)])
    return g if g.is_valid else g.buffer(0)


class Plat:
    __slots__ = ("oid", "name", "base", "family", "recorded", "tax_year", "geom")

    def __init__(self, attrs, geom):
        self.oid = attrs["OBJECTID"]
        self.name = (attrs.get("SubdivisionName") or "").strip()
        self.base = base_name(self.name)
        # The assessor stores RecordedDate as epoch milliseconds UTC.
        ms = attrs.get("RecordedDate")
        self.recorded = (
            datetime.datetime.fromtimestamp(ms / 1000, datetime.UTC).date()
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
        except shapely.errors.ShapelyError:
            inter = stretch.intersection(geom.buffer(0))
        if inter.is_empty:
            continue
        out.extend(p for p in shapely.get_parts(inter)
                   if p.geom_type == "LineString")
    return out


def _stretches(lines):
    """The unbroken runs of road surface that `lines` add up to.

    OSM cuts a street wherever an editor stopped, so merging first leaves only
    the genuine gaps.
    """
    return list(shapely.get_parts(shapely.ops.linemerge(lines)))


# Two plats of one name are one naming act only if they are in one place. Home
# Acres is ten polygons scattered over 7 km and Randall Acres seventeen over 15,
# one landowner's name reused across the city rather than one development. Left
# ungrouped, every street in any Randall Acres parcel is a peer of every other,
# across the full 15 km.
FAMILY_M = 1000.0


def _cluster(plats, gap=FAMILY_M):
    """Single-linkage grouping of plats within `gap`, biggest cluster first."""
    clusters = single_linkage(
        [[p] for p in plats],
        lambda g, o: any(p.geom.distance(q.geom) <= gap for p in g for q in o),
        list.extend)
    return sorted(clusters, key=lambda c: -len(c))


def _cluster_suffix(plat):
    """What distinguishes one filing from its siblings: ordinal, then type.

    Ada County does not allow two plats to carry the same name, so a merged
    group that splits on distance can always be told apart by what the record
    already says. Randall Sub and Randall Addition are different filings, which
    is the distinction AP drew on Stein.
    """
    m = ORD_BASE.match(plat.base)
    out = ""
    if m:
        out = " " + ORDINAL.sub(lambda x: x.group(1) + x.group(2).lower(),
                                 plat.base[len(m.group(1)):].strip())
    for w in ("NORTH", "SOUTH", "EAST", "WEST"):
        if plat.base.endswith(" " + w):
            out += " " + w.title()
    a = ADD_W.search(plat.name.upper())
    if a:
        out += " Addition"
        if a.group("city"):
            out += " to " + a.group("city").strip().title()
    return out


def _label_clusters(clusters, judged):
    """Label every cluster of a merged group. Warns if two labels collide."""
    if len(clusters) == 1:
        live = [q for q in clusters[0]
                if not AMD_ANY.search(" " + q.name.upper() + " ")] or clusters[0]
        earliest = min(live, key=lambda q: str(q.recorded or "9999"))
        return [judged or display_name(earliest.name, designated=False)]
    labels = []
    for c in clusters:
        live = [q for q in c if not AMD_ANY.search(" " + q.name.upper() + " ")] or c
        earliest = min(live, key=lambda q: str(q.recorded or "9999"))
        labels.append(display_name(earliest.name, scattered=True))
    dupes = {l for l in labels if labels.count(l) > 1}
    if dupes:
        # Ada County does not permit two plats to share a name, so this is
        # not one. It is a stray polygon, or geometry that split a family.
        log.warning("cluster labels collide for %s: two filings of one name that "
                    "the record does not distinguish. Check for a stray polygon "
                    "rather than labelling around it", sorted(dupes))
    return labels


def _families(plats, gap=FAMILY_M):
    """Split each base name into geographically connected families."""
    out = {}
    by_base = collections.defaultdict(list)
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
            g = shapely.ops.transform(_TO_UTM.transform, g)
            plat = Plat(f["attributes"], g)
            if plat.name.upper() in excluded():
                continue
            self.plats.append(plat)
        self.tree = shapely.STRtree([p.geom for p in self.plats])
        fams = _families(self.plats)
        for p in self.plats:
            p.family = fams[p.oid]
        # Contiguity, for the display name. A name whose numbered plats sit
        # in one family is a phased development. One spread across families is
        # a name someone reused: Randall Acres over four, Home Acres over
        # three.
        self._apply_merges()
        spread = collections.defaultdict(set)
        for p in self.plats:
            spread[p.base].add(p.family)
        self.scattered = {b for b, f in spread.items() if len(f) > 1}
        self._name_families()


    def _apply_merges(self):
        """Fold hand-judged merges into the families computed above.

        Judgement joins names and geometry still splits them. A merge lists
        base names that are one naming act, then the family distance applies
        again across the union, so a listed base sitting far from the rest
        still comes out on its own. That is why Seamans 02nd stays out of
        Seaman's without anyone having to say so twice.
        """
        self.merged_label = {}
        doc = judgement()
        present = {p.base for p in self.plats}
        groups = [(e["label"], [b for b in e["bases"] if b in present])
                  for e in doc.get("merge", ())]
        # Ordinal filings are phases of one development: Dundee 1st, 2nd and
        # 3rd, Hidden Springs 1st through 9th. They merge at the family level
        # while the phase layer keeps the ordinal visible, which is what AP
        # wanted preserved. Distance still splits them afterwards.
        ordinal_stem = collections.defaultdict(set)
        for b in present:
            m = ORD_BASE.match(b)
            if m:
                ordinal_stem[m.group(1).strip()].add(b)
        for stem, bs in ordinal_stem.items():
            group = sorted(bs | ({stem} if stem in present else set()))
            if len(group) > 1:
                groups.append((None, group))

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

        members = collections.defaultdict(list)
        for p in self.plats:
            if p.base in parent:
                members[find(p.base)].append(p)
        for root, ps in members.items():
            # Name the family for its shortest base, not the union-find root,
            # which is whichever name the merge list happened to start from.
            stem = min((q.base for q in ps), key=len)
            clusters = _cluster(ps)
            for i, (cluster, label) in enumerate(
                    zip(clusters, _label_clusters(clusters, label_of.get(root)))):
                fam = f"{stem} MERGED" + (f" #{i + 1}" if i else "")
                for q in cluster:
                    q.family = fam
                self.merged_label[fam] = label

    def merged_label_for(self, plat):
        """The judged label for a merged family, or None if it was not judged."""
        return self.merged_label.get(plat.family)

    def _name_families(self):
        """One name per family, settled once.

        It has to be a property of the family, not of whichever plat is in hand.
        Deriving it per plat disagrees with itself: a street takes the earliest
        filing that touches it, "Randall Acres #10", while the polygon for the
        same family takes its earliest filing overall, "#3".

        A judged merge names itself. Otherwise the family's earliest unamended
        filing names it, phase designation dropped but type kept: Ellis Addition
        to Meridian and Ellis Addition to Boise are different developments fifty
        years and one town apart. A scattered name keeps its number, because the
        number is the only thing separating one from the next.
        """
        members = collections.defaultdict(list)
        for p in self.plats:
            members[p.family].append(p)
        self.family_label = {}
        for fam, ps in members.items():
            if fam in self.merged_label:
                self.family_label[fam] = self.merged_label[fam]
                continue
            live = [q for q in ps if not AMD_ANY.search(" " + q.name.upper() + " ")] or ps
            first = min(live, key=lambda q: str(q.recorded or "9999"))
            self.family_label[fam] = display_name(
                first.name, scattered=True,
                designated=first.base in self.scattered)

    def family_name(self, plat):
        """What to call the naming act this plat belongs to."""
        return self.family_label[plat.family]

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

        This returns the pieces rather than one run length because deciding
        whether two pieces count as one run takes judgement. A plat boundary
        detours around a park parcel or a phase line, and that plat still laid
        out the street running through it. `build_context` makes that call, in
        the stage that owns it.

        It takes every way of a place at once and merges them first. OSM splits
        a street at arbitrary points, such as a lane change, a bridge, or an
        editing session, so a share of one way measures mapping accidents as
        much as geography. A plat that laid out a street produces a long
        unbroken run of it inside the boundary, and that survives however the
        ways were split.
        """
        stretches = _stretches(lines)
        out = {}
        for p in self.covering(shapely.ops.linemerge(lines)):
            pieces = [(x.length, x.coords[0], x.coords[-1])
                      for x in _clip(stretches, p.geom)]
            if pieces:
                out[p] = (sum(m for m, _, _ in pieces), pieces)
        return out

    def covered_metres(self, lines):
        """Metres of street lying inside ANY plat, and the merged street length.

        Plats overlap, since an amended plat sits on its original and phases
        abut, so summing per-plat metres counts some of it twice. The union
        says whether a street was platted at all. A town laid out its grid
        streets and developers filed additions along them piecemeal decades
        later, so most of such a street falls inside no plat. That is what
        separates it from a street a developer built.
        """
        stretches = _stretches(lines)
        total = sum(s.length for s in stretches)
        covering = [p.geom for p in self.covering(shapely.ops.linemerge(lines))]
        if not covering:
            return 0.0, total
        inside = sum(x.length for x in _clip(stretches, shapely.unary_union(covering)))
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
            except shapely.errors.ShapelyError:
                inside = line.intersection(p.geom.buffer(0)).length
            if inside > 0:
                out[p] = inside / total
        return out
