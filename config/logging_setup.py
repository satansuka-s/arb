from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        structured = getattr(record, "payload", None)
        if structured is not None:
            payload["payload"] = structured
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class HumanFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return f"{self.formatTime(record, '%Y-%m-%d %H:%M:%S')} {record.levelname:<8} {record.name}: {record.getMessage()}"


def configure_logging(log_path: Path, level: str = "INFO") -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(root.level)
    console.setFormatter(HumanFormatter())

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(root.level)
    file_handler.setFormatter(JsonFormatter())

    root.addHandler(console)
    root.addHandler(file_handler)
