"""OSM ways grouped into places: one core name in one location.

Ways carrying a name are grouped into alignments, alignments sharing a grid
band become one however far apart, and what is left is joined by proximity.
Every step only ever joins. Distance is allowed to prove two runs are the same
street, never to prove they are not.

Coordinates here are UTM metres, projected by `plats.to_utm` before they
arrive.
"""
import collections
import math

import shapely

from streetymology import normalize
from streetymology.grouping import single_linkage

# Ada County's grid puts a mile between arterials, so a break shorter than this
# is one street interrupted rather than two.
LINK_M = 2000.0
# Proximity alone, no alignment required. Every case between 500 m and 5 km was
# ruled on by hand. The closest confirmed duplicate is 2,028 m and the widest
# confirmed single street is 1,916 m, so only 112 metres are left to choose in.
# This equals LINK_M by coincidence. LINK_M measures a gap between collinear
# runs, which is a different quantity.
SPLIT_M = 2000.0
# Ada County is on a section grid, so an east-west street holds one latitude
# for its whole length. Two runs of one name in the same band are the same
# street at any separation. Widening this does nothing. 94% of runs sit inside
# 150 m and the rest wander past 400 m, so the ones it misses follow the Boise
# River rather than the grid, and no band width reaches those.
GRID_BAND_M = 150.0

# Classes a developer plausibly named. Anything above tertiary is a public road
# that predates the plats it crosses.
ANALYSED_CLASSES = {"residential", "unclassified", "tertiary", "living_street"}


def _absorb_run_group(first, other):
    """Fold one group of runs into another. `bands` only exists after banding."""
    first["items"].extend(other["items"])
    first["pts"].extend(other["pts"])
    first["members"].extend(other["members"])
    if "bands" in first:
        first["bands"].extend(other["bands"])


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

    Proximity alone merges East Chester Lane with West Chester Drive, two
    unrelated streets 400 m apart in plats 47 years apart. A canal, a school or
    a section line leaves the road pointing the same way and resuming ahead of
    itself. So both tests must pass. The endpoints fall within `gap`, and the
    gap runs collinear with the road on either side of it.
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

    Graph sense. Each item is a node, `test` decides whether two are joined,
    and a component is a maximal set where every member is reachable from every
    other. Reachability is what matters. A way can join another it never
    touches as long as something links them, which is how a street that bends
    around a corner stays one thing.

    `test` has no default, because the two callers mean different things by
    joined. `_same_location` measures closest approach. `_same_alignment` also
    requires that the two run along one line.
    """
    def singleton(it):
        pts = list(pts_of(it))
        return {"items": [it], "pts": list(pts), "members": [pts]}

    return single_linkage(
        [singleton(it) for it in items],
        lambda g, o: test(g["pts"], o["members"], gap),
        _absorb_run_group)


def _same_alignment(pts, members, gap):
    """On one line: touching, or resuming collinearly after a break."""
    return any(continues(pts, m, gap) for m in members)


def _same_location(pts, members, gap):
    """Near each other, whatever their heading. Not a claim of alignment."""
    here = shapely.MultiPoint(list(pts))
    return any(here.distance(shapely.MultiPoint(list(m))) <= gap for m in members)


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

        A place that is part Drive and part Court is both, so it says both,
        as "West Largo Drive/Court". POST_RANK sets the order, never the
        alphabet and never one way's name. Taking one way's name lets a short
        offshoot rename the street, which titles the Ustick arterial "North
        Ustick Court".

        A place carrying more than one directional shows none, because "East
        Carol Street" claims something false about a street that also runs
        north.
        """
        run = collections.Counter()
        for w in self.ways:
            run[w["name"]] += _length(w["points"])
        longest = max(run, key=run.get)

        posts, seen = [], set()
        for w in sorted(self.ways, key=lambda w: -run[w["name"]]):
            post = normalize.parts(w["name"])[2]
            bare = normalize.bare(post)
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
    banded = [{**g, "bands": [b for b in (_band(m) for m in g["members"]) if b]}
              for g in groups]
    return single_linkage(
        banded,
        lambda g, o: any(_overlap(x, y, band_m)
                         for x in g["bands"] for y in o["bands"]),
        _absorb_run_group)


def _split_axes(places, core):
    """Separate a place that holds both north-south and east-west ways.

    On a grid these are different streets that share a word. Joined, Broadway
    becomes one place spanning East, South and West, and Garden City's West 41st
    Street lands with the numbered streets of the other grid.

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
