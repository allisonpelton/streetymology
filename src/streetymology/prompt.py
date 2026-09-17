"""The prompt: one wording, one context layout, one candidate filter.

Both the 240-item chat prompt and the paid batch run render items from here. When
they each had their own copy, the batch builder drifted onto retired modules and
stopped running at all, and the chat prompt offered candidates the filter was
written to remove.

Nothing in this module reads the network or writes a file.
"""
import json

from streetymology import config, normalize

HEADER = """# Street etymology — 240 items

For each street, choose the Wikidata item it is named after, or say that none
applies. Candidate order is randomised and carries no meaning.

## Essential background

Most American suburban street names have **no etymology at all** — a developer
picked a word because it sounded pleasant. Wikidata contains something for almost
any string. A candidate existing is not evidence the street refers to it.
**The three non-candidate answers are expected to be common.**

Subdivisions are usually themed, so the names of streets *named by the same
subdivision* are the strongest evidence available. Themes can be mixed, and many
subdivisions have no theme at all.

Where several candidates are the same kind of thing, prefer the **least specific**
one that fits: "Prickly Pear" means the genus *Opuntia*, not a Galapagos species.

## How to read the context

Each item names the subdivision that platted the street, then three tiers of
neighbouring street names, strongest evidence first:

- **Named by that subdivision** — platted by the same act. One theme, if there
  is one, lives here.
- **In that subdivision, named by a different one** — the plats overlap, but a
  different developer chose the name. Related, weaker.
- **Nearby, outside it** — adjacent or unplatted ground. Weakest; proximity
  alone is not evidence of a shared theme. Rarely, one of these streets could 
  be the etymology.

Two numbers are given, both 0 to 1:

- **Confidence this subdivision laid the street out.** Below about 0.9, treat the subdivision and its street names as uncertain.
- **Confidence its name follows that subdivision's theme.** This is the
  confidence above, reduced by the plat's age. Older subdivisions seldom have themes beyond trees
  and presidents. This number doesn't imply the subdivision has a theme or 
  that every listed street is part of the theme. If this value is low, themes
  are likely coincidental.

## Answers

- A single **candidate letter**.
- **NONE** — a real etymology probably exists, but no candidate above is it.
- **INVENTED** — no referent exists. A developer coined the name.
- **PERSONAL** — named for a person or a family. A real referent exists, but
  Wikidata does not carry it.

## Output format
Return a markdown table, one row per item, nothing else:
| n | street | choice | confidence | theme | reasoning |
- choice: a candidate letter, NONE, INVENTED, or PERSONAL
- confidence: high / medium / low
- theme: the subdivision theme you infer, or none, or unclear
- reasoning: one sentence, max ~20 words

---

## Items (240)
"""

LETTERS = "ABCDEFGHIJ"

OPTIONS = [
    "    - **NONE.** A real etymology probably exists, but no candidate above is it.",
    "    - **INVENTED.** No referent exists. A developer coined the name.",
    "    - **PERSONAL.** Named for a person or a family. A real referent exists,"
    " but Wikidata does not carry it.",
]


def pick(street, by_core):
    places = by_core.get(normalize.key(street))
    if not places:
        return None
    if len(places) == 1:
        return places[0][1]
    exact = [r for _, r in places if r.get("name") == street]
    pool = exact or [r for _, r in places]
    return max(pool, key=lambda r: len(r.get("peers", ())))


def tiers(rec, ctx, by_core):
    """The three tiers, deduped so a street appears once at its strongest."""
    def nm(pid):
        r = ctx.get(pid)
        return r["display"] if r else None

    peers = [nm(p) for p in rec.get("peers", ()) if nm(p)]
    same = [nm(p) for p in rec.get("same_plat", ()) if nm(p)]
    near = sorted({nm(p) for b in ("attached", "near_unplatted")
                   for p in rec.get(b, ()) if nm(p)})

    mine = rec.get("display")
    seen = {mine}
    def dedupe(seq):
        out = []
        for x in seq:
            if x and x not in seen:
                seen.add(x)
                out.append(x)
        return out

    return dedupe(sorted(set(peers))), dedupe(same), dedupe(near)


def render(n, street, cand_lines, rec, ctx, by_core):
    L = [f"### {n}. {street}"]
    if rec is None:
        L.append("- **Subdivision:** unknown — this street is not in the plat data")
        L += ["- **Candidates:**"] + cand_lines + OPTIONS
        return "\n".join(L)
    plat = rec.get("naming_plat")
    if plat:
        yr = (rec.get("naming_recorded") or "")[:4]
        L.append(f"- **Subdivision:** {plat}" + (f", platted {yr}" if yr else ""))
        L.append("- **Confidence this subdivision laid the street out:** "
                 f"{rec['confidence']:.2f}")
        L.append("- **Confidence its name follows that subdivision's theme:** "
                 f"{rec['theme_confidence']:.2f}")
    else:
        L.append("- **Subdivision:** none — no subdivision appears to have named "
                 "this street")
        L.append("- **Confidence its name follows a subdivision theme:** low")
    a, b, c = tiers(rec, ctx, by_core)
    # With no subdivision there is no "that subdivision", so the two tiers that
    # refer to one are left out rather than printed empty.
    if plat:
        L.append("- **Named by that subdivision:** " + (", ".join(a) or "(none)"))
        L.append("- **In that subdivision, named by a different one:** "
                 + (", ".join(b) or "(none)"))
    L.append("- **Nearby, outside it:** " + (", ".join(c) or "(none)"))
    L += ["- **Candidates:**"] + cand_lines + OPTIONS
    return "\n".join(L)


def load_context():
    """place_context.json, plus a core -> places index for name lookup."""
    ctx = json.loads(config.data_path("place_context.json").read_text())
    by_core = {}
    for pid, rec in ctx.items():
        by_core.setdefault(pid.split("#")[0], []).append((pid, rec))
    return ctx, by_core


def lettered(cands):
    """(letter, candidate) pairs. The only place a letter is assigned.

    `answers` inverts this, so the order here is what a paid answer means.
    """
    return list(zip(LETTERS, cands[:len(LETTERS)]))


def candidate_lines(cands):
    """Render Wikidata hits as lettered options. Input is already filtered."""
    return [f"    - **{letter}.** {c['label']} \u2014 "
            f"{c.get('description') or '(no description)'}"
            for letter, c in lettered(cands)]
