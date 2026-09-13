"""Central config, loaded from .env (never committed)."""
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

# Pipeline data sits in the repo beside the code that reads it, but is not
# tracked: all of it re-downloads or recomputes. `streetymology-data` is for
# notes about the project, which the pipeline never touches.
DATA_DIR = Path(os.environ.get("STREETYMOLOGY_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"                  # downloaded sources
DERIVED_DIR = DATA_DIR / "derived"          # computed intermediates
ARTIFACTS_DIR = DATA_DIR / "artifacts"      # run output

# Tracked, because it cannot be regenerated.
LABELS = ROOT / "data" / "labels.csv"
# Anchored to ROOT, not DATA_DIR, so no pipeline stage can reach it by writing
# into its own output directory.
SUBDIVISIONS = ROOT / "data" / "subdivisions.json"

USER_AGENT = os.environ.get("WIKIDATA_USER_AGENT", "streetymology/0.1")


def session(retries=4, backoff=1.0, timeout=120):
    """A requests Session that retries transport and server errors itself.

    Every fetch stage had its own loop with its own sleep, and two of them used
    urllib while two used requests. urllib3 does this properly -- exponential
    backoff, and it honours Retry-After on a 429, which none of the hand-written
    loops did.
    """
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    retry = Retry(total=retries, backoff_factor=backoff,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset({"GET", "POST"}))
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.request_timeout = timeout
    return s
OVERPASS_ENDPOINTS = [
    e.strip() for e in os.environ.get("OVERPASS_ENDPOINTS", "").split(",") if e.strip()
] or ["https://overpass-api.de/api/interpreter"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

_HOMES = (("osm_", RAW_DIR), ("assessor_", RAW_DIR))


def data_path(name):
    """Downloads live in raw/, everything computed in derived/."""
    name = str(name)
    for prefix, home in _HOMES:
        if name.startswith(prefix):
            return home / name
    return DERIVED_DIR / name


for _d in (RAW_DIR, DERIVED_DIR, ARTIFACTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
