from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold a new bookmaker adapter")
    parser.add_argument("name", help="Python package name, e.g. fonbet")
    args = parser.parse_args()
    name = args.name.strip().lower().replace("-", "_")
    if not name.isidentifier() or name.startswith("_"):
        raise SystemExit("Bookmaker name must be a valid Python identifier and must not start with '_'.")

    root = Path(__file__).resolve().parents[1]
    target = root / "sources" / name
    if target.exists():
        raise SystemExit(f"Already exists: {target}")
    target.mkdir(parents=True)
    (target / "__init__.py").write_text(
        f'''from .adapter import {name.title().replace("_", "")}Adapter\n\n\ndef build_adapter():\n    return {name.title().replace("_", "")}Adapter()\n''',
        encoding="utf-8",
    )
    (target / "adapter.py").write_text(
        f'''from __future__ import annotations\n\nfrom pathlib import Path\n\nfrom config.settings import Settings\nfrom models.domain import SourceEvent\nfrom sources.base import BookmakerWSAdapter, EventHandler\n\n\nclass {name.title().replace("_", "")}Adapter(BookmakerWSAdapter):\n    source_name = "{name}"\n    display_name = "{name.title()}"\n    supported_sports = ()\n    ws_url = "wss://example.com/live"\n\n    def __init__(self, data_root: Path = Path("data")):\n        self.data_root = data_root\n\n    def decode_frame(self, payload: bytes) -> list[SourceEvent]:\n        raise NotImplementedError\n\n    async def refresh_subscriptions(self, sport: str) -> bool:\n        raise NotImplementedError\n\n    def subscription_age(self, sport: str) -> float:\n        raise NotImplementedError\n\n    def has_subscriptions(self, sports: list[str]) -> bool:\n        raise NotImplementedError\n\n    def load_subscriptions(self, sports: list[str]) -> list[bytes]:\n        raise NotImplementedError\n''',
        encoding="utf-8",
    )
    (target / "parser.py").write_text(
        '''# Implement the bookmaker-specific wire/protobuf/json parser here.\n\n''', encoding="utf-8"
    )
    print(f"[+] created {target}")
    print("[.] Discovery is automatic. Implement adapter.py, then run: python -m app.runtime")


if __name__ == "__main__":
    main()
