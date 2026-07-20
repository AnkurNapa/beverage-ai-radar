from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "radar.sqlite"
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
HTTP_CACHE_DIR = PROJECT_ROOT / ".http_cache"

# Obsidian vault mirror target
VAULT_DIR = Path.home() / "Documents" / "obsidian" / "Beverage-AI Radar"

RECENCY_YEARS = 5
ACTIVE_MONTHS = 18

DISCOVERY_QUERIES = [
    "AI brewery", "GenAI winemaking", "machine learning distillery",
    "AI sensory beer", "computer vision wine quality", "AI flavor prediction beer",
    "generative AI wine marketing", "demand forecasting brewery AI",
    "whiskey distillery machine learning", "AI beverage quality control",
]
