from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from models.domain import SourceEvent
from .arbitrage import CrossBookArbitrageDetector
from .movement import MovementDetector


logger = logging.getLogger(__name__)


class DetectionEngine:
    def __init__(self, *, min_odds: float, jump_threshold: float, jump_window: int, arb_threshold: float, low_margin_threshold: float, log_path: Path):
        self.movement = MovementDetector(min_odds, jump_threshold, jump_window)
        self.arbitrage = CrossBookArbitrageDetector(min_odds, arb_threshold, low_margin_threshold)
        self.log_path = log_path

    def process(self, event: SourceEvent) -> list[dict]:
        signals = self.movement.process(event) + self.arbitrage.process(event)
        for record in signals:
            record["ts"] = time.time()
            logger.info("detector signal", extra={"payload": record})
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return signals
