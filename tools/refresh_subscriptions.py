from __future__ import annotations

import argparse
import asyncio

from sources.discovery import discover_adapters


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="sporthub")
    parser.add_argument("--sport", action="append", required=True)
    args = parser.parse_args()
    adapters = discover_adapters()
    adapter = adapters.get(args.source)
    if adapter is None:
        raise SystemExit(f"Unknown source {args.source!r}; available: {', '.join(sorted(adapters))}")
    for sport in args.sport:
        ok = await adapter.refresh_subscriptions(sport)
        if not ok:
            raise SystemExit(f"Failed to refresh {args.source}/{sport}")


if __name__ == "__main__":
    asyncio.run(main())
