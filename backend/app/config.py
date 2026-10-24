"""Central configuration. Everything here can be overridden with env vars."""
import os
from datetime import date, time
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_URL = os.getenv("ELEXON_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1")
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
TZ = ZoneInfo("Europe/London")

# ASSUMPTION (documented in README): the day-ahead purchase decision for delivery
# day D is taken on D-1 at this UK-local clock time. Only forecasts published at or
# before this moment are "available" to the trader.
DEFAULT_DECISION_TIME = time.fromisoformat(os.getenv("DECISION_TIME", "09:00"))

# Scope: purchase decisions made in January 2026 -> delivery days 2 Jan .. 1 Feb 2026.
DECISION_START = date(2026, 1, 1)
DECISION_END = date(2026, 1, 31)

# Forecasts further than this many hours ahead of their target are dropped at fetch time.
MAX_HORIZON_H = int(os.getenv("MAX_HORIZON_H", "96"))
