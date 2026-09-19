from detection.arbitrage import CrossBookArbitrageDetector
from models.domain import Odd, SourceEvent


def event(source: str, event_id: str, prices: tuple[float, float], market_key: str = "match_winner_2way") -> SourceEvent:
    return SourceEvent(
        source=source,
        event_id=event_id,
        external_id="",
        league_id="",
        league_name="",
        sport="Dota 2",
        start_time="2026-09-17T12:00:00Z",
        canonical_event_id="canonical-1",
        odds=[
            Odd(f"{source}-1", "m", "Winner", "main", "П1", None, prices[0], market_key=market_key, outcome_key="team:alpha"),
            Odd(f"{source}-2", "m", "Winner", "main", "П2", None, prices[1], market_key=market_key, outcome_key="team:beta"),
        ],
    )


def test_cross_book_arb():
    detector = CrossBookArbitrageDetector(min_odds=1.01, threshold=1.0, low_margin_threshold=1.05, cooldown_seconds=0)
    assert detector.process(event("book-a", "1", (2.2, 1.5))) == []
    signals = detector.process(event("book-b", "2", (1.5, 2.2)))
    assert any(signal["type"] == "arbitrage" for signal in signals)


def test_three_way_winner_requires_all_three_outcomes():
    detector = CrossBookArbitrageDetector(min_odds=1.01, threshold=1.0, cooldown_seconds=0)
    a = SourceEvent(
        source="a", event_id="1", external_id="", league_id="", league_name="", sport="football",
        start_time="2026-09-17T12:00:00Z", canonical_event_id="canonical-1",
        odds=[
            Odd("1", "m", "Winner", "main", "1", None, 3.2, market_key="match_winner_3way", outcome_key="team:alpha"),
            Odd("2", "m", "Winner", "main", "X", None, 3.5, market_key="match_winner_3way", outcome_key="draw"),
            Odd("3", "m", "Winner", "main", "2", None, 3.1, market_key="match_winner_3way", outcome_key="team:beta"),
        ],
    )
    b = SourceEvent(
        source="b", event_id="2", external_id="", league_id="", league_name="", sport="football",
        start_time="2026-09-17T12:00:00Z", canonical_event_id="canonical-1",
        odds=[
            Odd("4", "m", "Winner", "main", "1", None, 3.6, market_key="match_winner_3way", outcome_key="team:alpha"),
            Odd("5", "m", "Winner", "main", "X", None, 3.0, market_key="match_winner_3way", outcome_key="draw"),
            Odd("6", "m", "Winner", "main", "2", None, 3.0, market_key="match_winner_3way", outcome_key="team:beta"),
        ],
    )
    assert detector.process(a) == []
    signals = detector.process(b)
    assert any(signal["type"] == "arbitrage" for signal in signals)


def test_arbitrage_cooldowns_are_purged():
    detector = CrossBookArbitrageDetector(min_odds=1.01, threshold=1.0, cooldown_seconds=30)
    detector.cooldowns[("stale",)] = 0.0
    detector._purge(100.0)
    assert ("stale",) not in detector.cooldowns
