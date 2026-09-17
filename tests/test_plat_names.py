"""`base_name` and `display_name` against the assessor quirks they encode.

These two functions are about 300 lines of regex, and until now the only thing
watching them was the golden test, which sees a change after it has flowed
through measure_streets, build_context and build_batch. A regex edit that broke
one name in 7,435 showed up there as a moved prompt, if at all.

Every case below is a real recorded name from `data/raw/assessor_subdivisions.
json`, grouped by the quirk it exercises. The quirk is the test's name; the
comment above each group is the rule, not a description of the data.

`display_name` reads `judgement` for possessives, standardised
numbering and subtitles, so the cases that depend on hand judgement are kept in
their own class and say which entry they rest on. The rest are pure regex.
"""
import pytest

from streetymology.platnames import base_name, designation, display_name


class TestBaseName:
    """The naming act: phase markers and plat-type words removed."""

    # Phases of one development collapse to one naming act, whichever marker
    # word the assessor used and whether or not the phase carries a letter.
    @pytest.mark.parametrize("recorded,expect", [
        ("SUTTERS MILL SUB NO 01", "SUTTERS MILL"),
        ("SUTTERS MILL SUB NO 05", "SUTTERS MILL"),
        ("HIGHLANDS HACKBERRY NO 01A", "HIGHLANDS HACKBERRY"),
        ("CAMELBACK 02 SUB PHASE 01", "CAMELBACK"),
        ("B BAR B ACRES UNIT NO 01", "B BAR B ACRES"),
        ("LEXINGTON HILLS SUB NO 04", "LEXINGTON HILLS"),
    ])
    def test_phases_share_a_base(self, recorded, expect):
        assert base_name(recorded) == expect

    # A bare UNIT is left behind once SUB and the number come off, and would
    # otherwise read as a development called "A T Sorensen Unit".
    def test_stranded_unit_is_removed(self):
        assert base_name("A T SORENSEN SUB UNIT NO 02") == "A T SORENSEN"
        assert base_name("A T SORENSEN SUB") == "A T SORENSEN"

    # A phase number with no marker word in front of it, only ever zero-padded.
    def test_bare_phase_is_removed(self):
        assert base_name("PARKCENTER POINTE 01A SUB") == "PARKCENTER POINTE"

    # A number that is part of the name is not zero-padded, and stays. This is
    # the only thing separating the two cases, so it is the whole rule.
    @pytest.mark.parametrize("recorded,expect", [
        ("CONCEPT 500 SUB", "CONCEPT 500"),
        ("PINE 43 SUB NO 01", "PINE 43"),
        ("EDSONS SUB LOT 18 AMD", "EDSONS LOT 18"),
        ("CLOVERDALE RIDGE ESTATES NO 02 BLOCK 1",
         "CLOVERDALE RIDGE ESTATES BLOCK 1"),
    ])
    def test_an_unpadded_number_is_part_of_the_name(self, recorded, expect):
        assert base_name(recorded) == expect

    # Stripping "UNIT NO 01 AND 02" leaves a dangling conjunction.
    def test_dangling_conjunction_is_removed(self):
        assert base_name("LANCASTER TERRACE SUB UNIT NO 01 AND 02 AMD") == \
            "LANCASTER TERRACE"

    # An addition to a city: the naming act is the name, not the city.
    def test_addition_to_a_city_drops_the_city(self):
        assert base_name("EAST SIDE ADD TO BOISE") == "EAST SIDE"
        assert base_name("MCCARTYS ADD TO BOISE") == "MCCARTYS"

    # PROJ is Project Amendment. Left in, the amendment lands on a base of its
    # own and reads as a development nobody filed.
    def test_project_amendment_shares_its_parents_base(self):
        assert base_name("AURORA SKY CONDO PROJ AMD NO 01") == \
            base_name("AURORA SKY CONDO") == "AURORA SKY CONDO"

    # The assessor files "The Country Club" as "COUNTRY CLUB THE".
    def test_trailing_the_is_inverted(self):
        assert base_name("CONDO AT HIDDEN SPRINGS THE") == \
            "THE CONDO AT HIDDEN SPRINGS"
        assert base_name("COUNTRY CLUB THE SUB NO 01") == "THE COUNTRY CLUB"

    # An ordinal filing keeps its ordinal: these are separate naming acts that
    # a merge rule joins later, not one act spelled several ways.
    def test_an_ordinal_filing_keeps_its_ordinal(self):
        assert base_name("MCCARTYS 02ND ADD TO BOISE") == "MCCARTYS 02ND"
        assert base_name("HIDDEN SPRINGS SUB 03RD ADD") == "HIDDEN SPRINGS 03RD"

    @pytest.mark.parametrize("empty", ["", None, "   "])
    def test_empty_input_is_not_an_error(self, empty):
        assert base_name(empty) == ""


