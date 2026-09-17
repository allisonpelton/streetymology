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

# Pipeline data is in the repo beside the code that reads it, but is not
# tracked: all of it re-downloads or recomputes. `streetymology-data` is for
# notes about the project, which the pipeline never touches.
DATA_DIR = Path(os.environ.get("STREETYMOLOGY_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"                  # downloaded sources
DERIVED_DIR = DATA_DIR / "derived"          # computed intermediates
ARTIFACTS_DIR = DATA_DIR / "artifacts"      # run output

# Tracked, because it cannot be regenerated. Anchored to ROOT, not DATA_DIR, so
# no pipeline stage reaches it by writing into its own output directory.
LABELS = ROOT / "data" / "labels.csv"

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


def write_json(path, obj, indent=None, compact=False):
    """`obj` as JSON, atomically. The common case of `atomic_write`.

    `compact` drops the space after every comma and colon. On a file the size
    of the street export that is worth about 8% before compression, and no
    reader cares.
    """
    seps = (",", ":") if compact else None
    with atomic_write(path) as fh:
        json.dump(obj, fh, indent=indent, separators=seps)
    return pathlib.Path(path)


def log_to_stderr(level=logging.WARNING):
    """Warnings to stderr. Entry points call this; importing configures nothing.

    A stage's own numbers go to stdout, so redirecting a run to a file still
    shows the warnings in the terminal.
    """
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def session(retries=4, backoff=1.0, timeout=120):
    """A requests Session that retries transport and server errors itself.

    urllib3 backs off exponentially and honours Retry-After on a 429. A
    hand-written sleep loop in each fetch stage does neither.
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
    """Downloaded files resolve to raw/, computed files to derived/."""
    name = str(name)
    for prefix, home in _HOMES:
        if name.startswith(prefix):
            return home / name
    return DERIVED_DIR / name


for _d in (RAW_DIR, DERIVED_DIR, ARTIFACTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
