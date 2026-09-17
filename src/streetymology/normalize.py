"""Normalize Ada County street names to a 'core' name for etymology analysis.

Ada County code: predirectionals and post-types are not part of the name proper
and do not count toward the 13-character limit. The core name is therefore both
the correct join key across sources and the correct unit of etymology.
"""
import json
import re

from streetymology.config import data_path

DIRECTIONALS = {
    "n","s","e","w","ne","nw","se","sw",
    "north","south","east","west","northeast","northwest","southeast","southwest",
}

# USPS-style post-types, abbreviated and expanded.
SUFFIXES = {
    "st","street","rd","road","ln","lane","dr","drive","ave","avenue","av",
    "ct","court","pl","place","blvd","boulevard","cir","circle","way","wy",
    "pkwy","parkway","ter","terrace","trl","trail","loop","hwy","highway",
    "bnd","bend","cv","cove","xing","crossing","run","pt","point","pass",
    "sq","square","expy","expressway","aly","alley","row","walk","plz","plaza",
    "mnr","manor","grn","green","gln","glen","vw","view","rdg","ridge",
    "hts","heights","est","estates","cres","crescent","spur","cutoff","connector",
}

# Post-types in order of how much street they usually describe. Roughly a
# quarter of places carry several, and such a place should be named for the
# biggest, not for whichever way sorts first: Ustick is a multi-mile arterial
# with a tiny Court offshoot.
POST_RANK = ("highway", "hwy", "boulevard", "blvd", "parkway", "pkwy",
             "road", "rd", "avenue", "ave", "av", "street", "st",
             "way", "wy", "drive", "dr", "court", "ct", "place", "pl")

_WS = re.compile(r"\s+")
_TOK = re.compile(r"[^a-z0-9]")


def bare(tok: str) -> str:
    """Lowercase a token and drop punctuation (assessor marks names with '*')."""
    return _TOK.sub("", tok.lower())


def normalize(name: str) -> str:
    """Return the core street name: directional and post-type stripped."""
    if not name:
        return ""
    toks = _WS.sub(" ", name.strip()).split(" ")
    # strip leading directional, but never leave nothing behind
    if len(toks) > 1 and bare(toks[0]) in DIRECTIONALS:
        toks = toks[1:]
    # strip trailing post-type, but never leave nothing behind
    if len(toks) > 1 and bare(toks[-1]) in SUFFIXES:
        toks = toks[:-1]
    return " ".join(toks)


def parts(name: str):
    """(directional, core, post-type) with original casing preserved.

    Splitting rather than stripping, so a display name can be recomposed with a
    different post-type than the one this particular way carried.
    """
    if not name:
        return "", "", ""
    toks = _WS.sub(" ", name.strip()).split(" ")
    direction = ""
    if len(toks) > 1 and bare(toks[0]) in DIRECTIONALS:
        direction, toks = toks[0], toks[1:]
    post = ""
    if len(toks) > 1 and bare(toks[-1]) in SUFFIXES:
        post, toks = toks[-1], toks[:-1]
    return direction, " ".join(toks), post


def post_rank_token(post: str) -> int:
    """Rank a bare post-type token. Lower is more important."""
    b = bare(post)
    return POST_RANK.index(b) if b in POST_RANK else len(POST_RANK)


def post_rank(name: str) -> int:
    """Lower is more important. Anything unlisted sorts last, in no order."""
    post = bare(parts(name)[2])
    return POST_RANK.index(post) if post in POST_RANK else len(POST_RANK)


def axis(name: str) -> str:
    """Which grid axis a name's directional puts it on, if any.

    North and East halves of one core are different streets on a grid, and
    grouping them makes places that span both, such as Broadway and Garden City's
    numbered streets. Unprefixed names belong to no axis and may join either.
    """
    d = bare(parts(name)[0])
    if d in ("n", "north", "s", "south"):
        return "NS"
    if d in ("e", "east", "w", "west"):
        return "EW"
    return ""


def _compare(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace. No word removal."""
    t = re.sub(r"\s*&\s*", " and ", text)
    return _WS.sub(" ", re.sub(r"[^a-z0-9 ]", "", t.lower())).strip()


def key(name: str) -> str:
    """Comparison key for a STREET name: directional and post-type removed."""
    return _compare(normalize(name))

# Loading OSM names lives here too: the only thing anyone does with the extract
# is turn it into core keys, which is this module's job.
EXCLUDED_HIGHWAYS = {"trunk"}


def osm_cores() -> dict[str, str]:
    """Map core-name key -> a representative original OSM name."""
    els = json.loads((data_path("osm_named_ways.json")).read_text())["elements"]
    cores: dict[str, str] = {}
    for e in els:
        if e["tags"].get("highway") in EXCLUDED_HIGHWAYS:
            continue
        cores.setdefault(key(e["tags"]["name"]), e["tags"]["name"])
    cores.pop("", None)
    return cores
