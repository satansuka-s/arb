from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

SPORT_URLS = {
    "dota": "https://betboom.ru/esport/live/dota-2",
    "cs2": "https://betboom.ru/esport/live/counter-strike-2",
    "lol": "https://betboom.ru/esport/live/league-of-legends",
    "valorant": "https://betboom.ru/esport/live/valorant",
}

DEFAULT_SECONDS = 25


class SporthubSubscriptionCollector:
    def __init__(self, root: Path = Path("data/subscriptions/sporthub"), collect_seconds: int = DEFAULT_SECONDS):
        self.root = root
        self.collect_seconds = collect_seconds

    @staticmethod
    def validate_sport(sport: str) -> str:
        sport = sport.lower().strip()
        if sport not in SPORT_URLS:
            raise ValueError(f"Unknown sport {sport!r}. Available: {', '.join(SPORT_URLS)}")
        return sport

    def path(self, sport: str) -> Path:
        return self.root / f"{self.validate_sport(sport)}.txt"

    async def collect(self, sport: str) -> Path:
        sport = self.validate_sport(sport)
        from playwright.async_api import async_playwright

        url = SPORT_URLS[sport]
        self.root.mkdir(parents=True, exist_ok=True)
        collected: list[str] = []

        async with async_playwright() as p:
            browser = None
            for channel in ("chrome", "msedge", None):
                try:
                    kwargs = {"headless": False}
                    if channel:
                        kwargs["channel"] = channel
                    browser = await p.chromium.launch(**kwargs)
                    break
                except Exception:
                    continue
            if browser is None:
                raise RuntimeError("Unable to launch Chromium/Chrome/Edge")

            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page = await context.new_page()

            def on_websocket(ws):
                if "sporthub" not in ws.url:
                    return
                logger.info("subscription collector connected: url=%s", ws.url)

                def on_frame_sent(payload):
                    try:
                        value = payload.hex() if isinstance(payload, bytes) else payload.encode("utf-8").hex()
                    except Exception:
                        return
                    collected.append(value)

                ws.on("framesent", on_frame_sent)

            page.on("websocket", on_websocket)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                logger.info("collecting subscriptions: sport=%s duration=%ss", sport, self.collect_seconds)
                await asyncio.sleep(self.collect_seconds)
            finally:
                await browser.close()

        if not collected:
            raise RuntimeError(f"No sporthub subscription frames collected for {sport}")

        seen: set[str] = set()
        unique: list[str] = []
        for frame in collected:
            if frame not in seen:
                seen.add(frame)
                unique.append(frame)

        path = self.path(sport)
        path.write_text("\n".join(unique) + "\n", encoding="utf-8")
        logger.info("saved subscription frames: count=%s path=%s", len(unique), path)
        return path

    async def collect_many(self, sports: Iterable[str]) -> list[Path]:
        result = []
        for sport in sports:
            result.append(await self.collect(sport))
        return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport", default="dota", choices=sorted(SPORT_URLS))
    parser.add_argument("--seconds", type=int, default=DEFAULT_SECONDS)
    args = parser.parse_args()
    asyncio.run(SporthubSubscriptionCollector(collect_seconds=args.seconds).collect(args.sport))


if __name__ == "__main__":
    main()
