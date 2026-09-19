from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import websockets

from config.settings import Settings
from models.domain import SourceEvent

EventHandler = Callable[[SourceEvent], Awaitable[None]]


class BookmakerAdapter(ABC):
    source_name: str
    display_name: str
    supported_sports: tuple[str, ...] = ()

    @abstractmethod
    async def stream(self, sports: list[str], settings: Settings, on_event: EventHandler, stop_event: Any) -> str:
        """Run a source stream until reconnect/stop is requested."""

    @abstractmethod
    async def refresh_subscriptions(self, sport: str) -> bool:
        """Refresh source-specific subscription frames for one sport."""

    @abstractmethod
    def subscription_age(self, sport: str) -> float:
        """Seconds since subscription file was modified."""

    @abstractmethod
    def has_subscriptions(self, sports: list[str]) -> bool:
        """Return True when every requested sport has a usable subscription."""

    @abstractmethod
    def load_subscriptions(self, sports: list[str]) -> list[bytes]:
        """Load encoded subscription frames."""


class BookmakerWSAdapter(BookmakerAdapter):
    ws_url: str = ""
    subprotocols: tuple[str, ...] = ()
    headers: dict[str, str] = {}
    subscription_delay: float = 0.0
    max_size: int = 20 * 1024 * 1024
    market_aliases: dict[str, str] = {}

    def decode_frame(self, payload: bytes) -> list[SourceEvent]:
        raise NotImplementedError

    async def open_ws(self):
        return websockets.connect(
            self.ws_url,
            subprotocols=list(self.subprotocols),
            additional_headers=self.headers or None,
            max_size=self.max_size,
            open_timeout=15,
            ping_interval=None,
            ping_timeout=20,
        )

    async def subscribe(self, ws, subscriptions: list[bytes]) -> None:
        import asyncio
        for frame in subscriptions:
            await ws.send(frame)
            if self.subscription_delay:
                await asyncio.sleep(self.subscription_delay)
