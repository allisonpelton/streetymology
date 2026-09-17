"""Recorded plat names, as filed and as a reader should see them.

Names arrive in assessor shorthand: upper case, with `SUB`, `ADD`, `AMD` and a
`NO n` phase marker. Two functions ask different questions of one name.

  - `base_name` gives the naming act. "SUTTERS MILL SUB NO 3" and "NO 4" are
    one act, so streets in both plausibly share an etymology. Everything groups
    on this.
  - `display_name` gives the filing, phase and all, so the map can say when a
    particular street was named.

Where no regex decides, `data/subdivisions.json` holds the judgement and this
module reads it: which names are possessive, which were standardised to one
numbered sequence, which carry a marketing subtitle, and which name no
development at all. This module does string work only. It holds no geometry,
and `plats` imports it rather than the reverse.
"""
import functools
import json
import re

from streetymology import platparse

from .config import SUBDIVISIONS

# "COUNTRY CLUB THE" is the assessor's filing order for "The Country Club".
_TRAILING_THE = re.compile(r"^(.*?),?\s+THE$", re.I)
_WS = re.compile(r"\s+")


def base_name(name):
    """The naming act behind a plat: phase and plat-type words removed.

    "SUTTERS MILL SUB NO 3" and "SUTTERS MILL SUB NO 4" are one act. The block
    and the ordinal stay, because two filings that differ only there are
    different acts: Stein's 1st Addition is not Stein's 2nd.
    """
    p = platparse.parse(name)
    out = p.stem
    if p.ordinal:
        out = (out + " " + p.ordinal).strip()
    if p.block_text:
        out = (out + " " + p.block_text).strip()
    return out


# The assessor zero-pads ordinals and _TRAIL leaves them, so .title() gives
# "02Nd" without this. Display-only: base_name still sees the original, so
# nothing regroups.
ORDINAL = re.compile(r"\b0*(\d+)(st|nd|rd|th)\b", re.I)


# ---------------------------------------------------------------- display ---
# `base_name` collapses a plat to its naming act. These render a plat as
# itself, phase and all, for a reader of the map. The two answer different
# questions: the naming act asserts a likely common etymology, the phase name
# says when specifically a street was named.

_ROMAN = re.compile(r"^(?:I{1,3}|IV|VI{0,3}|IX|XI{0,3})$")
# A base ending in an ordinal: "DUNDEE 03RD", "HIDDEN SPRINGS 06TH".
ORD_BASE = re.compile(r"^(.*\S)\s+0*\d+(?:ST|ND|RD|TH)$", re.I)

# Type words, so "Alscott Rocking A Ranch" and "B Bar B Acres" keep their bare
# letter: a single letter sitting in front of one of these is part of the name,
# not an initial.
_TYPE_WORDS = {"RANCH", "RANCHES", "ACRES", "TOWNHOUSES", "ESTATES", "ESTATE",
               "TRACT", "TRACTS", "HAVEN", "PARK", "PLACE", "ADDITION", "SUB",
               "CONDO", "VILLAS", "MANOR", "GARDENS", "HEIGHTS", "VIEW",
               "VILLAGE", "COURT", "ANNEX", "HOME", "HOMES"}

# Names where the initials rule is wrong and no general rule saves it. Ada
# County only; this list would mean nothing on another dataset.
_NOT_INITIALS = ("TOYS R US", "L AND W", "R AND A LEWIS SURVEY",
                 "CHARLES P O RORKE", "VIGNE D AQUILA")


def _dot_initials(s):
    """A. T. Sorensen, not A T Sorensen. Leading runs and middle runs only."""
    if s.startswith(_NOT_INITIALS):
        return s
    w = s.split()
    i = 0
    while i < len(w) and len(w[i]) == 1 and w[i].isalpha():
        i += 1
    if i >= 2:                      # a lone leading letter is too ambiguous
        w[:i] = [x + "." for x in w[:i]]
    j = 0
    while j < len(w):
        if (len(w[j]) == 1 and w[j].isalpha() and j > 0
                and len(w[j - 1].rstrip(".")) > 1):
            k = j
            while k < len(w) and len(w[k]) == 1 and w[k].isalpha():
                k += 1
            # a trailing letter is not an initial: Circle C, Bobs Point A
            if k < len(w) and w[k].upper() not in _TYPE_WORDS:
                w[j:k] = [x + "." for x in w[j:k]]
                j = k
                continue
        j += 1
    return " ".join(w)


