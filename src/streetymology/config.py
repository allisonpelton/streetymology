"""Central config, loaded from .env (never committed)."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.environ.get("STREETYMOLOGY_DATA_DIR", ROOT.parent / "streetymology-data"))
USER_AGENT = os.environ.get("WIKIDATA_USER_AGENT", "streetymology/0.1")
OVERPASS_ENDPOINTS = [
    e.strip() for e in os.environ.get("OVERPASS_ENDPOINTS", "").split(",") if e.strip()
] or ["https://overpass-api.de/api/interpreter"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Human-authored ground truth lives IN the repo: it cannot be regenerated,
# unlike everything in DATA_DIR, which re-downloads.
LABELS_DIR = ROOT / "data" / "labels"

# DATA_DIR is organised into subfolders. See scripts/organize_data.py.
RAW_DIR = DATA_DIR / "raw"                    # downloaded, re-fetchable sources
GAZ_DIR = DATA_DIR / "gazetteers"             # Wikidata domain dumps
DERIVED_DIR = DATA_DIR / "derived"            # computed intermediates
ARTIFACTS_DIR = DATA_DIR / "artifacts"        # machine run output
DELIVERABLES_DIR = DATA_DIR / "deliverables"  # human-facing documents
BUNDLES_DIR = DATA_DIR / "bundles"            # git bundle backups
UNUSED_DIR = DATA_DIR / "unused"              # stale; author deletes these

# Filename prefix -> home. Keeps call sites from hard-coding directories.
_HOMES = (
    ("osm_", RAW_DIR),
    ("assessor_", RAW_DIR),
    ("gaz_", GAZ_DIR),
    ("meta_", DERIVED_DIR),
    ("search_", DERIVED_DIR),
    ("llm_batch", DERIVED_DIR),
    ("street_", DERIVED_DIR),
    ("place_", DERIVED_DIR),
)


def data_path(name):
    """Resolve a data filename to its subfolder inside DATA_DIR."""
    name = str(name)
    for prefix, home in _HOMES:
        if name.startswith(prefix):
            return home / name
    return DATA_DIR / name


for _d in (DATA_DIR, RAW_DIR, GAZ_DIR, DERIVED_DIR, ARTIFACTS_DIR,
           DELIVERABLES_DIR, BUNDLES_DIR, UNUSED_DIR, LABELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
