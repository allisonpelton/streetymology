"""Drop candidates that could never be a publishable etymology.

Search returns whatever matches the string, so "Ulmer" comes back with the
Wikidata item for the surname. "Named for someone called Ulmer" is true of every
such street and tells a reader nothing.

The test is the item's P31 claims, not its description. Descriptions are free
text in any language and anyone can edit them: the description rule this replaced
missed "male name" because it listed "given name" and "family name". Claims are a
closed set, and on the streets checked they reproduced the description rule
exactly, 17 of 17, with nothing new dropped.

Filtering is separate from fetching on purpose. Fetching is the expensive,
irreversible half; deciding what to exclude has already changed once and will
change again.

  python -m streetymology.filter_candidates
"""
import argparse
import csv
import functools
import io
import json
import time

from streetymology import config

# P31 values that make an item a bare personal name or Wikimedia plumbing.
# Add to this rather than writing string rules.
EXCLUDE_TYPES = {
    "Q101352": "family name",
    "Q202444": "given name",
    "Q12308941": "male given name",
    "Q11879590": "female given name",
    "Q3409032": "unisex given name",
    "Q1243157": "compound given name",
    "Q66480858": "composite given name",
    "Q60558422": "patronymic family name",
    "Q4167410": "Wikimedia disambiguation page",
    "Q4167836": "Wikimedia category",
    "Q13406463": "Wikimedia list article",
    "Q17362920": "Wikimedia duplicated page",
    # Subtypes of name. Wikidata often gives a bare surname a second, more
    # specific class, and requiring EVERY class to be excludable then kept the
    # item: Bonnie is {hypocorism, unisex given name} and survived. These are
    # every non-excluded class found riding alongside a name class across the
    # whole candidate set, and none of them is a referent.
    "Q82799": "name",
    "Q829026": "occupational surname",
    "Q56219051": "surname prefixed with Mac or Mc",
    "Q98775491": "family name based on given name",
    "Q1130279": "hypocorism",
    "Q11455398": "patronymic family name",
    "Q333021": "Uebername",
    "Q17143070": "toponymic surname",
    "Q1714800": "locational surname",
    "Q19914123": "Japanese family name",
    "Q1093580": "Chinese family name",
    "Q18972207": "feminine family name",
    "Q108709": "diminutive",
    "Q8436": "family",
}
BATCH = 400          # QIDs per SPARQL query; well inside the 60s budget

# Fallback only, for the 45 items Wikidata gives no P31 at all.
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


def _publishable(description: str | None) -> bool:
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

ENDPOINT = "https://query.wikidata.org/sparql"


@functools.cache
def _s():
    """One pooled config.session, built on first use rather than at import."""
    return config.session()


def query(sparql: str, timeout: int = 300) -> list[dict]:
    """Run a SPARQL query, returning its CSV rows as dicts."""
    r = _s().post(ENDPOINT, data={"query": sparql},
                headers={"Accept": "text/csv"}, timeout=timeout)
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.text)))


def claims_for(qids):
    """QID -> set of P31 values, fetched in batches."""
    out = {}
    qids = sorted(set(qids))
    for i in range(0, len(qids), BATCH):
        chunk = qids[i:i + BATCH]
        values = " ".join(f"wd:{q}" for q in chunk)
        rows = query(f"SELECT ?item ?type WHERE {{ VALUES ?item {{ {values} }}"
                     f" OPTIONAL {{ ?item wdt:P31 ?type. }} }}")
        for q in chunk:
            out.setdefault(q, set())
        for r in rows:
            q = r["item"].rsplit("/", 1)[-1]
            t = r.get("type", "").rsplit("/", 1)[-1]
            if t:
                out[q].add(t)
        print(f"  claims {min(i + BATCH, len(qids))}/{len(qids)}")
        time.sleep(1)
    return out


def excluded(types, description=None):
    """True if this item could never be a publishable etymology.

    Every P31 must be excludable, not merely one of them. Brahmani is both a
    given name and one of the seven Mother Goddesses in Hinduism; an any-match
    rule threw her away, along with a real estate company that shares its name
    with a person.

    Where Wikidata records no P31 at all, fall back to the description. That is
    the weaker signal, but 45 items are bare names carrying no claim to test, and
    the alternative is offering "Austin - name" as an etymology.

    An item with neither P31 nor description is KEPT: many species items carry no
    metadata and are identified only by their aliases, and dropping those cost
    three correct answers when it was measured against round 2.
    """
    if types:
        return types <= EXCLUDE_TYPES.keys()
    return not _publishable(description)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src", default="search_unmatched.json")
    ap.add_argument("--out", default="candidates.json")
    a = ap.parse_args()

    search = json.loads(config.data_path(a.src).read_text())
    claims = claims_for([h["qid"] for hits in search.values() for h in hits])

    out, dropped = {}, 0
    for core, hits in search.items():
        keep = [h for h in hits
                if not excluded(claims.get(h["qid"], set()), h.get("description"))]
        dropped += len(hits) - len(keep)
        if keep:
            out[core] = keep
    config.write_json(config.data_path(a.out), out, indent=1)

    total = sum(len(h) for h in search.values())
    print(f"cores {len(search)} -> {len(out)} with a candidate left")
    print(f"candidates {total} -> {total - dropped}, dropped {dropped}"
          f" ({dropped / total:.1%})")
    print(f"wrote {config.data_path(a.out)}")


if __name__ == "__main__":
    main()
