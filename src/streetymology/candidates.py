"""One home for "is this candidate worth offering as an etymology at all?".

Four scripts each carried their own `REJECT` tuple and they drifted:
`build_equal_ground.py` kept only ("wikimedia", "disambiguation"), so equal-ground
round 2 offered "Greiner - family name" and "Greiner - family" as candidates for
East Greiner Street. The model picked one, against an explicit instruction in the
prompt not to. Filtering the option out is more reliable than forbidding it.

A bare personal-name item is never a publishable etymology. "Named for someone
called Greiner" is true of every such street and tells a reader nothing.
"""

# Substring tests against the lowercased Wikidata description.
REJECT_SUBSTRINGS = (
    "family name",
    "given name",
    "male name",
    "female name",
    "surname",
    "wikimedia",
    "disambiguation",
)

# Whole-description tests. "family" alone must not be a substring rule: it would
# throw away "noble family of Tuscany", which can be a real etymology.
REJECT_EXACT = (
    "family",
    "name",
    "personal name",
)


def publishable(description: str | None) -> bool:
    """False if this item could only ever yield "named after someone".

    An empty description is NOT grounds for rejection. Measured against
    equal-ground round 2, that rule dropped the author's own correct answer on
    three items and emptied five candidate lists entirely: many Wikidata species
    items carry no description at all and are identified only by their aliases,
    which is how "Southern Hackberry" is recognisable as sugarberry. Missing
    metadata is a reason to show the aliases, not to hide the candidate.
    """
    d = (description or "").strip().lower()
    if not d:
        return True
    if d in REJECT_EXACT:
        return False
    return not any(r in d for r in REJECT_SUBSTRINGS)


def filter_candidates(cands, describe=lambda c: c.get("description")):
    """Drop unpublishable candidates, preserving order."""
    return [c for c in cands if publishable(describe(c))]
