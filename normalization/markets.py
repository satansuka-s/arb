from __future__ import annotations

from dataclasses import replace

from models.domain import Odd, SourceEvent
from .names import compact_name, normalize_name


_HOME = {"п1", "p1", "1", "home", "team1", "first"}
_AWAY = {"п2", "p2", "2", "away", "team2", "second"}
_DRAW = {"x", "х", "draw", "ничья"}


def _line_key(line: float | None) -> str:
    return "" if line is None else f"{line:.3f}"


def _team_key(name: str, team_aliases: dict[str, str]) -> str:
    normalized = normalize_name(name)
    canonical = team_aliases.get(normalized, normalized)
    return compact_name(canonical)


def _outcome_key(odd: Odd, event: SourceEvent, team_aliases: dict[str, str]) -> str:
    label = normalize_name(odd.outcome_label)
    compact = compact_name(odd.outcome_label)
    teams = event.teams[:2]

    if compact in _DRAW or label in _DRAW:
        return "draw"

    if teams:
        # Never use source-specific P1/P2 as the cross-book identity. Bind the
        # outcome to the actual team name so books may swap home/away ordering.
        if compact in _HOME or label in _HOME:
            return f"team:{_team_key(teams[0].name, team_aliases)}"
        if compact in _AWAY or label in _AWAY:
            if len(teams) > 1:
                return f"team:{_team_key(teams[1].name, team_aliases)}"
        if compact == compact_name(teams[0].name):
            return f"team:{_team_key(teams[0].name, team_aliases)}"
        if len(teams) > 1 and compact == compact_name(teams[1].name):
            return f"team:{_team_key(teams[1].name, team_aliases)}"

    return compact or normalize_name(odd.outcome_id)


def _classify_market(raw: str) -> str:
    text = normalize_name(raw)
    if any(token in text for token in ("match winner", "winner", "победитель", "исход", "1x2", "moneyline", "main")):
        return "match_winner"
    if any(token in text for token in ("total", "тотал", "over under", "больше меньше")):
        return "total"
    if any(token in text for token in ("handicap", "фора", "spread")):
        return "handicap"
    return text.replace(" ", "_") or "unknown"


def _market_base(odd: Odd, aliases: dict[str, str]) -> str:
    raw = odd.source_market_key or odd.market_group or odd.market_name or odd.market_id or "unknown"
    normalized_raw = normalize_name(raw)
    canonical = aliases.get(normalized_raw) or _classify_market(raw)
    return normalize_name(canonical).replace(" ", "_") or "unknown"


def normalize_event_markets(
    event: SourceEvent,
    market_aliases: dict[str, str] | None = None,
    team_aliases: dict[str, str] | None = None,
) -> SourceEvent:
    aliases = {normalize_name(k): normalize_name(v).replace(" ", "_") for k, v in (market_aliases or {}).items()}
    team_aliases = {normalize_name(k): normalize_name(v) for k, v in (team_aliases or {}).items()}

    preliminary: list[tuple[Odd, str, str, str]] = []
    for odd in event.odds:
        base = _market_base(odd, aliases)
        line = _line_key(odd.line)
        outcome_key = _outcome_key(odd, event, team_aliases)
        raw_market = normalize_name(odd.source_market_key or odd.market_group or odd.market_name or odd.market_id or "unknown")
        preliminary.append((odd, base, line, outcome_key + "\x00" + raw_market))

    # Infer the arity of winner markets from the complete event snapshot. A
    # two-way winner and a 1X2 winner are different market semantics and must
    # never share an arbitrage bucket.
    groups: dict[tuple[str, str, str], set[str]] = {}
    for _, base, line, packed in preliminary:
        outcome_key, raw_market = packed.split("\x00", 1)
        groups.setdefault((base, line, raw_market), set()).add(outcome_key)

    normalized_odds: list[Odd] = []
    for odd, base, line, outcome_key_packed in preliminary:
        outcome_key, raw_market = outcome_key_packed.split("\x00", 1)
        market_base = base
        if base == "match_winner":
            outcome_count = len(groups[(base, line, raw_market)])
            if outcome_count == 2:
                market_base = "match_winner_2way"
            elif outcome_count == 3:
                market_base = "match_winner_3way"
            else:
                market_base = "match_winner_unknown"
        market_key = f"{market_base}:{line}" if line else market_base
        normalized_odds.append(replace(odd, market_key=market_key, outcome_key=outcome_key))

    return replace(event, odds=normalized_odds)
