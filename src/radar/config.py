from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "radar.sqlite"
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
HTTP_CACHE_DIR = PROJECT_ROOT / ".http_cache"
SEED_PATH = PROJECT_ROOT / "data" / "seed.json"
PEOPLE_SEED_PATH = PROJECT_ROOT / "data" / "people_seed.json"

# Agentic scouting: briefs out, findings back in. .scout/ is working state.
SCOUT_DIR = PROJECT_ROOT / ".scout"
SCOUT_SURFACES_PATH = PROJECT_ROOT / "data" / "scout_surfaces.json"

# A slice counts as a coverage gap when it is both a small share of the corpus
# and a small absolute count. Either test alone misfires: share flags every
# value in a wide axis like country, count flags nothing once the seed is big.
GAP_MIN_COUNT = 12
GAP_MIN_SHARE = 0.08
GAP_TOP_N = 8
STALE_MONTHS = 12

# Obsidian vault mirror target
VAULT_DIR = Path.home() / "Documents" / "obsidian" / "Beverage-AI Radar"

RECENCY_YEARS = 10
ACTIVE_MONTHS = 18

DISCOVERY_QUERIES = [
    "AI brewery",
    "GenAI winemaking",
    "machine learning distillery",
    "AI sensory beer",
    "computer vision wine quality",
    "AI flavor prediction beer",
    "generative AI wine marketing",
    "demand forecasting brewery AI",
    "whiskey distillery machine learning",
    "AI beverage quality control",
]
