"""Hand judgement about Ada County subdivisions, where no rule reaches.

Two rules group plats into naming acts without anything here. An ordinal
filing merges with its stem, so Scott's 1st through 5th are one act. A base
that is another base plus a trailing NORTH, SOUTH, EAST or WEST merges with
it. The family distance still applies across any merge, so a listed base far
from the rest still separates. That is how Seamans 02nd stays out of Seaman's
without anyone saying so twice.

Everything below is what those rules cannot reach. It was decided by AP case by
case, and each entry records why. It cannot be regenerated.

This is the most Ada County specific file in the repo. A forker deletes it and
starts an empty one.
"""

# Bases that are one naming act, with the label the family takes. The two rules
# above already cover Scott's 1st-5th and Randall 1st-3rd, so neither is here.
MERGES = (
    # one development whose blocks were recorded separately
    ('Cloverdale Ridge Estates', (
        'CLOVERDALE RIDGE ESTATES',
        'CLOVERDALE RIDGE ESTATES BLOCK 1',
        'CLOVERDALE RIDGE ESTATES BLOCK 2',
        'CLOVERDALE RIDGE ESTATES BLOCK 3 AND 4',
    )),
    # same pattern as Cloverdale Ridge; no bare parent plat exists
    ('Heather Haven Estates', (
        'HEATHER HAVEN ESTATES BLOCK 3',
        'HEATHER HAVEN ESTATES BLOCKS 1 AND 2',
    )),
    # II is a phase, recorded seven months after the parent
    ('The Colony', (
        'THE COLONY',
        'COLONY II',
    )),
    # F B Smith Senior Estate (1923) is effectively the first; the estate
    # then filed 2nd through 5th
    ('F. B. Smith Estate', (
        'F B SMITH SENIOR ESTATE',
        'SMITH ESTATE 02ND',
        'SMITH ESTATE 03RD',
        'SMITH ESTATE 04TH',
        'SMITH ESTATE 05TH',
    )),
    # same name singular and plural. The 02nd is 5.6 km away and the
    # distance split keeps it separate, which is intended
    ("Seaman's Subdivision", (
        'SEAMAN',
        'SEAMANS 02ND',
        'SEAMANS 03RD',
    )),
    # singular and plural of one name. AP chose the plural, which appears
    # only in the amended plat
    ('Capitol Sites', (
        'CAPITOL SITE',
        'CAPITOL SITES',
    )),
    # same name, possessive
    ("Willson's Addition to Boise", (
        'WILLSON',
        'WILLSONS',
    )),
    # a spacing change between 1992 and 1994. AP: the sign says
    # Riverwoods, so the newer spelling won
    ('Leaders Riverwoods', (
        'LEADERS RIVER WOODS',
        'LEADERS RIVERWOODS',
    )),
    # One-A is a resubdivision of the common areas and parking, not a
    # separate development
    ('Kimberley One Townhouses', (
        'KIMBERLEY ONE TOWNHOUSES',
        'KIMBERLEY ONE A TOWNHOUSES',
    )),
    # one development, all seven at 0 m. The streets carry an actor theme
    # throughout
    ('Paramount', (
        'PARAMOUNT',
        'PARAMOUNT CHURCH',
        'PARAMOUNT DIRECTOR',
        'PARAMOUNT POINT',
        'PARAMOUNT SQUARE',
        'PARAMOUNT VERANDA',
        'PARAMOUNT VILLAGE CENTER',
    )),
    # No 3 and No 4 were filed as 'De Meyer Estates Sub No 03 The
    # Redwoods'. The subtitle sits after the phase number, so stripping
    # the number left it glued to the stem and split the family in two
    ('De Meyer Estates', (
        'DE MEYER ESTATES',
        'DE MEYER ESTATES THE REDWOODS',
    )),
    # same shape: 'Lakeharbor No 06 Village at Silver Lake' is phase 6
    # with a subtitle
    ('Lakeharbor', (
        'LAKEHARBOR',
        'LAKEHARBOR VILLAGE AT SILVER LAKE',
    )),
)


