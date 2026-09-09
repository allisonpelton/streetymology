"""Central config, loaded from .env (never committed)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

# Pipeline data sits in the repo beside the code that reads it, but is not
# tracked: all of it re-downloads or recomputes. `streetymology-data` is for
# notes about the project, which the pipeline never touches.
DATA_DIR = Path(os.environ.get("STREETYMOLOGY_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"                  # downloaded sources
DERIVED_DIR = DATA_DIR / "derived"          # computed intermediates
ARTIFACTS_DIR = DATA_DIR / "artifacts"      # run output

# Tracked, because neither can be regenerated.
LABELS = ROOT / "data" / "labels.csv"
JUDGEMENT_DIR = ROOT / "data" / "plat_judgement"

USER_AGENT = os.environ.get("WIKIDATA_USER_AGENT", "streetymology/0.1")
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
