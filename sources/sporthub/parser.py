from __future__ import annotations

import json
import struct
from dataclasses import asdict
from pathlib import Path
from typing import Any

from models.domain import Odd, SourceEvent, Team


def read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while pos < len(buf):
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")
    raise ValueError("truncated varint")


def read_fields(buf: bytes, pos: int = 0, end: int | None = None) -> dict[int, list[Any]]:
    if end is None:
        end = len(buf)
    fields: dict[int, list[Any]] = {}
    while pos < end:
        tag, pos = read_varint(buf, pos)
        fn = tag >> 3
        wt = tag & 0x07
        if fn <= 0:
            raise ValueError("invalid protobuf field number")
        if wt == 0:
            val, pos = read_varint(buf, pos)
        elif wt == 1:
            if pos + 8 > end:
                raise ValueError("truncated fixed64")
            val = struct.unpack_from("<d", buf, pos)[0]
            pos += 8
        elif wt == 2:
            length, pos = read_varint(buf, pos)
            if length < 0 or pos + length > end:
                raise ValueError("truncated length-delimited field")
            val = buf[pos:pos + length]
            pos += length
        elif wt == 5:
            if pos + 4 > end:
                raise ValueError("truncated fixed32")
            val = struct.unpack_from("<f", buf, pos)[0]
            pos += 4
        else:
            raise ValueError(f"unsupported wire type {wt}")
        fields.setdefault(fn, []).append(val)
    return fields


def first(fields: dict[int, list[Any]], key: int, default: Any = None) -> Any:
    values = fields.get(key)
    return values[0] if values else default


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class SporthubParser:
    """Decoder for the current sporthub.bet tree_ws protobuf-like payloads."""

    def __init__(self, sport_cache_path: Path, sport_names_path: Path, debug_path: Path | None = None):
        self.sport_cache_path = sport_cache_path
        self.sport_names_path = sport_names_path
        self.debug_path = debug_path
        self.league_sport: dict[int, str] = {}
        self.sport_names: dict[int, str] = {}
        self.tree_dumped = False
        self._load_caches()

    def _load_caches(self) -> None:
        for path, target in ((self.sport_cache_path, self.league_sport), (self.sport_names_path, self.sport_names)):
            try:
                if path.exists():
                    data = json.loads(path.read_text(encoding="utf-8"))
                    for key, value in data.items():
                        target[int(key)] = str(value)
            except Exception:
                continue

    def _save_caches(self) -> None:
        self.sport_cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.sport_cache_path.write_text(
            json.dumps({str(k): v for k, v in self.league_sport.items()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.sport_names_path.write_text(
            json.dumps({str(k): v for k, v in self.sport_names.items()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def parse_team(self, buf: bytes) -> Team:
        f = read_fields(buf)
        return Team(
            source_team_id=text(first(f, 1, 0)),
            external_id=text(first(f, 2, b"")),
            name=text(first(f, 3, b"")),
            logo=text(first(f, 7, b"")),
            color=text(first(f, 8, b"")),
        )

    def parse_odd(self, buf: bytes) -> Odd:
        f = read_fields(buf)
        line_raw = first(f, 9, 0.0)
        odds_raw = first(f, 10, 0.0)
        line = float(line_raw) if isinstance(line_raw, (int, float)) else None
        odds = float(odds_raw) if isinstance(odds_raw, (int, float)) else 0.0
        return Odd(
            outcome_id=text(first(f, 1, b"")),
            market_id=text(first(f, 2, 0)),
            outcome_label=text(first(f, 5, b"")),
            market_name=text(first(f, 14, b"")),
            market_group=text(first(f, 18, b"")),
            line=line,
            odds=odds,
            view_type=text(first(f, 16, b"")),
            sort=int(first(f, 19, 0) or 0),
            source_market_key=text(first(f, 24, b"")),
        )

    def _parse_event(self, buf: bytes) -> SourceEvent | None:
        outer = read_fields(buf)
        league_blob = first(outer, 1)
        if not isinstance(league_blob, bytes):
            return None
        league = read_fields(league_blob)
        event_id_raw = first(league, 1, 0)
        try:
            event_id = int(event_id_raw)
        except (TypeError, ValueError):
            return None
        if event_id <= 0:
            return None

        teams: list[Team] = []
        teams_raw = first(league, 16)
        if isinstance(teams_raw, bytes):
            tf = read_fields(teams_raw)
            for key in (1, 3):
                raw_team = first(tf, key)
                if isinstance(raw_team, bytes):
                    teams.append(self.parse_team(raw_team))

        score = ""
        score_raw = first(league, 20)
        if isinstance(score_raw, bytes):
            score_fields = read_fields(score_raw)
            score = text(first(score_fields, 2, b""))

        odds: list[Odd] = []
        for market in outer.get(2, []):
            if isinstance(market, bytes):
                try:
                    odds.append(self.parse_odd(market))
                except ValueError:
                    continue

        league_id = text(first(league, 10, 0))
        league_name = text(first(league, 11, b""))
        sport = self.league_sport.get(int(league_id)) if league_id.isdigit() else ""
        return SourceEvent(
            source="sporthub",
            event_id=str(event_id),
            external_id=text(first(league, 5, b"")),
            league_id=league_id,
            league_name=league_name,
            sport=sport or "unknown",
            start_time=text(first(league, 13, b"")),
            teams=teams,
            score=score,
            odds=odds,
        )

    def _walk_messages(self, blob: bytes, depth: int = 0):
        if depth > 8:
            return
        try:
            fields = read_fields(blob)
        except ValueError:
            return
        yield fields
        for values in fields.values():
            for value in values:
                if isinstance(value, bytes) and value:
                    yield from self._walk_messages(value, depth + 1)

    def _update_tree_cache(self, tree_blob: bytes) -> None:
        # The source changes the exact tree envelope over time. We therefore use
        # conservative structural detection and keep unknown data instead of
        # discarding events.
        found_change = False
        for fields in self._walk_messages(tree_blob):
            sport_id = first(fields, 1)
            sport_name_raw = first(fields, 3)
            if isinstance(sport_id, int) and sport_id > 0 and isinstance(sport_name_raw, bytes):
                sport_name = text(sport_name_raw).strip()
                if sport_name and len(sport_name) < 120 and "http" not in sport_name:
                    if self.sport_names.get(sport_id) != sport_name:
                        self.sport_names[sport_id] = sport_name
                        found_change = True
        if found_change:
            self._save_caches()

    def parse_frame(self, buf: bytes) -> list[SourceEvent]:
        fields = read_fields(buf)
        for key in (6, 8):
            for blob in fields.get(key, []):
                if isinstance(blob, bytes):
                    if not self.tree_dumped and self.debug_path is not None:
                        self.debug_path.parent.mkdir(parents=True, exist_ok=True)
                        self.debug_path.write_text(blob.hex(), encoding="utf-8")
                        self.tree_dumped = True
                    self._update_tree_cache(blob)

        events: list[SourceEvent] = []
        for wrapper in fields.get(29, []):
            if not isinstance(wrapper, bytes):
                continue
            wrapper_fields = read_fields(wrapper)
            event_blob = first(wrapper_fields, 6)
            if not isinstance(event_blob, bytes):
                continue
            event = self._parse_event(event_blob)
            if event is not None:
                events.append(event)
        return events
