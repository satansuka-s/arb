from __future__ import annotations

from pathlib import Path
from typing import Any

from models.domain import Odd, SourceEvent


SCHEMA = """
CREATE TABLE IF NOT EXISTS canonical_events (
    canonical_event_id TEXT PRIMARY KEY,
    sport TEXT NOT NULL,
    team1_name TEXT,
    team2_name TEXT,
    start_time TEXT,
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
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
    updated_at DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (source, source_event_id)
);
CREATE INDEX IF NOT EXISTS idx_source_events_canonical ON source_events(canonical_event_id);
CREATE TABLE IF NOT EXISTS odds_history (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    canonical_event_id TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    outcome_id TEXT,
    market_key TEXT NOT NULL,
    market_group TEXT,
    market_name TEXT,
    outcome_key TEXT NOT NULL,
    outcome_label TEXT,
    line DOUBLE PRECISION,
    odds DOUBLE PRECISION NOT NULL,
    ts DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_odds_canonical_market_ts ON odds_history(canonical_event_id, market_key, outcome_key, ts);
CREATE INDEX IF NOT EXISTS idx_odds_source_outcome_ts ON odds_history(source, outcome_id, ts);
CREATE TABLE IF NOT EXISTS current_odds (
    source TEXT NOT NULL,
    canonical_event_id TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    market_key TEXT NOT NULL,
    outcome_key TEXT NOT NULL,
    odds DOUBLE PRECISION NOT NULL,
    line DOUBLE PRECISION,
    updated_at DOUBLE PRECISION NOT NULL,
    PRIMARY KEY(source, canonical_event_id, market_key, outcome_key)
);
"""


class PostgresRepository:
    """Optional PostgreSQL backend.

    Install psycopg with `pip install 'psycopg[binary]>=3.2'` and pass a DSN.
    The runtime only depends on the small repository interface, so the source
    adapters and detectors do not change when the backend changes.
    """

    def __init__(self, dsn: str):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("Install PostgreSQL support: pip install 'psycopg[binary]>=3.2'") from exc
        self.conn = psycopg.connect(dsn)

    def init(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(SCHEMA)
        self.conn.commit()

    def save_batch(self, events: list[SourceEvent], changed_odds: dict[tuple[str, str], list[Odd]]) -> None:
        import time
        if not events:
            return
        ts = time.time()
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                for event in events:
                    t1 = event.teams[0] if len(event.teams) > 0 else None
                    t2 = event.teams[1] if len(event.teams) > 1 else None
                    cur.execute(
                        """
                        INSERT INTO canonical_events
                        (canonical_event_id, sport, team1_name, team2_name, start_time, created_at, updated_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(canonical_event_id) DO UPDATE SET
                          sport=EXCLUDED.sport, team1_name=EXCLUDED.team1_name,
                          team2_name=EXCLUDED.team2_name,
                          start_time=COALESCE(NULLIF(EXCLUDED.start_time,''), canonical_events.start_time),
                          updated_at=EXCLUDED.updated_at
                        """,
                        (event.canonical_event_id, event.sport, t1.name if t1 else None, t2.name if t2 else None,
                         event.start_time, ts, ts),
                    )
                    cur.execute(
                        """
                        INSERT INTO source_events
                        (source,source_event_id,canonical_event_id,external_id,league_id,league_name,sport,start_time,score,
                         team1_source_id,team1_name,team2_source_id,team2_name,updated_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(source,source_event_id) DO UPDATE SET
                          canonical_event_id=EXCLUDED.canonical_event_id, external_id=EXCLUDED.external_id,
                          league_id=EXCLUDED.league_id, league_name=EXCLUDED.league_name, sport=EXCLUDED.sport,
                          start_time=EXCLUDED.start_time, score=EXCLUDED.score,
                          team1_source_id=EXCLUDED.team1_source_id, team1_name=EXCLUDED.team1_name,
                          team2_source_id=EXCLUDED.team2_source_id, team2_name=EXCLUDED.team2_name,
                          updated_at=EXCLUDED.updated_at
                        """,
                        (event.source, event.event_id, event.canonical_event_id, event.external_id, event.league_id,
                         event.league_name, event.sport, event.start_time, event.score,
                         t1.source_team_id if t1 else None, t1.name if t1 else None,
                         t2.source_team_id if t2 else None, t2.name if t2 else None, ts),
                    )
                    for odd in changed_odds.get((event.source, event.event_id), []):
                        cur.execute(
                            """
                            INSERT INTO odds_history
                            (source,canonical_event_id,source_event_id,outcome_id,market_key,market_group,market_name,
                             outcome_key,outcome_label,line,odds,ts)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """,
                            (event.source, event.canonical_event_id, event.event_id, odd.outcome_id, odd.market_key,
                             odd.market_group, odd.market_name, odd.outcome_key, odd.outcome_label, odd.line, odd.odds, ts),
                        )
                        cur.execute(
                            """
                            INSERT INTO current_odds
                            (source,canonical_event_id,source_event_id,market_key,outcome_key,odds,line,updated_at)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT(source,canonical_event_id,market_key,outcome_key) DO UPDATE SET
                              source_event_id=EXCLUDED.source_event_id, odds=EXCLUDED.odds,
                              line=EXCLUDED.line, updated_at=EXCLUDED.updated_at
                            """,
                            (event.source, event.canonical_event_id, event.event_id, odd.market_key, odd.outcome_key,
                             odd.odds, odd.line, ts),
                        )

    def close(self) -> None:
        self.conn.close()
