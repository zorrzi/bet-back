"""Provider abstractions (spec §3).

Every external data source is hidden behind these interfaces so a provider
swap never touches the core. Implementations normalize raw payloads into
these DTOs; nothing outside src/providers may depend on a provider's wire
format.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class FixtureData:
    """One fixture as reported by the fixtures provider, normalized."""

    provider_id: str
    league_provider_id: str
    league_name: str
    league_country: str | None
    season: str
    home_team_provider_id: str
    home_team_name: str
    away_team_provider_id: str
    away_team_name: str
    kickoff_utc: datetime
    status: str  # normalized to MatchStatus values
    home_goals: int | None = None
    away_goals: int | None = None


@dataclass(frozen=True)
class OddsQuote:
    """One priced selection inside one market at one bookmaker."""

    bookmaker_provider_id: str
    bookmaker_name: str
    market_code: str  # normalized: '1X2', 'OU_2_5', ...
    market_name: str
    market_category: str
    n_selections: int
    selection: str  # 'HOME' | 'DRAW' | 'AWAY' | 'OVER' | 'UNDER' | ...
    price_decimal: Decimal
    line: Decimal | None = None


@dataclass(frozen=True)
class EventOdds:
    """All quotes captured for one event in one provider call.

    Odds providers use their own event ids and team names; the ingestion
    layer resolves them onto our matches (see match_resolver).
    """

    event_provider_id: str
    home_team_name: str
    away_team_name: str
    kickoff_utc: datetime
    quotes: tuple[OddsQuote, ...] = field(default_factory=tuple)


class FixtureProvider(Protocol):
    def fetch_fixtures(self, league_provider_id: str, season: str) -> list[FixtureData]:
        """All fixtures (past and future) for one league season."""
        ...


class OddsProvider(Protocol):
    def fetch_odds(self, sport_key: str, regions: str, markets: str) -> list[EventOdds]:
        """Current odds for all upcoming events of one sport/league."""
        ...
