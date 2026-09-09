"""Normalize Ada County street names to a 'core' name for etymology analysis.

Ada County code: predirectionals and post-types are not part of the name proper
and do not count toward the 13-character limit. The core name is therefore both
the correct join key across sources and the correct unit of etymology.
"""
import re

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

_WS = re.compile(r"\s+")
_TOK = re.compile(r"[^a-z0-9]")


def _bare(tok: str) -> str:
    """Lowercase a token and drop punctuation (assessor marks names with '*')."""
    return _TOK.sub("", tok.lower())


def normalize(name: str) -> str:
    """Return the core street name: directional and post-type stripped."""
    if not name:
        return ""
    toks = _WS.sub(" ", name.strip()).split(" ")
    # strip leading directional, but never leave nothing behind
    if len(toks) > 1 and _bare(toks[0]) in DIRECTIONALS:
        toks = toks[1:]
    # strip trailing post-type, but never leave nothing behind
    if len(toks) > 1 and _bare(toks[-1]) in SUFFIXES:
        toks = toks[:-1]
    return " ".join(toks)


def is_reserved(name: str) -> bool:
    """Assessor marks approved-but-unbuilt street names with a trailing asterisk."""
    return "*" in name


def _compare(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace. No word removal."""
    t = re.sub(r"\s*&\s*", " and ", text)
    return _WS.sub(" ", re.sub(r"[^a-z0-9 ]", "", t.lower())).strip()


def key(name: str) -> str:
    """Comparison key for a STREET name: directional and post-type removed."""
    return _compare(normalize(name))


def entity_key(name: str) -> str:
    """Comparison key for a WIKIDATA entity label.

    Entity labels are proper names, not addresses. Stripping a leading
    directional or a trailing post-type from them destroys the name:
    'North Korea' -> 'korea', 'Blake Run' -> 'blake', 'Charlotte Pass' ->
    'charlotte'. Those produced spurious matches against unrelated streets.
    """
    return _compare(name)


# Loading OSM names lives here too: the only thing anyone does with the
# extract is turn it into core keys, which is this module's job.
import json

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