def _titlecase(s):
    m = _TRAILING_THE.match(s)
    if m:
        s = "THE " + m.group(1)
    s = ORDINAL.sub(lambda m: m.group(1) + m.group(2).lower(), s)
    out = [w if (len(w) > 1 and w.isupper() and _ROMAN.match(w)) else
           (w.title() if w.isupper() else w) for w in s.split()]
    s = " ".join(out)
    s = re.sub(r"(?<!^)\b(Of|The|And|At|In|On|To)\b",
               lambda m: m.group(1).lower(), s)
    return re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), s)


def designation(name):
    """The phase levels of a recorded name, outermost first. ["13", "B", "3"]."""
    return list(platparse.parse(name).levels)


@functools.cache
def judgement():
    """`data/subdivisions.json`: the hand judgement, read once per process.

    Absent is a valid state. A forker has no such file, and every section below
    degrades to "no judgement recorded" rather than failing.
    """
    return json.loads(SUBDIVISIONS.read_text()) if SUBDIVISIONS.exists() else {}


@functools.cache
def _judged(section):
    """One section of the judgement file. `_`-prefixed keys hold its reasons."""
    return {k: v for k, v in judgement().get(section, {}).items()
            if not k.startswith("_")}


@functools.cache
def excluded():
    """Plat names that are not developments, upper-cased for matching."""
    return {n.upper() for n in judgement().get("exclude", {}).get("names", ())}






def display_name(name, scattered=False, designated=True):
    """A recorded plat name as a reader should see it.

    `scattered` comes from the contiguity test. Where a name's numbered plats
    sit in one family they are phases of one development and read as "Phase n".
    Where they spread across families the name was reused, so "Randall Acres
    #15" is the fifteenth subdivision called that, not its fifteenth phase.

    Levels join with a dot, so a spaced letter and an attached one render the
    same. The assessor writes both "NO 03 A" and "NO 04A" and means one thing.
    """
    p = platparse.parse(name)
    # A marketing subtitle is filed after the phase number, as in "DE MEYER
    # ESTATES SUB NO 03 THE REDWOODS". It belongs to the phase rather than the
    # development, so it comes off the stem and goes back after the
    # designation. Only the judgement file records which trailing words are one.
    subtitle = _judged("subtitle").get(base_name(name), "")
    if subtitle:
        p = platparse.parse(
            re.sub(r"\s+" + re.escape(subtitle.upper()) + r"\b", " ", name, flags=re.I))
    return _render(p, subtitle, scattered, designated)


def _render(p, subtitle, scattered, designated):
    """A parsed name as a reader should see it.

    The stem is looked up in the judgement file twice, because two different
    kinds of correction apply to it. `number_style` names a sequence AP
    standardised, which always shows its number whatever each filing was
    called. `possessive` fixes an apostrophe the assessor left out.
    """
    stem = p.filed_stem
    canon = _judged("number_style").get(stem)
    poss = _judged("possessive").get(stem)
    tail = _titlecase("ADDITION" + (" TO " + p.city if p.city else "")) if p.addition else ""

    if canon and p.ordinal:
        out = canon + " #" + p.ordinal.lstrip("0")[:-2]
        return _WS.sub(" ", (out + " " + tail).strip())

    head = canon or poss or _titlecase(_dot_initials(stem))
    if p.ordinal and designated:
        ordinal = p.ordinal.lstrip("0").lower()
        # A comma is only correct in front of "Addition". "Dundee, 3rd" on
        # its own reads as a typo.
        out = f"{head}, {ordinal}" if (not poss and tail) else f"{head} {ordinal}"
    else:
        out = head
    if tail:
        out += " " + tail
    if p.tail:
        out += " " + _titlecase(p.tail)

    # A standardised name is a numbered sequence by definition, whatever the
    # contiguity test would have said.
    if canon and not p.ordinal:
        scattered = True
    if p.levels and designated:
        joined = ".".join(p.levels)
        # No comma before "#": "Randall Acres, #15" reads worse without one.
        out += (" #" + joined) if scattered else (", Phase " + joined)
    # "Scott's 4th" dangles. Every possessive ends in its filing type.
    if out.replace("’", "'").count("'") and " Addition" not in out:
        out += " Subdivision"
    if p.block:
        out += " Block " + _WS.sub(" ", p.block).lower()
    if p.area:
        out += " Area " + p.area
    if subtitle:
        out += " — " + _titlecase(subtitle)
    return _WS.sub(" ", out).strip()
