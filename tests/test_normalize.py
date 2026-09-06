
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


def test_entity_key_preserves_directionals_and_post_types():
    # Wikidata labels are proper names, not addresses. Stripping words from
    # them produced spurious matches (AP found North Bluff Place -> North Bluff, WI).
    from streetymology.normalize import entity_key
    assert entity_key("North Bluff") == "north bluff"
    assert entity_key("Blake Run") == "blake run"
    assert entity_key("North Korea") == "north korea"
    assert entity_key("Charlotte Pass") == "charlotte pass"


def test_street_key_and_entity_key_differ():
    from streetymology.normalize import entity_key
    assert key("North Bluff Place") == "bluff"
    assert entity_key("North Bluff") != key("North Bluff Place")
