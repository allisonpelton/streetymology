import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from streetymology.normalize import normalize, key, is_reserved


def test_cross_source_join():
    # OSM expands names; the assessor abbreviates. Cores must agree.
    assert key("East 31st Street") == key("E 31st St")


def test_single_directional_strip():
    # "North Star" is the name, not a directional we should eat.
    assert normalize("N North Star Ln") == "North Star"


def test_leading_word_not_directional():
    assert normalize("W Old Hill Rd") == "Old Hill"


def test_asterisk_marks_reserved():
    assert is_reserved("S Jon Snow Avenue*")
    assert normalize("S Jon Snow Avenue*") == "Jon Snow"


def test_never_empties_the_name():
    for n in ["N Hwy 55", "W State St", "Broadway Ramp"]:
        assert normalize(n)
