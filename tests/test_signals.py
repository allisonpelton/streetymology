import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from streetymology.signals import commonness, notability, nameness


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




def test_proximity_prefers_local_features():
    from streetymology.signals import proximity, distance_to_ada
    lucky_peak_id = proximity(distance_to_ada((43.52, -116.06)))
    chimney_peak_al = proximity(distance_to_ada((33.5, -86.8)))
    assert lucky_peak_id > 0.9 and chimney_peak_al < 0.05


def test_proximity_returns_none_when_inapplicable():
    # A bird has no coordinates; it must not be penalised for that.
    from streetymology.signals import proximity
    assert proximity(None) is None


def test_idaho_beats_connecticut_for_same_name():
    from streetymology.signals import proximity, distance_to_ada
    assert (proximity(distance_to_ada((45.18, -116.0)))
            > 10 * proximity(distance_to_ada((41.55, -72.45))))


def test_place_plausible_if_near_OR_famous():
    """Nearby-obscure and distant-famous are both valid; combine as max."""
    from streetymology.signals import proximity, distance_to_ada, notability
    cabarton = max(proximity(distance_to_ada((44.4, -116.1))) or 0, notability(0))
    denmark = max(proximity(distance_to_ada((56.0, 10.0))) or 0, notability(369))
    chimney_al = max(proximity(distance_to_ada((33.5, -86.8))) or 0, notability(1))
    assert cabarton > 0.4 and denmark > 0.9
    assert chimney_al < 0.15
