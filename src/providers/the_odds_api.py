"""The Odds API (the-odds-api.com) odds provider.

Docs: https://the-odds-api.com/liveapi/guides/v4/
Auth: `apiKey` query param. Each call returns upcoming events for one sport
with per-bookmaker markets. We normalize:

- ``h2h``    -> market '1X2' (HOME/DRAW/AWAY, 3 selections)
- ``totals`` -> market 'OU_<line>' (OVER/UNDER, 2 selections), line kept
- ``spreads``-> market 'AH_<line>' (HOME/AWAY, 2 selections), line = home handicap

Every quote of every capture becomes a NEW odds_snapshots row downstream —
append-only, never updated (spec §4.2).
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from src.config.settings import Settings
from src.models.odds import MarketCategory
from src.providers.base import EventOdds, OddsQuote, ScoreData
from src.providers.http import get_json

logger = logging.getLogger(__name__)


def format_line(line: Decimal) -> str:
    """2.5 -> '2_5'; -0.5 -> '-0_5' (market codes per spec §4.2)."""
    text = format(line.normalize(), "f")
    return text.replace(".", "_")


class TheOddsApiProvider:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.the_odds_api_base_url.rstrip("/")
        self._api_key = settings.the_odds_api_key
        self._timeout = settings.provider_timeout_seconds

    def fetch_odds(self, sport_key: str, regions: str, markets: str) -> list[EventOdds]:
        payload = get_json(
            f"{self._base_url}/sports/{sport_key}/odds",
            params={
                "apiKey": self._api_key,
                "regions": regions,
                "markets": markets,
                "oddsFormat": "decimal",
            },
            timeout=self._timeout,
        )
        events = [event for raw in payload if (event := self._parse_event(raw)) is not None]
        logger.info(
            "the_odds_api.odds_fetched",
            extra={
                "sport_key": sport_key,
                "events": len(events),
                "quotes": sum(len(e.quotes) for e in events),
            },
        )
        return events

    def fetch_scores(self, sport_key: str, days_from: int) -> list[ScoreData]:
        """Scores for events that started up to `days_from` days ago (costs
        2 credits per call on The Odds API)."""
        payload = get_json(
            f"{self._base_url}/sports/{sport_key}/scores",
            params={"apiKey": self._api_key, "daysFrom": days_from},
            timeout=self._timeout,
        )
        scores = [score for raw in payload if (score := self._parse_score(raw)) is not None]
        logger.info(
            "the_odds_api.scores_fetched",
            extra={
                "sport_key": sport_key,
                "events": len(scores),
                "completed": sum(1 for s in scores if s.completed),
            },
        )
        return scores

    def _parse_score(self, raw: dict[str, Any]) -> ScoreData | None:
        try:
            home_team = raw["home_team"]
            away_team = raw["away_team"]
            by_team: dict[str, int] = {}
            for entry in raw.get("scores") or []:
                by_team[entry["name"]] = int(entry["score"])
            return ScoreData(
                event_provider_id=str(raw["id"]),
                home_team_name=home_team,
                away_team_name=away_team,
                kickoff_utc=datetime.fromisoformat(raw["commence_time"]).astimezone(UTC),
                completed=bool(raw.get("completed")),
                home_score=by_team.get(home_team),
                away_score=by_team.get(away_team),
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("the_odds_api.score_parse_failed", extra={"raw": str(raw)[:200]})
            return None

    def _parse_event(self, raw: dict[str, Any]) -> EventOdds | None:
        try:
            home_team = raw["home_team"]
            away_team = raw["away_team"]
            kickoff = datetime.fromisoformat(raw["commence_time"]).astimezone(UTC)
            quotes: list[OddsQuote] = []
            for bookmaker in raw.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    quotes.extend(self._parse_market(bookmaker, market, home_team, away_team))
            return EventOdds(
                event_provider_id=str(raw["id"]),
                home_team_name=home_team,
                away_team_name=away_team,
                kickoff_utc=kickoff,
                quotes=tuple(quotes),
            )
        except (KeyError, TypeError, ValueError, InvalidOperation):
            # InvalidOperation is an ArithmeticError (a null/garbage price),
            # not a ValueError — without it one bad price kills the whole run
            logger.warning("the_odds_api.event_parse_failed", extra={"raw": str(raw)[:200]})
            return None

    def _parse_market(
        self,
        bookmaker: dict[str, Any],
        market: dict[str, Any],
        home_team: str,
        away_team: str,
    ) -> list[OddsQuote]:
        market_key = market.get("key")
        quotes: list[OddsQuote] = []
        for outcome in market.get("outcomes", []):
            price = Decimal(str(outcome["price"]))
            point = outcome.get("point")
            line = Decimal(str(point)) if point is not None else None
            normalized = self._normalize_outcome(
                market_key, outcome.get("name", ""), line, home_team, away_team
            )
            if normalized is None:
                continue
            market_code, market_name, category, n_selections, selection, norm_line = normalized
            quotes.append(
                OddsQuote(
                    bookmaker_provider_id=bookmaker["key"],
                    bookmaker_name=bookmaker.get("title", bookmaker["key"]),
                    market_code=market_code,
                    market_name=market_name,
                    market_category=category,
                    n_selections=n_selections,
                    selection=selection,
                    price_decimal=price,
                    line=norm_line,
                )
            )
        return quotes

    def _normalize_outcome(
        self,
        market_key: str | None,
        outcome_name: str,
        line: Decimal | None,
        home_team: str,
        away_team: str,
    ) -> tuple[str, str, str, int, str, Decimal | None] | None:
        """Returns (market_code, market_name, category, n_selections,
        selection, normalized_line)."""
        if market_key == "h2h":
            selection_map = {home_team: "HOME", away_team: "AWAY", "Draw": "DRAW"}
            selection = selection_map.get(outcome_name)
            if selection is None:
                return None
            return "1X2", "Match Result", MarketCategory.MATCH_RESULT, 3, selection, None
        if market_key == "totals" and line is not None:
            if outcome_name not in ("Over", "Under"):
                return None
            code = f"OU_{format_line(line)}"
            return (
                code,
                f"Over/Under {line}",
                MarketCategory.TOTALS,
                2,
                outcome_name.upper(),
                line,
            )
        if market_key == "spreads" and line is not None:
            selection_map = {home_team: "HOME", away_team: "AWAY"}
            selection = selection_map.get(outcome_name)
            if selection is None:
                return None
            # each outcome carries its own point (home -0.5 / away +0.5);
            # the market is ONE — code and stored line are both keyed by the
            # HOME handicap so (market, line) is consistent across selections.
            home_line = line if selection == "HOME" else -line
            if home_line == 0:
                home_line = Decimal("0")  # kill Decimal('-0'): 'AH_-0' != 'AH_0'
            code = f"AH_{format_line(home_line)}"
            return (
                code,
                f"Asian Handicap {home_line}",
                MarketCategory.HANDICAP,
                2,
                selection,
                home_line,
            )
        return None
