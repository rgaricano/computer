"""Centralized environment configuration for cptr.

All environment variable reads go here. Import from this module
instead of reading os.environ directly.
"""

from __future__ import annotations

import os
from pathlib import Path

# ── Data directory ──────────────────────────────────────────
# Where cptr stores its database, config, and user data.
# Default: ~/.cptr
DATA_DIR = Path(os.environ.get("CPTR_DATA_DIR", str(Path.home() / ".cptr")))
CONFIG_FILE = DATA_DIR / "config.toml"
DB_FILE = DATA_DIR / "app.db"

# ── Startup token ───────────────────────────────────────────
# One-time token for first-time setup. Set by CLI, consumed by app.
STARTUP_TOKEN: str | None = os.environ.pop("CPTR_STARTUP_TOKEN", None)

# ── Chat settings ───────────────────────────────────────────
CHAT_MAX_ITERATIONS = int(os.environ.get("CHAT_MAX_ITERATIONS", "2048"))
