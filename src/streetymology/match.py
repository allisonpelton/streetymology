"""Match a normalized core street name against gazetteer indexes.

Confidence tiers, highest first:
  full    - the entire core name is a gazetteer entry ("Golden Eagle" -> bird)
  surname - the core name is a person's surname ("Lincoln" -> Abraham Lincoln)
Span/token matching ("Quail Ridge" -> quail) lands here next; it needs a
common-word stoplist first or it floods the results with false positives.
"""
from dataclasses import dataclass
from .normalize import key


@dataclass(frozen=True)
class Candidate:
    domain: str
    qid: str
    name: str
    via: str          # how it matched: full | surname
    confidence: float


VIA_CONFIDENCE = {"full": 0.9, "surname": 0.5}


def build_indexes(domains, index_fn) -> dict[str, dict]:
    return {d: index_fn(d) for d in domains}


def match(street_name: str, indexes: dict[str, dict], allow_surname=True) -> list[Candidate]:
    """Return candidates for one street name, best-confidence first."""
    k = key(street_name)
    if not k:
        return []
    out = []
    for domain, idx in indexes.items():
        for e in idx.get(k, []):
            if e["via"] == "surname" and not allow_surname:
                continue
            out.append(Candidate(domain, e["qid"], e["name"], e["via"],
                                 VIA_CONFIDENCE[e["via"]]))
    return sorted(out, key=lambda c: -c.confidence)


def is_ambiguous(cands: list[Candidate]) -> bool:
    return len({c.domain for c in cands}) > 1
