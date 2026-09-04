"""Per-signal scorers for match plausibility.

Pure functions: no network, no file I/O, so they are testable in isolation.
Each returns a float in [0, 1] where HIGHER means MORE plausible.

The signals deliberately stay separate rather than being pre-blended, because
they catch different failure modes:
  commonness  - 'Rainbow', 'Buffalo': the string collided with a common word
  notability  - 'Blake Run', 'Valentino': a real item nobody names a street for
  nameness    - 'Blake', 'Baker': matched a feature named for a DIFFERENT person
"""
from wordfreq import zipf_frequency

# Zipf scale is ~0 (never seen) to ~7 ("the"). Observed in Ada County matches:
# correct matches clustered 1.7-3.2, incorrect 2.8-5.2.
ZIPF_DISTINCTIVE = 2.0   # at or below this, treat as fully distinctive
ZIPF_GENERIC = 5.0       # at or above this, treat as hopelessly generic


def commonness(text: str) -> float:
    """1.0 = rare/distinctive wording, 0.0 = everyday English.

    Multi-word strings score by their COMMONEST token: 'Golden Eagle' is only
    as distinctive as its weakest part.
    """
    toks = [t for t in text.split() if t]
    if not toks:
        return 0.0
    worst = max(zipf_frequency(t, "en") for t in toks)
    if worst <= ZIPF_DISTINCTIVE:
        return 1.0
    if worst >= ZIPF_GENERIC:
        return 0.0
    return 1.0 - (worst - ZIPF_DISTINCTIVE) / (ZIPF_GENERIC - ZIPF_DISTINCTIVE)


def notability(sitelinks: int, statements: int = 0) -> float:
    """1.0 = widely documented concept, 0.0 = bulk-import stub.

    Sitelink count is a proxy for how much human attention an item has had.
    Saturates at 20 -- beyond that, more Wikipedias adds no information here.
    """
    if sitelinks <= 0:
        return 0.0 if statements < 15 else 0.1
    return min(1.0, sitelinks / 20.0)


def nameness(is_surname: bool, is_given_name: bool) -> float:
    """0.0 = the string is a personal name, 1.0 = it is not.

    A street matching 'Blake Run' is near-certainly named for a local Blake,
    not for a Pennsylvania stream that was itself named for another Blake.
    """
    if is_surname and is_given_name:
        return 0.0
    if is_surname or is_given_name:
        return 0.2
    return 1.0


def specificity(matched_text: str) -> float:
    """Longer matched spans are far less likely to be coincidental."""
    n = len([t for t in matched_text.split() if t])
    return {0: 0.0, 1: 0.4, 2: 0.85}.get(n, 1.0)


def collision(domain_count: int) -> float:
    """1.0 = matched exactly one domain, falling off as it matches more."""
    if domain_count <= 1:
        return 1.0
    return max(0.0, 1.0 - (domain_count - 1) * 0.3)
