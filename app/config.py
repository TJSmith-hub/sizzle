"""Application configuration, driven by environment variables.

All settings have sensible defaults so the app runs with zero config for local
development, while Docker/compose can override them via the environment.
"""
from __future__ import annotations

import os
from pathlib import Path

# Absolute path to the SQLite database file. In Docker this points at the
# mounted volume (/data/recipes.db); locally it defaults to ./data/recipes.db.
DATABASE_PATH: str = os.environ.get(
    "DATABASE_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "recipes.db"),
)

# Default unit system used for display and shopping lists: "metric" or "imperial".
# Users can still toggle per-recipe in the UI; this is only the starting point.
DEFAULT_UNIT_SYSTEM: str = os.environ.get("DEFAULT_UNIT_SYSTEM", "metric").lower()
if DEFAULT_UNIT_SYSTEM not in ("metric", "imperial"):
    DEFAULT_UNIT_SYSTEM = "metric"

# User-Agent used when fetching recipe pages. Many sites reject the default
# python-requests/httpx UA with a 403, so we present a normal browser string.
FETCH_USER_AGENT: str = os.environ.get(
    "FETCH_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
)

# Timeout (seconds) for fetching a recipe page.
FETCH_TIMEOUT: float = float(os.environ.get("FETCH_TIMEOUT", "20"))
