from __future__ import annotations

import logging
import time
from pathlib import Path

from config.settings import Settings
from models.domain import SourceEvent
from sources.base import BookmakerWSAdapter, EventHandler
from .parser import SporthubParser
from .subscriptions import SporthubSubscriptionCollector, SPORT_URLS

logger = logging.getLogger(__name__)


class SporthubAdapter(BookmakerWSAdapter):
    source_name = "sporthub"
    display_name = "BetBoom / Sporthub"
    supported_sports = tuple(SPORT_URLS)
    ws_url = "wss://ru-ws2.sporthub.bet/api/tree_ws/v1"
    subprotocols = ("protobuf",)
    headers = {
        "Origin": "https://betboom.ru",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0",
        "Accept-Language": "en-US,en;q=0.9",
    }
    subscription_delay = 0.15
    market_aliases = {
        "main": "match_winner",
        "winner": "match_winner",
        "победитель": "match_winner",
        "match_winner": "match_winner",
    }

    def __init__(self, data_root: Path = Path("data")):
        self.data_root = data_root
        self.collector = SporthubSubscriptionCollector(data_root / "subscriptions" / self.source_name)
        self.parser = SporthubParser(
            data_root / "cache" / "league_sport.json",
            data_root / "cache" / "sport_names.json",
            data_root / "fixtures" / self.source_name / "tree_debug.hex",
        )

    async def refresh_subscriptions(self, sport: str) -> bool:
        try:
            await self.collector.collect(sport)
            return True
        except Exception as exc:
            logger.exception("subscription refresh failed: sport=%s", sport)
            return False

    def subscription_age(self, sport: str) -> float:
        path = self.collector.path(sport)
        if not path.exists():
            return float("inf")
        return time.time() - path.stat().st_mtime

    def has_subscriptions(self, sports: list[str]) -> bool:
        return all(self.collector.path(sport).exists() for sport in sports)

    def load_subscriptions(self, sports: list[str]) -> list[bytes]:
        frames: list[bytes] = []
        seen: set[bytes] = set()
        for sport in sports:
            path = self.collector.path(sport)
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    frame = bytes.fromhex(line)
                except ValueError:
                    continue
                if frame not in seen:
                    seen.add(frame)
                    frames.append(frame)
        return frames

    def decode_frame(self, payload: bytes) -> list[SourceEvent]:
        return self.parser.parse_frame(payload)

    async def stream(self, sports: list[str], settings: Settings, on_event: EventHandler, stop_event) -> str:
        import asyncio

        subscriptions = self.load_subscriptions(sports)
        if not subscriptions:
            return "no_subscriptions"

        async with await self.open_ws() as ws:
            logger.info("connected: source=%s url=%s", self.source_name, self.ws_url)
            await self.subscribe(ws, subscriptions)
            logger.info("subscriptions sent: source=%s count=%s sports=%s", self.source_name, len(subscriptions), sports)
            last_data = time.time()

            while not stop_event.is_set():
                try:
                    payload = await asyncio.wait_for(ws.recv(), timeout=settings.ping_interval)
                except asyncio.TimeoutError:
                    if time.time() - last_data > settings.idle_timeout:
                        return "idle"
                    continue
                if payload is None:
                    return "closed"
                last_data = time.time()
                if not isinstance(payload, bytes):
                    continue
                try:
                    events = self.decode_frame(payload)
                except Exception as exc:
                    logger.exception("parse error: source=%s", self.source_name)
                    continue
                for event in events:
                    event.received_at = time.time()
                    await on_event(event)
        return "closed"
