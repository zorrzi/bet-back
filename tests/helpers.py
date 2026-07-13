"""Small factories shared by tests."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from src.models.competition import League, Team
from src.models.match import Match, MatchStatus
from src.providers.base import EventOdds, OddsQuote

KICKOFF = datetime(2026, 7, 20, 16, 0, tzinfo=UTC)


def seed_match(session: Session, kickoff: datetime = KICKOFF) -> Match:
    league = League(provider_id="71", season="2026", name="Serie A", country="Brazil")
    session.add(league)
    session.flush()
    home = Team(provider_id="127", name="Flamengo", league_id=league.id)
    away = Team(provider_id="121", name="Palmeiras", league_id=league.id)
    session.add_all([home, away])
    session.flush()
    match = Match(
        provider_id="1234",
        league_id=league.id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_utc=kickoff,
        status=MatchStatus.SCHEDULED,
    )
    session.add(match)
    session.commit()
    return match


def h2h_quote(selection: str, price: str, bookmaker: str = "pinnacle") -> OddsQuote:
    return OddsQuote(
        bookmaker_provider_id=bookmaker,
        bookmaker_name=bookmaker.title(),
        market_code="1X2",
        market_name="Match Result",
        market_category="match_result",
        n_selections=3,
        selection=selection,
        price_decimal=Decimal(price),
    )


def event_odds(
    quotes: tuple[OddsQuote, ...],
    home: str = "Flamengo",
    away: str = "Palmeiras",
    kickoff: datetime = KICKOFF,
) -> EventOdds:
    return EventOdds(
        event_provider_id="abc123",
        home_team_name=home,
        away_team_name=away,
        kickoff_utc=kickoff,
        quotes=quotes,
    )
