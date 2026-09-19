from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(slots=True)
class Team:
    source_team_id: str
    external_id: str
    name: str
    logo: str = ""
    color: str = ""


@dataclass(slots=True)
class Odd:
    outcome_id: str
    market_id: str
    market_name: str
    market_group: str
    outcome_label: str
    line: float | None
    odds: float
    view_type: str = ""
    sort: int = 0
    source_market_key: str = ""
    market_key: str = ""
    outcome_key: str = ""


@dataclass(slots=True)
class SourceEvent:
    source: str
    event_id: str
    external_id: str
    league_id: str
    league_name: str
    sport: str
    start_time: str
    teams: list[Team] = field(default_factory=list)
    score: str = ""
    odds: list[Odd] = field(default_factory=list)
    canonical_event_id: str = ""
    received_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PersistEvent:
    event: SourceEvent
    changed_odds: list[Odd] = field(default_factory=list)
