"""Subdivision-level theme inference.

A street's own match must NEVER contribute to its subdivision's theme score.
Leave-one-out is mandatory: without it the signal confirms itself and any
evaluation against labels is meaningless.

Significance rather than raw counts: with 26 domains and small subdivisions,
coincidental matches are common. A subdivision of 3 streets where one matches
`plant` says nothing; 7 of 9 matching `bird` is decisive. We score the binomial
tail probability of seeing at least this many matches by chance, given the
domain's county-wide base rate.
"""
import json
import math
from collections import defaultdict
from .config import data_path


def binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p). Exact; n is small here."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return sum(math.comb(n, i) * p**i * (1 - p)**(n - i) for i in range(k, n + 1))


class ThemeModel:
    def __init__(self, assignments: dict, matches: dict[str, set[str]]):
        """assignments: core key -> {"subdivisions": {name: count}}
        matches: core key -> set of domains it matches.

        The gazetteer arm supplied these domains and was retired 2026-09-07.
        agreement() and unmatched_rate() are still tested but no longer called
        by anything: pass {} unless a new domain source appears."""
        self.members = defaultdict(set)          # subdivision -> {core keys}
        for k, v in assignments.items():
            for s in v["subdivisions"]:
                self.members[s].add(k)
        self.matches = matches
        total = len(assignments) or 1
        dom_counts = defaultdict(int)
        for doms in matches.values():
            for d in doms:
                dom_counts[d] += 1
        # county-wide base rate per domain, floored to avoid zero probabilities
        self.base = {d: max(c / total, 1e-4) for d, c in dom_counts.items()}

    def subdivisions_of(self, core: str, assignments: dict) -> list[str]:
        return list(assignments.get(core, {}).get("subdivisions", {}))

    def agreement(self, core: str, domain: str, subdivision: str) -> float:
        """How strongly this subdivision is themed on `domain`, EXCLUDING `core`.

        Returns 0.0 (no evidence) to 1.0 (overwhelming). 0.5 means the observed
        count would arise by chance half the time.
        """
        peers = self.members.get(subdivision, set()) - {core}
        n = len(peers)
        if n < 2:
            return 0.0                     # too small to carry a theme
        k = sum(1 for p in peers if domain in self.matches.get(p, ()))
        if k == 0:
            return 0.0
        return 1.0 - binom_sf(k, n, self.base.get(domain, 1e-4))

    def best_agreement(self, core: str, domain: str, assignments: dict) -> float:
        """Max agreement across every subdivision this street belongs to."""
        subs = self.subdivisions_of(core, assignments)
        return max((self.agreement(core, domain, s) for s in subs), default=0.0)

    def unmatched_rate(self, core: str, assignments: dict) -> float | None:
        """Fraction of peer streets matching NO gazetteer domain.

        High values indicate an invented-name subdivision. Author's rule:
        "invented confidence goes up for multiple invented streets".
        """
        best = None
        for s in self.subdivisions_of(core, assignments):
            peers = self.members.get(s, set()) - {core}
            if len(peers) < 2:
                continue
            rate = sum(1 for p in peers if not self.matches.get(p)) / len(peers)
            best = rate if best is None else max(best, rate)
        return best


def load(assignments_file="street_subdivisions.json"):
    return json.loads((data_path(assignments_file)).read_text())
