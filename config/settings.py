from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _csv(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    sources: list[str] = field(default_factory=lambda: ["sporthub"])
    sports: list[str] = field(default_factory=lambda: ["dota"])
    db_path: Path = Path("data/arb.sqlite3")
    snapshot_path: Path = Path("data/events.json")
    log_path: Path = Path("data/arb.log")
    arbitrage_log_path: Path = Path("data/arbitrage.jsonl")
    reconnect_base: int = 5
    reconnect_max: int = 300
    ping_interval: int = 20
    idle_timeout: int = 90
    subscriptions_max_age: int = 3600
    state_ttl: int = 900
    batch_size: int = 250
    batch_interval: float = 0.25
    jump_threshold: float = 0.10
    jump_window: int = 60
    arbitrage_threshold: float = 1.0
    low_margin_threshold: float = 1.05
    min_odds: float = 1.01
    log_level: str = "INFO"


def load_settings() -> Settings:
    return Settings(
        sources=_csv("ARB_SOURCES", ["sporthub"]),
        sports=_csv("ARB_SPORTS", ["dota"]),
        db_path=Path(os.getenv("ARB_DB_PATH", "data/arb.sqlite3")),
        snapshot_path=Path(os.getenv("ARB_SNAPSHOT_PATH", "data/events.json")),
        log_path=Path(os.getenv("ARB_LOG_PATH", "data/arb.log")),
        arbitrage_log_path=Path(os.getenv("ARB_ARB_LOG_PATH", "data/arbitrage.jsonl")),
        reconnect_base=int(os.getenv("ARB_RECONNECT_BASE", "5")),
        reconnect_max=int(os.getenv("ARB_RECONNECT_MAX", "300")),
        ping_interval=int(os.getenv("ARB_PING_INTERVAL", "20")),
        idle_timeout=int(os.getenv("ARB_IDLE_TIMEOUT", "90")),
        subscriptions_max_age=int(os.getenv("ARB_SUBS_MAX_AGE", "3600")),
        state_ttl=int(os.getenv("ARB_STATE_TTL", "900")),
        batch_size=int(os.getenv("ARB_BATCH_SIZE", "250")),
        batch_interval=float(os.getenv("ARB_BATCH_INTERVAL", "0.25")),
        jump_threshold=float(os.getenv("ARB_JUMP_THRESHOLD", "0.10")),
        jump_window=int(os.getenv("ARB_JUMP_WINDOW", "60")),
        arbitrage_threshold=float(os.getenv("ARB_ARBITRAGE_THRESHOLD", "1.0")),
        low_margin_threshold=float(os.getenv("ARB_LOW_MARGIN_THRESHOLD", "1.05")),
        min_odds=float(os.getenv("ARB_MIN_ODDS", "1.01")),
        log_level=os.getenv("ARB_LOG_LEVEL", "INFO"),
    )
