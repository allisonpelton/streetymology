import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from streetymology.themes import ThemeModel, binom_sf

# A themed subdivision of 6, inside a county where birds are otherwise rare.
# The background streets matter: the base rate is computed from all assignments,
# so a toy fixture without them makes every theme look statistically ordinary.
ASSIGN = {f"s{i}": {"name": f"Street {i}", "subdivisions": {"Aviary": 1}} for i in range(6)}
ASSIGN["lone"] = {"name": "Lone Street", "subdivisions": {"Tiny": 1}}
ASSIGN.update({f"bg{i}": {"name": f"Background {i}", "subdivisions": {"Elsewhere": 1}}
               for i in range(200)})

MATCHES = {f"s{i}": {"bird"} for i in range(5)}
MATCHES["s5"] = set()
MATCHES["lone"] = {"bird"}
MATCHES.update({f"bg{i}": set() for i in range(200)})


def test_binomial_tail_is_sane():
    assert binom_sf(0, 5, 0.1) == 1.0
    assert binom_sf(6, 5, 0.1) == 0.0
    assert 0 < binom_sf(4, 5, 0.02) < 0.001


def test_theme_detected_from_peers():
    tm = ThemeModel(ASSIGN, MATCHES)
    assert tm.agreement("s0", "bird", "Aviary") > 0.99


def test_leave_one_out_excludes_self():
    """A street\'s own match must not create the theme that then supports it."""
    solo = {"only": {"name": "Only Street", "subdivisions": {"Solo": 1}}}
    tm = ThemeModel(solo, {"only": {"bird"}})
    assert tm.agreement("only", "bird", "Solo") == 0.0


def test_small_subdivision_carries_no_theme():
    tm = ThemeModel(ASSIGN, MATCHES)
    assert tm.agreement("lone", "bird", "Tiny") == 0.0


def test_unmatched_rate_flags_invented_blocks():
    tm = ThemeModel(ASSIGN, MATCHES)
    assert tm.unmatched_rate("s0", ASSIGN) == 1 / 5
