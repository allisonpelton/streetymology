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
and `geo` imports it rather than the reverse.
"""
import functools
import json
import re

from .config import SUBDIVISIONS

# Assessor shorthand. SUB=subdivision, ADD=addition, AMD=amended plat.
# UNIT appears both as "UNIT NO 02" and bare, because the assessor writes
# "A T SORENSEN SUB UNIT NO 02": SUB and NO 02 came off and UNIT was left behind,
# so the naming act read as "A T Sorensen Unit". Both forms go.
# Phase numbers carry a letter suffix often enough to matter: "SUB NO 04A",
# "PHASE 01A1", "UNIT NO 02A". `\d+` followed by `\b` cannot match those --
# there is no boundary between "4" and "A", so the marker survives and every
# lettered phase reads as its own naming act. "PHASE A" has no digits at all.
# The assessor writes a phase letter both ways, "NO 04A" and "NO 03 A", so each
# marker accepts an adjacent suffix or a standalone letter token. The `\b` on
# the standalone branch is what stops it eating the S of a following SUB: in
# "NO 01 SUB" there is no boundary between S and U, so the branch fails and
# only "NO 01" comes off. AREA is the same kind of marker: "06TH ADD AREA C".
_TRAIL = re.compile(r"\s+(SUB(DIVISION)?|ADD(ITION)?|AMD|AMENDED|"
                    r"NO\s+\d+(?:\s+[A-Z]\b|[A-Z]?\d*)|"
                    r"#\s*\d+(?:\s+[A-Z]\b|[A-Z]?\d*)|"
                    r"PHASE\s+(?:\d+(?:\s+[A-Z]\b|[A-Z]?\d*)|[A-Z]\b)|"
                    r"AREA\s+(?:\d+(?:\s+[A-Z]\b|[A-Z]?\d*)|[A-Z]\b)|"
                    r"UNIT(\s+\d+(?:\s+[A-Z]\b|[A-Z]?\d*))?)\b", re.I)
# A trailing phase with no marker word in front of it: "PARKCENTER POINTE 01A",
# "CAMELBACK 02". Only zero-padded, which is how the assessor writes phases and
# is what separates them from a number that belongs to the name. CONCEPT 500,
# PINE 43, EDSONS LOT 18 and CLOVERDALE RIDGE ESTATES BLOCK 1 all keep theirs.
_BARE_PHASE = re.compile(r"\s+0\d*[A-Z]?\d*$", re.I)
# "LANCASTER TERRACE SUB UNIT NO 01 AND 02 AMD" strips down to a dangling AND.
_STRAND = re.compile(r"\s+(AND|OR)$", re.I)
# "PROJ" is Project Amendment: "AURORA SKY CONDO PROJ AMD NO 01" amends AURORA
# SKY CONDO. Without stripping it the amendment lands on a base of its own and
# reads as a development nobody ever filed.
_PROJ = re.compile(r"\s+PROJ(ECT)?\b", re.I)
# "EAST SIDE ADD TO BOISE" is an addition to a city: the naming act is "East
# Side", and the city is not part of it.
_ADD_TO = re.compile(r"\s+ADD(ITION)?(\s+NO\s+\d+)?\s+TO\s+.*$", re.I)
# "COUNTRY CLUB THE" is the assessor's filing order for "The Country Club".
_TRAILING_THE = re.compile(r"^(.*?),?\s+THE$", re.I)
_WS = re.compile(r"\s+")


def base_name(name: str) -> str:
    """The naming act behind a plat: phase and plat-type words removed.

    'SUTTERS MILL SUB NO 3' and 'SUTTERS MILL SUB NO 4' are one theme.
    """
    prev = None
    out = _PROJ.sub("", _ADD_TO.sub("", (name or "").strip()))
    while out != prev:
        prev = out
        out = _TRAIL.sub("", out).strip()
        out = _BARE_PHASE.sub("", out).strip()
        out = _STRAND.sub("", out).strip()
    m = _TRAILING_THE.match(out)
    if m:
        out = f"THE {m.group(1)}"
    return _WS.sub(" ", out)


# The assessor zero-pads ordinals and _TRAIL leaves them, so .title() gives
# "02Nd" without this. Display-only: base_name still sees the original, so
# nothing regroups.
ORDINAL = re.compile(r"\b0*(\d+)(st|nd|rd|th)\b", re.I)


# ---------------------------------------------------------------- display ---
# `base_name` collapses a plat to its naming act. These render a plat as
# itself, phase and all, for a reader of the map. The two answer different
# questions: the naming act asserts a likely common etymology, the phase name
# says when specifically a street was named.

AMD_ANY = re.compile(r"\s*\bAM(D|ENDED)\b(\s+NO\s+\d+)?", re.I)
_SUB_W = re.compile(r"\s*\bSUB(DIVISION)?\b", re.I)
# ADD is kept and spelled out, because "Stein's Addition" and "Stein's" are
# different filings and the map has to be able to say which.
ADD_W = re.compile(r"\bADD(ITION)?\b(\s+TO\s+(?P<city>[A-Z ]+?))?(?=\s|$)", re.I)
_NO_N = re.compile(r"\bNO\s+(\d+)\s*([A-Z])?(?![A-Z])", re.I)
_PHASE_N = re.compile(r"\bPHASE\s+(\d+)\s*([A-Z])?(?![A-Z])|\bPHASE\s+([A-Z])(?![A-Z])", re.I)
_UNIT_N = re.compile(r"\bUNIT\b(\s+(\d+)\s*([A-Z])?(?![A-Z]))?", re.I)
_AREA_X = re.compile(r"\bAREA\s+(\d+|[A-Z])(?![A-Z])", re.I)
_BLOCK_N = re.compile(r"\bBLOCKS?\s+(\d+(?:\s+AND\s+\d+)?)", re.I)
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
    """The phase levels of a recorded name, outermost first. ["13","B","3"]."""
    s = AMD_ANY.sub(" ", " " + (name or "").upper().strip() + " ")
    out = []
    m = _NO_N.search(s)
    u = _UNIT_N.search(s)
    if m:
        out.append(m.group(1).lstrip("0") or "0")
        if m.group(2):
            out.append(m.group(2).upper())
    elif u and u.group(2):
        out.append(u.group(2).lstrip("0") or "0")
        if u.group(3):
            out.append(u.group(3).upper())
    p = _PHASE_N.search(s)
    if p:
        if p.group(3):
            out.append(p.group(3).upper())
        else:
            out.append(p.group(1).lstrip("0") or "0")
            if p.group(2):
                out.append(p.group(2).upper())
    return out


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




# An ordinal sitting in the stem: "MCCARTYS 02ND ADDITION TO BOISE".
_ORD_IN = re.compile(r"\s+0*(\d+)(ST|ND|RD|TH)\b(?=\s+ADDITION|\s*$)", re.I)


def display_name(name, scattered=False, designated=True):
    """A recorded plat name as a reader should see it.

    `scattered` comes from the contiguity test: where a name's numbered plats
    sit in one family they are phases of one development and read as "Phase n";
    where they are spread across families the name was simply reused, and
    "Randall Acres #15" is the fifteenth subdivision called that, not its
    fifteenth phase.

    Levels join with a dot, so a spaced letter and an attached one render the
    same. The assessor writes both "NO 03 A" and "NO 04A" and means one thing.
    """
    s = " " + (name or "").upper().strip() + " "
    s = AMD_ANY.sub(" ", s)
    # A marketing subtitle is filed after the phase number: "DE MEYER ESTATES
    # SUB NO 03 THE REDWOODS". It belongs to the phase, not the development, so
    # it comes out here and goes back on after the designation.
    subtitle = _judged("subtitle").get(base_name(name), "")
    if subtitle:
        s = re.sub(r"\s+" + re.escape(subtitle.upper()) + r"\b", " ", s, flags=re.I)
    levels = designation(name)
    s = _NO_N.sub(" ", s)
    s = _PHASE_N.sub(" ", s)
    s = _UNIT_N.sub(" ", s)
    area = _AREA_X.search(s)
    block = _BLOCK_N.search(s)
    s = _AREA_X.sub(" ", s)
    s = _BLOCK_N.sub(" ", s)
    s = ADD_W.sub(lambda m: " ADDITION" + (" TO " + m.group("city").strip()
                                            if m.group("city") else "") + " ", s)
    s = _SUB_W.sub(" ", s)
    s = _PROJ.sub(" ", s)
    prev = None
    while s != prev:                 # "UNIT NO 01 AND 02" strands an "AND 02"
        prev = s
        s = _BARE_PHASE.sub("", s.strip())
        s = _STRAND.sub("", s.strip())
    s = _WS.sub(" ", s).strip()
    # An ordinal filing is usually a family platting its own land, so it reads
    # as a possessive, "McCarty's 1st Addition to Boise". The assessor is not
    # consistent about the apostrophe, or even the S, so the judgement lives in
    # subdivisions.json. A name that is not a person takes a comma instead:
    # "South Boise, 2nd Addition".
    om = _ORD_IN.search(s)
    if om:
        ordinal = om.group(1) + om.group(2).lower()
        rest = _WS.sub(" ", (s[:om.start()] + " " + s[om.end():])).strip()
        stem, sep, city = rest.partition(" ADDITION")
        stem = stem.strip()
        tail = _titlecase("ADDITION" + city) if sep else ""
        poss = _judged("possessive").get(stem)
        head = poss or _titlecase(_dot_initials(stem))
        # A name AP has standardised to one numbered sequence reads its
        # ordinals as numbers: Blaser #1, #2, #3, however each was filed.
        canon = _judged("number_style").get(stem)
        if canon:
            # A standardised sequence always shows its number: AP asked for
            # Blaser #1 through #9 whatever each filing was called.
            out = canon + " #" + om.group(1).lstrip("0")
            if sep:
                out += " " + tail
            return _WS.sub(" ", out).strip()
        # A comma only earns its place in front of "Addition"; "Dundee, 3rd"
        # on its own reads as a typo.
        if not designated:
            out = head
        else:
            out = f"{head}, {ordinal}" if (not poss and tail) else f"{head} {ordinal}"
        if tail:
            out += " " + tail
    else:
        canon = _judged("number_style").get(s)
        stem_only, sep2, city2 = s.partition(" ADDITION")
        out = (canon or _judged("possessive").get(stem_only.strip())
               or _titlecase(_dot_initials(s)))
        if not canon and _judged("possessive").get(stem_only.strip()) and sep2:
            out += " " + _titlecase("ADDITION" + city2)
        # A standardised name is a numbered sequence by definition, whatever
        # the contiguity test would have said.
        scattered = scattered or bool(canon)
    if levels and designated:
        joined = ".".join(levels)
        # No comma before "#": "Randall Acres, #15" reads worse than without.
        out += (" #" + joined) if scattered else (", Phase " + joined)
    # "Scott's 4th" dangles. Every possessive ends in its filing type.
    if out.replace("\u2019", "'").count("'") and " Addition" not in out:
        out += " Subdivision"
    if block:
        out += " Block " + _WS.sub(" ", block.group(1).strip()).lower().replace(" and ", " and ")
    if area:
        out += " Area " + area.group(1).upper()
    if subtitle:
        out += " \u2014 " + _titlecase(subtitle)
    return _WS.sub(" ", out).strip()
