from __future__ import annotations

from typing import Protocol, TypeAlias

from models.domain import Odd, SourceEvent

EventKey: TypeAlias = tuple[str, str]
ChangedOdds: TypeAlias = dict[EventKey, list[Odd]]


class Repository(Protocol):
    def init(self) -> None: ...
    def save_batch(self, events: list[SourceEvent], changed_odds: ChangedOdds) -> None: ...
    def close(self) -> None: ...
