"""The answer classes, and the order in which to decide between them.

One home. Previously the definitions were written out separately in
`build_equal_ground.py` and `build_equal_ground_adjudication.py`, which is how
`REJECT` drifted into four versions.

Round 2 showed the old wording did not work: 20 of 72 disagreements were NONE
vs NOETYM, and AP declined to rule on any of them. Both classes read as "I am
not choosing a letter", so they competed. They now sit in a fixed order, so
only one question is live at a time.
"""

# The two questions, asked in this order. Asking "is it publishable?" first is
# the whole fix: it settles NOETYM before the candidate list is consulted at all.
DECISION_RULE = """**Decide in this order. The order is what keeps the two
abstentions apart.**

1. **Is there any etymology worth publishing?** A name is *not* publishable if it
   is invented ("Lyngate"), purely descriptive ("Westview", "Big Creek"), or a
   bare surname or given name used as filler. If so, answer **NOETYM** and stop.
   Do not look at the candidates first — a candidate existing is not evidence
   that a developer meant it.
2. **Only if it is publishable: is the referent among the candidates?** Answer
   with that **letter** if it is, **NONE** if it is not."""

NONE_LINE = ("**NONE.** This name has a real etymology, but it is not among the "
             "candidates above.")
NOETYM_LINE = ("**NOETYM.** No etymology worth publishing: invented, purely "
               "descriptive, or a bare personal name.")

# What each abstention means once the data is in hand. NONE acquires a use it
# did not have before: it counts pipeline misses, not street properties.
INTERPRETATION = """**NONE** is a complaint about the pipeline, not about the
street: it means an answer exists and was not surfaced. **NOETYM** is a
judgement about the street itself and is independent of what was offered."""


def options_block(indent="    - "):
    """The two abstention choices, as shown under every item's candidate list."""
    return [f"{indent}{NONE_LINE}", f"{indent}{NOETYM_LINE}"]


def guide():
    """The block explaining the classes at the top of a labelling document."""
    return f"""{DECISION_RULE}

{INTERPRETATION}

**NONE and NOETYM are both expected to be common answers.** Most American
suburban street names have no etymology at all; a developer picked a word
because it sounded pleasant. Wikidata contains something for almost any string."""