class TestDesignation:
    """The phase levels of a recorded name, outermost first."""

    @pytest.mark.parametrize("recorded,expect", [
        ("SUTTERS MILL SUB NO 03", ["3"]),
        ("HIGHLANDS HACKBERRY NO 01A", ["1", "A"]),
        ("A T SORENSEN SUB UNIT NO 02", ["2"]),
        ("CAMELBACK 02 SUB PHASE 01", ["1"]),
        ("HIDDEN SPRINGS SUB", []),
    ])
    def test_levels(self, recorded, expect):
        assert designation(recorded) == expect

    # An amendment number is not a phase level: "AMD NO 02" amends the plat, it
    # does not name a phase 2 of it.
    def test_amendment_number_is_not_a_level(self):
        assert designation("DUNDEE 03RD SUB AMD NO 03") == []
        assert designation("LANCASTER TERRACE SUB UNIT NO 02 AMD NO 02") == ["2"]


class TestDisplayName:
    """A recorded name as a reader should see it, phase kept."""

    # A spaced letter and an attached one mean one thing, so they render alike.
    def test_phase_levels_join_with_a_dot(self):
        assert display_name("HIGHLANDS HACKBERRY NO 01A") == \
            "Highlands Hackberry, Phase 1.A"

    # `scattered` says the name was reused rather than phased, so the number
    # identifies which subdivision, not which phase of one.
    def test_scattered_names_number_rather_than_phase(self):
        assert display_name("RANDALL ACRES SUB NO 03") == "Randall Acres, Phase 3"
        assert display_name("RANDALL ACRES SUB NO 03", scattered=True) == \
            "Randall Acres #3"

    # `designated=False` names the development, for a family label.
    def test_undesignated_drops_the_phase(self):
        assert display_name("SUTTERS MILL SUB NO 03", designated=False) == \
            "Sutters Mill"

    # Amendments render as the plat they amend: an amendment is not a filing a
    # reader needs to tell apart on a map.
    def test_amendments_render_as_their_parent(self):
        assert display_name("EAST SIDE ADD TO BOISE AMD") == \
            display_name("EAST SIDE ADD TO BOISE") == "East Side Addition to Boise"

    # ADD is kept and spelled out: "Stein's Addition" and "Stein's" are
    # different filings and the map has to be able to say which.
    def test_addition_is_spelled_out_and_keeps_its_city(self):
        assert display_name("PECKSTEIN ADD TO BOISE") == "Peckstein Addition to Boise"

    # SUB is dropped, because every plat is one.
    def test_subdivision_is_dropped(self):
        assert display_name("LUCY IN THE SKY SUB") == "Lucy in the Sky"

    # Leading and interior single letters are initials; a trailing one, or one
    # in front of a type word, is part of the name.
    @pytest.mark.parametrize("recorded,expect", [
        ("A T SORENSEN SUB", "A. T. Sorensen"),
        ("ALSCOTT ROCKING A RANCH SUB", "Alscott Rocking A Ranch"),
        ("B BAR B ACRES UNIT NO 01", "B Bar B Acres, Phase 1"),
        ("TOYS R US SUB", "Toys R Us"),
    ])
    def test_initials(self, recorded, expect):
        assert display_name(recorded) == expect

    # Interior articles lower-case; a leading one does not.
    def test_article_case(self):
        assert display_name("LUCY IN THE SKY SUB") == "Lucy in the Sky"
        assert display_name("CONDO AT HIDDEN SPRINGS THE") == \
            "The Condo at Hidden Springs"

    # Ordinals are kept numeric: "52nd Street Condo" is a street name, and
    # "Fifty-Second Street" would be wrong.
    def test_ordinals_stay_numeric_and_lose_their_padding(self):
        assert display_name("DUNDEE 03RD SUB") == "Dundee 3rd"

    # Block and Area are filing subdivisions of a phase, and both survive.
    def test_block_and_area(self):
        assert display_name("CLOVERDALE RIDGE ESTATES NO 02 BLOCK 3 AND 4") == \
            "Cloverdale Ridge Estates, Phase 2 Block 3 and 4"

    @pytest.mark.parametrize("empty", ["", None, "   "])
    def test_empty_input_is_not_an_error(self, empty):
        assert display_name(empty) == ""