# The assessor is inconsistent about the apostrophe and sometimes drops the S
# entirely: BLASERS 01ST then BLASER 02ND, eleven months apart. So which names
# are possessive is recorded, not derived. 62% of pre-1950 ordinal filings
# carry a possessive surname against 5% of NO and UNIT filings, which is not a
# high enough rate to guess from. None means the comma form instead, as in
# "South Boise, 2nd Addition".
POSSESSIVE = {
    'AFTONS': "Afton's",
    'AIKENS': "Aiken's",
    'ASSELINS': "Asselin's",
    'BALDERSTONS': "Balderston's",
    'BELL': None,
    'BLASER': None,
    'BLASERS': None,
    'BOWERS': "Bower's",
    'BOWNS': "Bown's",
    'BROSE': None,
    'CARPENTERS': "Carpenter's",
    'DUNDEE': None,
    'ELMER DAVIS': None,
    'EMILIE GANZ': None,
    'F A NOURSES': "F. A. Nourse's",
    'FAIRMONT': None,
    'GEORGIANNA MILKS': "Georgianna Milk's",
    'GINZELS': "Ginzel's",
    'HIDDEN SPRINGS': None,
    'HILLSIDE': None,
    'HOWARDS': "Howard's",
    'HUMPHREYS': None,
    'J M ANDERSONS': "J. M. Anderson's",
    'JOHN KRALLS': "John Krall's",
    'JOHN MCMILLANS': "John McMillan's",
    'JOHNSTONS': "Johnston's",
    'KEPNER PLACE': None,
    'LAMPERTS': "Lampert's",
    'LEONARDS': "Leonard's",
    'LONDONER': None,
    'MARKO': None,
    'MCCARTYS': "McCarty's",
    'MCINTYRES': "McIntyre's",
    'MIKE MILLER': None,
    'MORTONS': "Morton's",
    'MRS A M WILSON': "Mrs. A. M. Wilson's",
    'NIDAYS': "Niday's",
    'ORA DELL': None,
    'RANDALL': None,
    'ROSEDALE GALLAHERS': "Rosedale Gallaher's",
    'SAXTONS': "Saxton's",
    'SCOTTS': "Scott's",
    'SEAMANS': "Seaman's",
    'SETYS': "Sety's",
    'SEWELLS': "Sewell's",
    'SMITH ESTATE': None,
    'SOUTH BOISE': None,
    'STEINS': "Stein's",
    'STONES': "Stone's",
    'STRAWBERRY GLENN': None,
    'THOMAS DAVIS': None,
    'THOMPSONS': "Thompson's",
    'VAILS': "Vail's",
    'VAUGHANS': "Vaughan's",
    'WAYLANDS': "Wayland's",
    'WILLSON': "Willson's",
    'WILLSONS': "Willson's",
}


# Names whose filings read as one numbered sequence however the assessor wrote
# each. Blaser ran 1st, 2nd, then NO 03 to NO 09 across four locations, losing
# the possessive partway. AP: standardise to Blaser #1, #2 and so on. Labelling
# only; the geographic split into four subdivisions stands.
NUMBER_STYLE = {
    'BLASER': 'Blaser',
    'BLASERS': 'Blaser',
}


# A marketing subtitle filed after the phase number, moved so it sits after the
# designation rather than inside the development's name. Keyed by base name. No
# regex finds these: "DE MEYER ESTATES SUB NO 03 THE REDWOODS" is a subtitle and
# "WOODS NO 02 AT RIVERSIDE THE SUB" is a name the designation interrupts, and
# the two are the same shape.
SUBTITLE = {
    'DE MEYER ESTATES THE REDWOODS': 'The Redwoods',
    'LAKEHARBOR VILLAGE AT SILVER LAKE': 'Village at Silver Lake',
}


# Plats that are not a development of their own. AP 2026-09-12: HYDE PARK ADD
# LIGHTS ADD modifies part of the two additions it names rather than adding
# anything, and OpenStreetMap is removing it for the same reason.
EXCLUDE = ('HYDE PARK ADD LIGHTS ADD',)

# Directional variants that are NOT one naming act, against the rule above.
# Both were judged apart on theme: Harris Ranch has 26 sawmill names against 6
# birds, and merging through the Shelburne parent would make two unrelated
# developments peers.
DIRECTIONAL_SKIP = ('HARRIS RANCH', 'SHELBURNE')
