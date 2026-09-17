"""Central config, loaded from .env (never committed)."""
import contextlib
import json
import logging
import os
import pathlib
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


@contextlib.contextmanager
def atomic_write(path, mode="w", **kw):
    """Open `path` for writing so that it either appears whole or not at all.

    A stage that dies mid-write otherwise leaves a truncated file that still
    parses as far as it goes, and nothing downstream can tell. Two cases make
    this worth the ceremony rather than a bare `open`: the run records under
    `artifacts/batch_runs/`, which hold the id of a batch that is already
    costing money, and the results download, which `fetch` will not repeat
    because it sees a file already there.

    Writes to a temporary file in the same directory and renames, since
    os.replace is only atomic within one filesystem.

    The temporary file is opened with an explicit 0o666 rather than through
    `tempfile`, which forces 0600. 0o666 is what the built-in `open` requests,
    so the result carries whatever permissions umask gives any other file here
    and this function imposes no policy of its own.
    """
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o666)
        with os.fdopen(fd, mode, **kw) as fh:
            yield fh
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_json(path, obj, indent=None):
    """`obj` as JSON, atomically. The common case of `atomic_write`."""
    with atomic_write(path) as fh:
        json.dump(obj, fh, indent=indent)
    return pathlib.Path(path)


def log_to_stderr(level=logging.WARNING):
    """Send library warnings to stderr. For entry points only.

    A stage's own report goes to stdout with `print`, so that redirecting a run
    to a file captures the numbers and leaves the warnings visible in the
    terminal. Importing the package configures nothing.
    """
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def session(retries=4, backoff=1.0, timeout=120):
    """A requests Session that retries transport and server errors itself.

    Every fetch stage had its own loop with its own sleep, and two of them used
    urllib while two used requests. urllib3 does this properly, with exponential
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
