from __future__ import annotations

import time

from models.domain import SourceEvent


class MovementDetector:
    def __init__(self, min_odds: float, jump_threshold: float, window_seconds: int, cooldown_seconds: int = 30):
        self.min_odds = min_odds
        self.jump_threshold = jump_threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self.last: dict[tuple[str, str, str, str], tuple[float, float]] = {}
        self.cooldowns: dict[tuple[str, str, str], float] = {}
        self._purge_interval = max(30, min(window_seconds, cooldown_seconds or window_seconds))
        self._next_purge = 0.0

    def process(self, event: SourceEvent) -> list[dict]:
        now = time.time()
        result = []
        for odd in event.odds:
            if odd.odds <= self.min_odds or not odd.outcome_key:
                continue
            key = (event.source, event.canonical_event_id, odd.market_key, odd.outcome_key)
            previous = self.last.get(key)
            self.last[key] = (odd.odds, now)
            if previous is None:
                continue
            previous_odds, previous_ts = previous
            if now - previous_ts > self.window_seconds or previous_odds <= self.min_odds:
                continue
            change = (odd.odds - previous_odds) / previous_odds
            if abs(change) <= self.jump_threshold:
                continue
            cooldown_key = (event.source, event.canonical_event_id, odd.outcome_key)
            if now - self.cooldowns.get(cooldown_key, 0) < self.cooldown_seconds:
                continue
            self.cooldowns[cooldown_key] = now
            result.append({
                "type": "jump",
                "source": event.source,
                "canonical_event_id": event.canonical_event_id,
                "event_id": event.event_id,
                "sport": event.sport,
                "market_key": odd.market_key,
                "outcome_key": odd.outcome_key,
                "outcome_label": odd.outcome_label,
                "from": round(previous_odds, 4),
                "to": round(odd.odds, 4),
                "change_pct": round(change * 100, 2),
            })

        if now >= self._next_purge:
            self._purge(now)
            self._next_purge = now + self._purge_interval
        return result

    def _purge(self, now: float) -> None:
        last_cutoff = now - max(self.window_seconds, self.cooldown_seconds)
        for key, (_, ts) in list(self.last.items()):
            if ts < last_cutoff:
                del self.last[key]

        cooldown_cutoff = now - self.cooldown_seconds
        for key, ts in list(self.cooldowns.items()):
            if ts < cooldown_cutoff:
                del self.cooldowns[key]
