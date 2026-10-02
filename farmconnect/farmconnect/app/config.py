"""Central configuration. Secrets come from environment variables, never the repo."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
DB_PATH = os.getenv("FARM_DB_PATH", str(BASE_DIR / "farm.db"))

DELIVERY_FEE = 1000.0          # naira, flat fee for the MVP
STORE_TIMEOUT_SECONDS = 3.0    # max wait per external store
CACHE_TTL_SECONDS = 30 * 60    # comparison results cached for 30 minutes
MIN_PASSWORD_LENGTH = 8
