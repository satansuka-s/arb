from __future__ import annotations

import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path

from models.domain import SourceEvent
from .names import normalize_name


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class CanonicalEventMatcher:
    """Deterministic first-stage cross-book matcher.

    Matching deliberately ignores source event ids. The same pair of teams on the
    same sport/date-time bucket therefore receives the same canonical id across books.
    Aliases can be added later without changing the rest of the pipeline.
    """

    bucket_hours = 6

    def __init__(self, aliases_path: Path | None = None):
        self.aliases: dict[str, str] = {}
        if aliases_path is not None and aliases_path.exists():
            try:
                data = json.loads(aliases_path.read_text(encoding="utf-8"))
                for canonical, aliases in data.items():
                    if isinstance(aliases, list):
                        self.aliases[normalize_name(canonical)] = normalize_name(canonical)
                        for alias in aliases:
                            self.aliases[normalize_name(str(alias))] = normalize_name(canonical)
                    else:
                        self.aliases[normalize_name(str(canonical))] = normalize_name(str(aliases))
            except Exception:
                pass

    def team_name(self, value: str) -> str:
        normalized = normalize_name(value)
        return self.aliases.get(normalized, normalized)

    def canonicalize(self, event: SourceEvent) -> SourceEvent:
        team_names = [self.team_name(team.name) for team in event.teams if team.name]
        if len(team_names) >= 2:
            team_names = sorted(team_names[:2])
            base = "|".join(team_names)
        elif team_names:
            base = team_names[0]
        else:
            base = f"source-event:{event.source}:{event.event_id}"

        dt = _parse_time(event.start_time)
        if dt is not None:
            bucket = int(dt.timestamp()) // (self.bucket_hours * 3600)
            time_part = str(bucket)
        else:
            time_part = "unknown-time"

        # Do not include the sport in the identity: one source may expose a sport
        # name while another exposes only an unknown/empty value. Team pair + time
        # keeps cross-book matching stable; sport remains a canonical attribute.
        payload = "|".join((base, time_part)).encode("utf-8")
        canonical_id = hashlib.sha256(payload).hexdigest()[:24]
        event.canonical_event_id = canonical_id
        return event
