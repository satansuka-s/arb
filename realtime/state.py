from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from models.domain import Odd, SourceEvent


class RealtimeState:
    def __init__(self, snapshot_path: Path, ttl_seconds: int):
        self.snapshot_path = snapshot_path
        self.ttl_seconds = ttl_seconds
        self.events: dict[str, SourceEvent] = {}
        self.last_update: dict[str, float] = {}
        self.dirty = False

    def _key(self, event: SourceEvent) -> str:
        return f"{event.source}:{event.event_id}"

    def apply(self, event: SourceEvent) -> list[Odd]:
        key = self._key(event)
        previous = self.events.get(key)
        changed: list[Odd] = []
        if previous is None:
            changed = list(event.odds)
        else:
            old = {(o.market_key, o.outcome_key): o.odds for o in previous.odds}
            for odd in event.odds:
                if old.get((odd.market_key, odd.outcome_key)) != odd.odds:
                    changed.append(odd)
        self.events[key] = event
        self.last_update[key] = event.received_at or time.time()
        self.dirty = True
        return changed

    def purge(self) -> int:
        now = time.time()
        expired = [key for key, ts in self.last_update.items() if now - ts > self.ttl_seconds]
        for key in expired:
            self.last_update.pop(key, None)
            self.events.pop(key, None)
        if expired:
            self.dirty = True
        return len(expired)

    def dump_snapshot(self) -> None:
        if not self.dirty:
            return
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: event.to_dict() for key, event in self.events.items()}
        tmp = self.snapshot_path.with_suffix(self.snapshot_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.snapshot_path)
        self.dirty = False
