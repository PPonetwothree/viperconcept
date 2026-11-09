"""Runtime configuration.

Values come from environment variables, optionally loaded from ``backend/.env``
(see ``.env.example``). No third-party dotenv dependency is used.
"""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
DOCS_DIR = PROJECT_DIR / "documentation"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file(BACKEND_DIR / ".env")


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


HOST = os.environ.get("VIPER_HOST", "127.0.0.1")
PORT = int(_float("VIPER_PORT", 8000))
DB_PATH = Path(os.environ.get("VIPER_DB_PATH", str(BACKEND_DIR / "data" / "viper.db")))
DEFAULT_ENVIRONMENT = os.environ.get("VIPER_DEFAULT_ENVIRONMENT", "airport")
TICK_HZ = _float("VIPER_TICK_HZ", 5.0)
SNAPSHOT_HZ = _float("VIPER_SNAPSHOT_HZ", 5.0)
# Fusion: observations in the same zone within this many seconds are correlated.
CORRELATION_WINDOW_S = _float("VIPER_CORRELATION_WINDOW_S", 6.0)
# Edge node heartbeat interval and the timeout that raises a communication failure.
HEARTBEAT_INTERVAL_S = _float("VIPER_HEARTBEAT_INTERVAL_S", 2.0)
HEARTBEAT_TIMEOUT_S = _float("VIPER_HEARTBEAT_TIMEOUT_S", 7.0)
# Ambient background activity (animals, gusts, unverified movement) per simulated minute.
AMBIENT_EVENTS_PER_MIN = _float("VIPER_AMBIENT_EVENTS_PER_MIN", 1.0)
RANDOM_SEED = int(_float("VIPER_RANDOM_SEED", 0)) or None
AUTOSTART = os.environ.get("VIPER_AUTOSTART", "1") == "1"
