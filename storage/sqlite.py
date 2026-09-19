from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from models.domain import Odd, SourceEvent
from storage.repository import ChangedOdds

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS canonical_events (
    canonical_event_id TEXT PRIMARY KEY,
    sport TEXT NOT NULL,
    team1_name TEXT,
    team2_name TEXT,
    start_time TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS source_events (
    source TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    canonical_event_id TEXT NOT NULL,
    external_id TEXT,
    league_id TEXT,
    league_name TEXT,
    sport TEXT,
    start_time TEXT,
    score TEXT,
    team1_source_id TEXT,
    team1_name TEXT,
    team2_source_id TEXT,
    team2_name TEXT,
    updated_at REAL NOT NULL,
    PRIMARY KEY (source, source_event_id)
);

CREATE INDEX IF NOT EXISTS idx_source_events_canonical
    ON source_events(canonical_event_id);

CREATE TABLE IF NOT EXISTS odds_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    canonical_event_id TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    outcome_id TEXT,
    market_key TEXT NOT NULL,
    market_group TEXT,
    market_name TEXT,
    outcome_key TEXT NOT NULL,
    outcome_label TEXT,
    line REAL,
    odds REAL NOT NULL,
    ts REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_odds_canonical_market_ts
    ON odds_history(canonical_event_id, market_key, outcome_key, ts);
CREATE INDEX IF NOT EXISTS idx_odds_source_outcome_ts
    ON odds_history(source, outcome_id, ts);

CREATE TABLE IF NOT EXISTS current_odds (
    source TEXT NOT NULL,
    canonical_event_id TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    market_key TEXT NOT NULL,
    outcome_key TEXT NOT NULL,
    odds REAL NOT NULL,
    line REAL,
    updated_at REAL NOT NULL,
    PRIMARY KEY(source, canonical_event_id, market_key, outcome_key)
);
"""


class SQLiteRepository:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def init(self) -> None:
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def save_batch(self, events: list[SourceEvent], changed_odds: ChangedOdds) -> None:
        if not events:
            return
        import time
        ts = time.time()
        with self.conn:
            for event in events:
                t1 = event.teams[0] if len(event.teams) > 0 else None
                t2 = event.teams[1] if len(event.teams) > 1 else None
                self.conn.execute(
                    """
                    INSERT INTO canonical_events
                      (canonical_event_id, sport, team1_name, team2_name, start_time, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(canonical_event_id) DO UPDATE SET
                      sport=excluded.sport,
                      team1_name=excluded.team1_name,
                      team2_name=excluded.team2_name,
                      start_time=COALESCE(NULLIF(excluded.start_time, ''), canonical_events.start_time),
                      updated_at=excluded.updated_at
                    """,
                    (
                        event.canonical_event_id,
                        event.sport,
                        t1.name if t1 else None,
                        t2.name if t2 else None,
                        event.start_time,
                        ts,
                        ts,
                    ),
                )
                self.conn.execute(
                    """
                    INSERT INTO source_events
                      (source, source_event_id, canonical_event_id, external_id, league_id, league_name,
                       sport, start_time, score, team1_source_id, team1_name,
                       team2_source_id, team2_name, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source, source_event_id) DO UPDATE SET
                      canonical_event_id=excluded.canonical_event_id,
                      external_id=excluded.external_id,
                      league_id=excluded.league_id,
                      league_name=excluded.league_name,
                      sport=excluded.sport,
                      start_time=excluded.start_time,
                      score=excluded.score,
                      team1_source_id=excluded.team1_source_id,
                      team1_name=excluded.team1_name,
                      team2_source_id=excluded.team2_source_id,
                      team2_name=excluded.team2_name,
                      updated_at=excluded.updated_at
                    """,
                    (
                        event.source,
                        event.event_id,
                        event.canonical_event_id,
                        event.external_id,
                        event.league_id,
                        event.league_name,
                        event.sport,
                        event.start_time,
                        event.score,
                        t1.source_team_id if t1 else None,
                        t1.name if t1 else None,
                        t2.source_team_id if t2 else None,
                        t2.name if t2 else None,
                        ts,
                    ),
                )

                for odd in changed_odds.get((event.source, event.event_id), []):
                    self.conn.execute(
                        """
                        INSERT INTO odds_history
                          (source, canonical_event_id, source_event_id, outcome_id, market_key,
                           market_group, market_name, outcome_key, outcome_label, line, odds, ts)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.source,
                            event.canonical_event_id,
                            event.event_id,
                            odd.outcome_id,
                            odd.market_key,
                            odd.market_group,
                            odd.market_name,
                            odd.outcome_key,
                            odd.outcome_label,
                            odd.line,
                            odd.odds,
                            ts,
                        ),
                    )
                    self.conn.execute(
                        """
                        INSERT INTO current_odds
                          (source, canonical_event_id, source_event_id, market_key, outcome_key,
                           odds, line, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(source, canonical_event_id, market_key, outcome_key) DO UPDATE SET
                          source_event_id=excluded.source_event_id,
                          odds=excluded.odds,
                          line=excluded.line,
                          updated_at=excluded.updated_at
                        """,
                        (
                            event.source,
                            event.canonical_event_id,
                            event.event_id,
                            odd.market_key,
                            odd.outcome_key,
                            odd.odds,
                            odd.line,
                            ts,
                        ),
                    )

    def close(self) -> None:
        self.conn.close()
