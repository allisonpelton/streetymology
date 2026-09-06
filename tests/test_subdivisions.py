
from shapely.geometry import Polygon
from streetymology.subdivisions import SubdivisionIndex


def _fake(monkey_polys, monkey_names):
    si = SubdivisionIndex.__new__(SubdivisionIndex)
    from shapely.strtree import STRtree
    si.polys, si.names = monkey_polys, monkey_names
    si.tree = STRtree(monkey_polys)
    return si


SQ = Polygon([(-116.40, 43.60), (-116.39, 43.60), (-116.39, 43.61), (-116.40, 43.61)])


def test_point_inside_is_contained():
    si = _fake([SQ], ["Celestial Village"])
    assert si.containing(43.605, -116.395) == ["Celestial Village"]


def test_point_outside_is_not_contained():
    si = _fake([SQ], ["Celestial Village"])
    assert si.containing(43.50, -116.30) == []


def test_boundary_street_found_by_nearest():
    """Streets often run along a subdivision edge, so their centroid falls
    just outside every polygon."""
    si = _fake([SQ], ["Celestial Village"])
    just_outside = 43.605, -116.4005          # ~40m west of the edge
    assert si.containing(*just_outside) == []
    assert si.nearest(*just_outside, max_m=150) == ["Celestial Village"]


def test_nearest_respects_max_distance():
    si = _fake([SQ], ["Celestial Village"])
    assert si.nearest(43.605, -116.45, max_m=150) == []
