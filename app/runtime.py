from __future__ import annotations

import asyncio
import logging
import signal
import time
from collections import defaultdict

from config.logging_setup import configure_logging
from config.settings import Settings, load_settings
from detection.engine import DetectionEngine
from models.domain import Odd, SourceEvent
from normalization.markets import normalize_event_markets
from normalization.matcher import CanonicalEventMatcher
from realtime.state import RealtimeState
from sources.base import BookmakerAdapter
from sources.discovery import discover_adapters
from storage.sqlite import SQLiteRepository


logger = logging.getLogger(__name__)


class BatchPersister:
    def __init__(self, repository: SQLiteRepository, batch_size: int, interval: float):
        self.repository = repository
        self.batch_size = batch_size
        self.interval = interval
        self.queue: asyncio.Queue[tuple[SourceEvent, list[Odd]]] = asyncio.Queue(maxsize=batch_size * 20)
        self.task: asyncio.Task | None = None
        self.stop = False

    async def put(self, event: SourceEvent, changed: list[Odd]) -> None:
        await self.queue.put((event, changed))
        if self.queue.qsize() >= self.batch_size:
            await asyncio.sleep(0)

    async def run(self) -> None:
        while not self.stop or not self.queue.empty():
            batch: list[SourceEvent] = []
            changed: dict[tuple[str, str], list[Odd]] = defaultdict(list)
            deadline = asyncio.get_running_loop().time() + self.interval
            while len(batch) < self.batch_size:
                timeout = max(0.0, deadline - asyncio.get_running_loop().time())
                try:
                    event, odds = await asyncio.wait_for(self.queue.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    break
                batch.append(event)
                changed[(event.source, event.event_id)].extend(odds)
            if batch:
                latest: dict[tuple[str, str], SourceEvent] = {}
                for event in batch:
                    latest[(event.source, event.event_id)] = event
                try:
                    self.repository.save_batch(list(latest.values()), changed)
                except Exception:
                    logger.exception("storage batch failed")
            elif self.stop:
                break

    async def close(self) -> None:
        self.stop = True
        if self.task:
            await self.task


class PlatformRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.adapters = discover_adapters()
        self.matcher = CanonicalEventMatcher(settings.db_path.parent / "cache" / "team_aliases.json")
        self.repository = SQLiteRepository(settings.db_path)
        self.state = RealtimeState(settings.snapshot_path, settings.state_ttl)
        self.detectors = DetectionEngine(
            min_odds=settings.min_odds,
            jump_threshold=settings.jump_threshold,
            jump_window=settings.jump_window,
            arb_threshold=settings.arbitrage_threshold,
            low_margin_threshold=settings.low_margin_threshold,
            log_path=settings.arbitrage_log_path,
        )
        self.persister = BatchPersister(self.repository, settings.batch_size, settings.batch_interval)
        self.stop_event = asyncio.Event()
        self.last_snapshot_flush = time.monotonic()

    def request_stop(self) -> None:
        if not self.stop_event.is_set():
            logger.info("shutdown requested")
            self.stop_event.set()

    async def on_event(self, event: SourceEvent) -> None:
        adapter = self.adapters.get(event.source)
        aliases = adapter.market_aliases if adapter is not None else {}
        event = normalize_event_markets(event, aliases, self.matcher.aliases)
        event = self.matcher.canonicalize(event)
        changed = self.state.apply(event)
        self.detectors.process(event)
        await self.persister.put(event, changed)

        now = time.monotonic()
        if self.state.dirty and now - self.last_snapshot_flush >= 1.0:
            self.state.dump_snapshot()
            self.state.purge()
            self.last_snapshot_flush = now

    async def _ensure_subscriptions(self, adapter: BookmakerAdapter, sports: list[str]) -> None:
        for sport in sports:
            if sport not in adapter.supported_sports:
                logger.warning("sport not supported: source=%s sport=%s", adapter.source_name, sport)
                continue

            loaded = bool(adapter.load_subscriptions([sport]))
            stale = adapter.subscription_age(sport) > self.settings.subscriptions_max_age
            if loaded and not stale:
                continue

            if stale:
                logger.info("refreshing stale subscriptions: source=%s sport=%s", adapter.source_name, sport)
            else:
                logger.info("missing subscriptions: source=%s sport=%s", adapter.source_name, sport)

            refreshed = await adapter.refresh_subscriptions(sport)
            if not refreshed and loaded:
                logger.warning("using existing subscriptions after refresh failure: source=%s sport=%s", adapter.source_name, sport)
            elif not refreshed:
                logger.error("no usable subscriptions: source=%s sport=%s", adapter.source_name, sport)

    async def run_adapter(self, adapter: BookmakerAdapter) -> None:
        sports = [sport for sport in self.settings.sports if not adapter.supported_sports or sport in adapter.supported_sports]
        if not sports:
            logger.info("no requested sports enabled: source=%s", adapter.source_name)
            return
        delay = self.settings.reconnect_base
        while not self.stop_event.is_set():
            await self._ensure_subscriptions(adapter, sports)
            try:
                reason = await adapter.stream(sports, self.settings, self.on_event, self.stop_event)
                delay = self.settings.reconnect_base
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("stream error: source=%s", adapter.source_name)
                reason = "error"
            if self.stop_event.is_set():
                break
            if reason == "idle":
                for sport in sports:
                    await adapter.refresh_subscriptions(sport)
            logger.info("reconnecting: source=%s delay=%ss reason=%s", adapter.source_name, delay, reason)
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
            delay = min(delay * 2, self.settings.reconnect_max)

    async def run(self) -> None:
        self.repository.init()
        self.persister.task = asyncio.create_task(self.persister.run())
        requested = self.settings.sources
        missing = [name for name in requested if name not in self.adapters]
        if missing:
            await self.persister.close()
            self.repository.close()
            raise RuntimeError(f"Unknown source(s): {', '.join(missing)}. Discovered: {', '.join(sorted(self.adapters))}")

        tasks = [asyncio.create_task(self.run_adapter(self.adapters[name])) for name in requested]
        try:
            await self.stop_event.wait()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self.persister.close()
            self.state.dump_snapshot()
            self.repository.close()


def run_cli() -> None:
    settings = load_settings()
    configure_logging(settings.log_path, settings.log_level)
    runtime = PlatformRuntime(settings)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, runtime.request_stop)
            except (NotImplementedError, RuntimeError):
                signal.signal(sig, lambda *_: runtime.request_stop())
        loop.run_until_complete(runtime.run())
    finally:
        loop.close()
