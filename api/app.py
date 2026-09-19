from __future__ import annotations

import sqlite3
from pathlib import Path

from config.settings import load_settings


class ApiStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def events(self, limit: int = 100):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM source_events ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def create_app():
    try:
        from fastapi import FastAPI, Query
    except ImportError as exc:
        raise RuntimeError("Install optional API dependencies: pip install -e '.[api]'") from exc

    app = FastAPI(title="ARB Platform API", version="0.1.0")
    store = ApiStore(load_settings().db_path)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/events")
    def events(limit: int = Query(default=100, ge=1, le=1000)):
        return store.events(limit)

    return app


app = None
try:
    app = create_app()
except RuntimeError:
    # API dependencies are intentionally optional for collector-only installs.
    pass
