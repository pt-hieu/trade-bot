"""
Shared pytest configuration for evals.

- Adds scripts/ to sys.path
- Loads LOGFIRE_TOKEN from .env and configures Logfire for evals dashboard
- Sets safe env defaults (no production DB, cheap models)
"""

import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent

# Add scripts to path for agent/shared imports
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# Load LOGFIRE_TOKEN from .env (not in .env.local)
load_dotenv(PROJECT_ROOT / ".env", override=False)

# Configure Logfire BEFORE any eval imports — results appear in Logfire Evals tab
import logfire

logfire.configure(
    send_to_logfire="if-token-present",
    service_name="swingy",
    environment="eval",
)


@pytest.fixture(autouse=True)
def eval_environment(monkeypatch):
    """Safe defaults for eval runs — cheap models, no production DB."""
    monkeypatch.setenv("SWINGY_MODEL_TIER", "cheap")
    monkeypatch.setenv("SWINGY_ENV", "local")
    # Don't leak real tokens — tests that need them must set explicitly
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    # Keep LOGFIRE_TOKEN so eval results appear in Logfire Evals dashboard
