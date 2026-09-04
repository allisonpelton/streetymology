import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from streetymology.signals import commonness, notability, nameness, specificity, collision


def test_distinctive_words_score_high():
    assert commonness("Weimaraner") > commonness("Rainbow")
    assert commonness("Borzoi") > commonness("Buffalo")


def test_everyday_word_bottoms_out():
    assert commonness("Star") == 0.0


def test_multiword_scored_by_commonest_token():
    # "Golden Eagle" is only as distinctive as "Golden"
    assert commonness("Golden Eagle") == commonness("Golden")


def test_notability_separates_stub_from_documented():
    assert notability(30) > notability(1)
    assert notability(0, statements=8) == 0.0


def test_personal_names_penalised():
    assert nameness(True, False) < nameness(False, False)
    assert nameness(True, True) == 0.0


def test_longer_spans_more_specific():
    assert specificity("Golden Eagle") > specificity("Eagle")


def test_collision_penalises_multi_domain():
    assert collision(1) == 1.0 and collision(3) < collision(2)
