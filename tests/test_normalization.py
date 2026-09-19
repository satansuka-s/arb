from models.domain import Odd, SourceEvent, Team
from normalization.markets import normalize_event_markets
from normalization.matcher import CanonicalEventMatcher


def make_event(source: str) -> SourceEvent:
    return SourceEvent(
        source=source,
        event_id="1" if source == "a" else "999",
        external_id="",
        league_id="7",
        league_name="League",
        sport="Dota 2",
        start_time="2026-09-17T12:00:00Z",
        teams=[Team("1", "", "Team Alpha"), Team("2", "", "Team Beta")],
        odds=[
            Odd("o1", "m1", "Winner", "main", "П1", None, 2.1),
            Odd("o2", "m1", "Winner", "main", "П2", None, 1.8),
        ],
    )


def test_canonical_id_is_source_independent():
    matcher = CanonicalEventMatcher()
    a = matcher.canonicalize(make_event("a"))
    b = matcher.canonicalize(make_event("b"))
    assert a.canonical_event_id == b.canonical_event_id


def test_two_way_winner_is_separate_market():
    normalized = normalize_event_markets(make_event("a"))
    assert normalized.odds[0].outcome_key == "team:teamalpha"
    assert normalized.odds[1].outcome_key == "team:teambeta"
    assert normalized.odds[0].market_key == "match_winner_2way"


def test_three_way_winner_is_separate_market():
    event = make_event("a")
    event.odds.append(Odd("o3", "m1", "Winner", "main", "X", None, 3.8))
    normalized = normalize_event_markets(event)
    assert {odd.market_key for odd in normalized.odds} == {"match_winner_3way"}
    assert {odd.outcome_key for odd in normalized.odds} == {"team:teamalpha", "team:teambeta", "draw"}


def test_team_aliases_produce_same_outcome_key():
    event = make_event("a")
    event.odds[0].outcome_label = "П1"
    normalized = normalize_event_markets(event, team_aliases={"team alpha": "alpha esports"})
    assert normalized.odds[0].outcome_key == "team:alphaesports"


def test_normalized_reverse_team_order_still_matches():
    a = SourceEvent(
        source="a", event_id="1", external_id="", league_id="", league_name="", sport="Dota 2",
        start_time="2026-09-17T12:00:00Z", teams=[Team("1", "", "Alpha"), Team("2", "", "Beta")],
        odds=[Odd("a1", "m", "Winner", "main", "П1", None, 2.2), Odd("a2", "m", "Winner", "main", "П2", None, 1.6)],
    )
    b = SourceEvent(
        source="b", event_id="999", external_id="", league_id="", league_name="", sport="unknown",
        start_time="2026-09-17T12:15:00Z", teams=[Team("8", "", "Beta"), Team("9", "", "Alpha")],
        odds=[Odd("b1", "x", "Winner", "main", "П1", None, 2.0), Odd("b2", "x", "Winner", "main", "П2", None, 2.2)],
    )
    matcher = CanonicalEventMatcher()
    a = matcher.canonicalize(normalize_event_markets(a))
    b = matcher.canonicalize(normalize_event_markets(b))
    assert a.canonical_event_id == b.canonical_event_id
