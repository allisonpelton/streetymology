"""Wikidata SPARQL client: shared by gazetteer building, candidate retrieval,
and QID validation. Handles retries and CSV parsing in one place."""
import csv, io, time
import requests
from .config import USER_AGENT

ENDPOINT = "https://query.wikidata.org/sparql"


def query(sparql: str, tries: int = 3, timeout: int = 300) -> list[dict]:
    """Run a SPARQL query, returning rows as dicts. Retries with backoff."""
    last = None
    for i in range(tries):
        try:
            r = requests.post(
                ENDPOINT, data={"query": sparql},
                headers={"Accept": "text/csv", "User-Agent": USER_AGENT},
                timeout=timeout,
            )
            if r.ok:
                return list(csv.DictReader(io.StringIO(r.text)))
            last = f"HTTP {r.status_code}: {r.text[:200]}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"SPARQL failed after {tries} tries — {last}")


def qid(uri: str) -> str:
    """Strip a Wikidata entity URI down to its QID."""
    return uri.rsplit("/", 1)[-1]
