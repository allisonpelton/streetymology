"""One structural parse of a recorded plat name.

A name like "DE MEYER ESTATES SUB NO 03 THE REDWOODS" is not free text. It is a
stem, a plat type, a phase designation and a marketing subtitle, written in a
fixed order. `parse` reads that structure once and returns it. `base_name` and
`display_name` are then two views over the same record rather than two separate
attempts to take the name apart.

One parse, because two are not guaranteed to agree. Recognising the phase
markers separately for the naming act and for the label lets a name come out
with a base and a caption that describe different things, and nothing detects
it. Reading the structure once removes the possibility rather than the
symptom.

The patterns themselves are unchanged and live in `platnames`. Only the number
of times they run is different.
"""
import dataclasses
import re

_WS = re.compile(r"\s+")

# Plat-type words, which say what was filed rather than what it is called.
# ADD survives parsing because "Stein's Addition" and "Stein's" are different
# filings and a reader has to be able to tell which.
_SUB_W = re.compile(r"\s*\bSUB(DIVISION)?\b", re.I)
ADD_W = re.compile(r"\bADD(ITION)?\b(\s+TO\s+(?P<city>[A-Z ]+?))?(?=\s|$)", re.I)

# "PROJ" is Project Amendment. "AURORA SKY CONDO PROJ AMD NO 01" amends AURORA
# SKY CONDO, and leaving PROJ in gives the amendment a stem of its own that
# names a development nobody filed.
_PROJ = re.compile(r"\s+PROJ(ECT)?\b", re.I)
AMD_ANY = re.compile(r"\s*\bAM(D|ENDED)\b(\s+NO\s+\d+)?", re.I)

# Phase markers. The assessor writes a phase letter attached and detached,
# "NO 04A" and "NO 03 A", and means one thing by both. The negative lookahead
# stops a single letter swallowing the start of a following word.
# The trailing \d* is consumed but never captured. "PHASE 01A1" is one marker,
# and leaving its last digit behind puts a stray "1" in the rendered label.
_NO_N = re.compile(r"\bNO\s+(\d+)\s*([A-Z])?\d*(?![A-Z])", re.I)
_PHASE_N = re.compile(r"\bPHASE\s+(\d+)\s*([A-Z])?\d*(?![A-Z])|\bPHASE\s+([A-Z])(?![A-Z])", re.I)
_UNIT_N = re.compile(r"\bUNIT\b(\s+(\d+)\s*([A-Z])?\d*(?![A-Z]))?", re.I)

# A phase number with no marker word in front of it, only ever zero-padded.
# That padding is the only thing separating it from a number belonging to the
# name: CONCEPT 500, PINE 43 and EDSONS LOT 18 all keep theirs.
_BARE_PHASE = re.compile(r"\s+0\d*[A-Z]?\d*$", re.I)
# "UNIT NO 01 AND 02" strands a conjunction once the numbers come off.
_STRAND = re.compile(r"\s+(AND|OR)$", re.I)

_AREA_X = re.compile(r"\bAREA\s+(\d+|[A-Z])(?![A-Z])", re.I)
_BLOCK_N = re.compile(r"\bBLOCKS?\s+(\d+(?:\s+AND\s+\d+)?)", re.I)

# An ordinal filing: "MCCARTYS 02ND ADDITION TO BOISE", "DUNDEE 03RD".
_ORDINAL_TAIL = re.compile(r"\s+(0*\d+)(ST|ND|RD|TH)\b(?=\s+ADDITION|\s*$)", re.I)

# "COUNTRY CLUB THE" is the assessor's filing order for "The Country Club".
_TRAILING_THE = re.compile(r"^(.*?),?\s+THE$", re.I)


@dataclasses.dataclass(frozen=True)
class PlatName:
    """What a recorded name says, once its structure is separated out.

    `stem` is the development's name with every marker removed, still in the
    assessor's upper case. `levels` are the phase designation outermost first,
    so "NO 03 A" and "NO 04A" both give a list of two.
    """

    stem: str = ""
    filed_stem: str = ""
    levels: tuple = ()
    addition: bool = False
    city: str = ""
    block: str = ""
    block_text: str = ""
    area: str = ""
    ordinal: str = ""
    tail: str = ""
    amended: bool = False


def _levels(s):
    """The phase designation, outermost first. NO and UNIT are alternatives."""
    out = []
    m, u = _NO_N.search(s), _UNIT_N.search(s)
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
    return tuple(out)


def parse(name):
    """Read a recorded name into its parts. Never raises; "" parses to empty."""
    s = " " + (name or "").upper().strip() + " "
    amended = bool(AMD_ANY.search(s))
    s = AMD_ANY.sub(" ", s)

    levels = _levels(s)
    for pattern in (_NO_N, _PHASE_N, _UNIT_N):
        s = pattern.sub(" ", s)

    area = _AREA_X.search(s)
    block = _BLOCK_N.search(s)
    s = _BLOCK_N.sub(" ", _AREA_X.sub(" ", s))

    # An addition TO a city splits the name: what follows the city is a tail
    # the label keeps and the naming act drops, as in "COTTAGE HOME ADD TO
    # MERIDIAN 02ND (VACATED)". A bare ADD only comes out of the stem, because
    # "HYDE PARK ADD LIGHTS ADD" is Hyde Park Lights and splitting loses it.
    add = ADD_W.search(s)
    city = tail = ""
    if add and add.group("city"):
        city = add.group("city").strip()
        s, tail = s[:add.start()], _WS.sub(" ", s[add.end():]).strip()
        # An amendment number trails the city: "... ADD TO BOISE AMD 03".
        # AMD itself came off above, leaving a bare number nothing renders.
        prev = None
        while tail != prev:
            prev = tail
            tail = _STRAND.sub("", _BARE_PHASE.sub("", " " + tail.strip())).strip()
    elif add:
        s = ADD_W.sub(" ", s)
    s = _PROJ.sub(" ", _SUB_W.sub(" ", s))

    prev = None
    while s != prev:
        prev = s
        s = _STRAND.sub("", _BARE_PHASE.sub("", s.strip()))
    s = _WS.sub(" ", s).strip()

    ordinal = ""
    om = _ORDINAL_TAIL.search(s)
    if om:
        # Kept zero-padded, as filed. The naming act groups on the recorded
        # spelling; only the rendered label drops the padding.
        ordinal = om.group(1) + om.group(2).upper()
        s = _WS.sub(" ", s[:om.start()] + " " + s[om.end():]).strip()

    # base_name needs "THE COUNTRY CLUB"; the label needs the filing order,
    # because _dot_initials letters "G I THE" before _titlecase moves the THE.
    filed = s
    the = _TRAILING_THE.match(s)
    if the:
        s = "THE " + the.group(1)

    return PlatName(stem=s, filed_stem=filed, levels=levels, addition=bool(add), city=city,
                    block=block.group(1).strip() if block else "",
                    block_text=_WS.sub(" ", block.group(0)).strip() if block else "",
                    tail=tail,
                    area=area.group(1).upper() if area else "",
                    ordinal=ordinal, amended=amended)
