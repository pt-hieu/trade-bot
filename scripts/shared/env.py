"""
Environment file loader with SWINGY_ENV support.

SWINGY_ENV controls which .env file is loaded:
  - "production" → .env (Neon production database)
  - anything else / unset → .env.local (local Docker database)

GH Actions sets DATABASE_URL via secrets, so load_dotenv() is a no-op there.
Lightsail sets env via systemd, so .env.local not existing is fine.

SWINGY_DRY_RUN=true mocks all LLM calls and forces local Docker DB.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_LOCAL_DB_URL = "postgresql://swingy:localdev@localhost:5432/swingy"


def is_dry_run() -> bool:
    """Return True if SWINGY_DRY_RUN=true (case-insensitive)."""
    return os.environ.get("SWINGY_DRY_RUN", "").lower() in ("true", "1", "yes")


def is_production() -> bool:
    """Return True when SWINGY_ENV=production. Single source of truth for
    env-gated fail-loud vs fail-quiet decisions in pipeline code."""
    return os.environ.get("SWINGY_ENV") == "production"


def load_env() -> None:
    """Load the appropriate .env file based on SWINGY_ENV."""
    env = os.environ.get("SWINGY_ENV", "local")
    env_path = _PROJECT_ROOT / ".env" if env == "production" else _PROJECT_ROOT / ".env.local"

    if env_path.exists():
        load_dotenv(env_path)

    if is_dry_run():
        # Force local Docker DB regardless of SWINGY_ENV.
        # Strip OPENROUTER_API_KEY so any missed LLM path fails loud instead of billing.
        os.environ["DATABASE_URL"] = _LOCAL_DB_URL
        os.environ.pop("OPENROUTER_API_KEY", None)
        print("  [DRY RUN] LLM calls mocked | DB forced to localhost")
