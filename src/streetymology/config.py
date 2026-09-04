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

DATA_DIR.mkdir(parents=True, exist_ok=True)
LABELS_DIR.mkdir(parents=True, exist_ok=True)