class TestHandJudgement:
    """Cases that rest on an entry in `judgement`.

    These fail if the entry is removed, which is the point: the entry is the
    only thing carrying the judgement, and a silent removal should not pass.
    """

    # `possessive`: the assessor is inconsistent about the apostrophe and even
    # about the S, so which names are possessive is recorded, not derived.
    def test_possessive(self):
        assert display_name("STEINS ADD") == "Stein's Addition"
        assert display_name("MCCARTYS 02ND ADD TO BOISE") == \
            "McCarty's 2nd Addition to Boise"

    # Every possessive ends in its filing type, or "Stein's 2nd" dangles.
    def test_a_possessive_without_addition_gains_subdivision(self):
        assert display_name("STEINS 02ND SUB") == "Stein's 2nd Subdivision"

    # A name with no possessive entry is title-cased as it stands.
    def test_a_name_not_judged_possessive_keeps_its_s(self):
        assert display_name("EDSONS SUB") == "Edsons"

    # `number_style`: AP standardised these to one numbered sequence, so each
    # filing shows its number however it was recorded.
    def test_standardised_numbering(self):
        assert display_name("BLASER 02ND SUB") == "Blaser #2"
        assert display_name("BLASER SUB NO 03") == "Blaser #3"

    # `subtitle`: a marketing subtitle filed after the phase number belongs to
    # the phase, so it sits after the designation rather than inside the stem.
    def test_subtitle_moves_after_the_designation(self):
        assert display_name("DE MEYER ESTATES SUB NO 03 THE REDWOODS") == \
            "De Meyer Estates, Phase 3 — The Redwoods"

    # The subtitle splits the base name, so a merge entry rejoins the family.
    # base_name is deliberately left alone: it is what the merge keys on.
    def test_subtitle_splits_the_base_which_a_merge_entry_rejoins(self):
        assert base_name("DE MEYER ESTATES SUB NO 03 THE REDWOODS") == \
            "DE MEYER ESTATES THE REDWOODS"
        assert base_name("DE MEYER ESTATES SUB NO 01") == "DE MEYER ESTATES"


class TestOneParseFixesFourNames:
    """Names the two old regex families disagreed about.

    `base_name` stripped markers with one pattern set and `display_name`
    stripped them with another, so a name either family read differently came
    out as a naming act and a label that described different things. One parse
    cannot disagree with itself. These four are every name in the county's
    7,435 where the answer changed.
    """

    # The assessor files "The Bown" as "BOWN THE". Inverting it late left the
    # article stranded in the middle of the rendered label.
    def test_trailing_the_inverts_in_the_label_too(self):
        assert display_name("BOWN THE ADD TO MERIDIAN") == \
            "The Bown Addition to Meridian"

    # "PHASE 01A1" is one marker. Capturing 01 and A left the final digit
    # behind, and it rendered as part of the name.
    def test_a_phase_marker_is_consumed_whole(self):
        assert base_name("RIVER RUN PHASE 01A1") == "RIVER RUN"
        # The stray digit reaches the stem if the marker is not consumed
        # whole, and renders as part of the name.
        assert display_name("RIVER RUN PHASE 01A1") == "River Run, Phase 1.A"
        assert display_name("RIVER RUN PHASE 01A1", designated=False) == "River Run"

    # Two ADDs, and only the one naming a city ends the stem.
    def test_a_bare_addition_does_not_end_the_name(self):
        assert base_name("HYDE PARK ADD LIGHTS ADD") == "HYDE PARK LIGHTS"
        assert display_name("HYDE PARK ADD LIGHTS ADD") == "Hyde Park Lights Addition"

    # An amendment number trails the city and names no phase.
    def test_an_amendment_number_after_the_city_is_dropped(self):
        assert display_name("CRUZEN MOUNTAIN VIEW ADD TO BOISE AMD 03") == \
            "Cruzen Mountain View Addition to Boise"
