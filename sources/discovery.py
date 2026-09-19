from __future__ import annotations

import importlib
import pkgutil

import sources
from sources.base import BookmakerAdapter


def discover_adapters() -> dict[str, BookmakerAdapter]:
    adapters: dict[str, BookmakerAdapter] = {}
    for modinfo in pkgutil.iter_modules(sources.__path__):
        name = modinfo.name
        if name.startswith("_") or name in {"discovery", "base"}:
            continue
        module = importlib.import_module(f"sources.{name}")
        factory = getattr(module, "build_adapter", None)
        if factory is None:
            continue
        adapter = factory()
        if not isinstance(adapter, BookmakerAdapter):
            raise TypeError(f"sources.{name}.build_adapter() returned invalid adapter")
        if adapter.source_name in adapters:
            raise RuntimeError(f"Duplicate source_name: {adapter.source_name}")
        adapters[adapter.source_name] = adapter
    return adapters
