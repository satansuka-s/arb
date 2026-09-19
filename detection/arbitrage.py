from __future__ import annotations

import time
from collections import defaultdict

from models.domain import SourceEvent


class CrossBookArbitrageDetector:
    def __init__(
        self,
        min_odds: float,
        threshold: float = 1.0,
        low_margin_threshold: float = 1.05,
        ttl_seconds: int = 180,
        cooldown_seconds: int = 30,
    ):
        self.min_odds = min_odds
        self.threshold = threshold
        self.low_margin_threshold = low_margin_threshold
        self.ttl_seconds = ttl_seconds
        self.cooldown_seconds = cooldown_seconds
        self.quotes = defaultdict(dict)
        self.cooldowns: dict[tuple, float] = {}

    def process(self, event: SourceEvent) -> list[dict]:
        now = time.time()
        results: list[dict] = []
        if not event.canonical_event_id:
            return results

        for odd in event.odds:
            if odd.odds <= self.min_odds or not odd.outcome_key or odd.market_key.startswith("match_winner_unknown"):
                continue
            key = (event.source, odd.market_key, odd.outcome_key)
            self.quotes[event.canonical_event_id][key] = (odd.odds, now, odd.outcome_label)

        market_outcomes: dict[str, dict[str, tuple[str, float, float, str]]] = defaultdict(dict)
        for (source, market, outcome), (odds, ts, label) in self.quotes[event.canonical_event_id].items():
            if now - ts > self.ttl_seconds:
                continue
            current = market_outcomes[market].get(outcome)
            if current is None or odds > current[1]:
                market_outcomes[market][outcome] = (source, odds, ts, label)

        for market_key, outcomes in market_outcomes.items():
            required_outcomes = self._required_outcomes(market_key)
            if required_outcomes is not None:
                if len(outcomes) != required_outcomes:
                    continue
            elif len(outcomes) < 2:
                continue
            unique_sources = {value[0] for value in outcomes.values()}
            if len(unique_sources) < 2:
                continue
            inverse_sum = sum(1.0 / item[1] for item in outcomes.values() if item[1] > self.min_odds)
            signature = (
                event.canonical_event_id,
                market_key,
                tuple(sorted((outcome, value[0], round(value[1], 4)) for outcome, value in outcomes.items())),
            )
            if inverse_sum < self.threshold:
                if now - self.cooldowns.get(signature, 0) >= self.cooldown_seconds:
                    self.cooldowns[signature] = now
                    results.append({
                        "type": "arbitrage",
                        "canonical_event_id": event.canonical_event_id,
                        "sport": event.sport,
                        "market_key": market_key,
                        "outcomes": {
                            outcome: {"source": value[0], "odds": round(value[1], 4), "label": value[3]}
                            for outcome, value in outcomes.items()
                        },
                        "inverse_sum": round(inverse_sum, 6),
                        "profit_pct": round((1 - inverse_sum) * 100, 4),
                    })
            elif inverse_sum < self.low_margin_threshold:
                low_signature = ("low",) + signature
                if now - self.cooldowns.get(low_signature, 0) >= self.cooldown_seconds:
                    self.cooldowns[low_signature] = now
                    results.append({
                        "type": "low_margin",
                        "canonical_event_id": event.canonical_event_id,
                        "sport": event.sport,
                        "market_key": market_key,
                        "inverse_sum": round(inverse_sum, 6),
                        "margin_pct": round((inverse_sum - 1) * 100, 4),
                    })
        self._purge(now)
        return results

    @staticmethod
    def _required_outcomes(market_key: str) -> int | None:
        if market_key.startswith("match_winner_2way"):
            return 2
        if market_key.startswith("match_winner_3way"):
            return 3
        return None

    def _purge(self, now: float) -> None:
        for event_id, values in list(self.quotes.items()):
            for key, (_, ts, _) in list(values.items()):
                if now - ts > self.ttl_seconds:
                    del values[key]
            if not values:
                del self.quotes[event_id]

        cooldown_cutoff = now - self.cooldown_seconds
        for key, ts in list(self.cooldowns.items()):
            if ts < cooldown_cutoff:
                del self.cooldowns[key]
