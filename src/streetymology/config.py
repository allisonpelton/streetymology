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

DATA_DIR.mkdir(parents=True, exist_ok=True)
