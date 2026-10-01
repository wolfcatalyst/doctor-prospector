"""Simple JSON-based user profile for saving default preferences.

Stores user defaults (search scope, specialty, filters) in a JSON file
so settings persist between sessions without needing a database or accounts.

Usage:
    from src.doctor_prospector.profiles import load_profile, save_profile

    profile = load_profile()  # loads data/profiles/default.json
    profile['defaults']['search_scope'] = 'state'
    save_profile(profile)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .paths import DATA_DIR

logger = logging.getLogger(__name__)

PROFILES_DIR = DATA_DIR / "profiles"
DEFAULT_PROFILE_PATH = PROFILES_DIR / "default.json"

# Default settings — used when no profile file exists yet
DEFAULT_PROFILE: dict[str, Any] = {
    "name": "Default",
    "created": None,
    "updated": None,
    "defaults": {
        # Hospital detail page
        "search_scope": "city",
        "specialty_filter": [],
        "show_payments": False,
        "show_trends": False,
        # Red/yellow data-quality warnings on hospitals and physicians
        "show_data_flags": True,
        # "Login is off" banner (hide once you've decided login isn't needed)
        "show_auth_notice": True,
        # Post-search filters (empty = all checked)
        "preferred_specialties": [],
        "min_volume": 0,
        "sort_by": "volume",
        # Payment filters
        "payment_company_filter": "All Companies",
        "payment_level_filter": "All Payment Levels",
        # Hospital browser
        "default_states": [],
    },
}


def load_profile(path: Path | None = None) -> dict[str, Any]:
    """Load a user profile from JSON file.

    Returns default settings if the file doesn't exist yet.
    """
    path = path or DEFAULT_PROFILE_PATH
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                profile = json.load(f)
            logger.info(f"Loaded profile from {path}")
            # Merge with defaults to handle new fields added after profile was saved
            merged = DEFAULT_PROFILE.copy()
            merged["defaults"] = {**DEFAULT_PROFILE["defaults"], **profile.get("defaults", {})}
            merged["name"] = profile.get("name", "Default")
            merged["created"] = profile.get("created")
            merged["updated"] = profile.get("updated")
            return merged
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Error loading profile from {path}: {e}")
    return DEFAULT_PROFILE.copy()


def save_profile(profile: dict[str, Any], path: Path | None = None) -> None:
    """Save a user profile to JSON file."""
    path = path or DEFAULT_PROFILE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat()
    if not profile.get("created"):
        profile["created"] = now
    profile["updated"] = now
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
    logger.info(f"Saved profile to {path}")
