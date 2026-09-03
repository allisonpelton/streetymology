import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from streetymology.match import match, is_ambiguous, Candidate

IDX = {
    "bird": {"meadowlark": [{"qid": "Q1431050", "name": "Meadowlark", "via": "full"}]},
    "us_president": {"lincoln": [{"qid": "Q91", "name": "Abraham Lincoln", "via": "surname"}]},
    "plant": {"meadowlark": [{"qid": "Q999", "name": "Meadowlark", "via": "full"}]},
}


def test_full_match_beats_surname():
    c = match("South Lincoln Avenue", IDX)
    assert c and c[0].via == "surname" and c[0].qid == "Q91"


def test_surname_can_be_disabled():
    assert match("South Lincoln Avenue", IDX, allow_surname=False) == []


def test_ambiguity_across_domains():
    c = match("West Meadowlark Lane", IDX)
    assert is_ambiguous(c)


def test_unmatched_name_returns_empty():
    assert match("West Nonesuch Street", IDX) == []
