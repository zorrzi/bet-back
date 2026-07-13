from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.odds import Bookmaker, Market, OddsSnapshot
from src.providers.base import EventOdds
from src.services.odds_ingestion_service import OddsIngestionService
from tests.helpers import event_odds, h2h_quote, seed_match


class FakeOddsProvider:
    def __init__(self, events: list[EventOdds]) -> None:
        self.events = events

    def fetch_odds(self, sport_key: str, regions: str, markets: str) -> list[EventOdds]:
        return self.events


def test_ingest_inserts_snapshots_and_reference_data(session: Session) -> None:
    seed_match(session)
    provider = FakeOddsProvider(
        [
            event_odds(
                (
                    h2h_quote("HOME", "2.10"),
                    h2h_quote("DRAW", "3.40"),
                    h2h_quote("AWAY", "3.60"),
                )
            )
        ]
    )
    result = OddsIngestionService(session, provider).ingest_current_odds(
        "soccer_brazil_campeonato", "eu", "h2h"
    )

    assert result.events_matched == 1
    assert result.snapshots_inserted == 3
    assert session.scalar(select(func.count(OddsSnapshot.id))) == 3
    bookmaker = session.scalar(select(Bookmaker))
    assert bookmaker is not None
    assert bookmaker.is_sharp is True  # pinnacle
    market = session.scalar(select(Market))
    assert market is not None
    assert market.code == "1X2"
    assert market.n_selections == 3


def test_reingest_appends_never_updates(session: Session) -> None:
    """The golden rule (spec §4.2): every capture is a NEW row."""
    seed_match(session)
    provider = FakeOddsProvider([event_odds((h2h_quote("HOME", "2.10"),))])
    service = OddsIngestionService(session, provider)
    first = service.ingest_current_odds("soccer_brazil_campeonato", "eu", "h2h")

    provider.events = [event_odds((h2h_quote("HOME", "2.25"),))]  # price moved
    second = service.ingest_current_odds("soccer_brazil_campeonato", "eu", "h2h")

    snapshots = list(session.scalars(select(OddsSnapshot).order_by(OddsSnapshot.id)))
    assert len(snapshots) == 2  # appended, not overwritten
    assert str(snapshots[0].price_decimal) != str(snapshots[1].price_decimal)
    assert second.captured_at >= first.captured_at
    # reference data was reused, not duplicated
    assert session.scalar(select(func.count(Bookmaker.id))) == 1
    assert session.scalar(select(func.count(Market.id))) == 1


def test_event_matches_despite_accents_and_case(session: Session) -> None:
    """The Odds API spells names without accents ('Sao Paulo'); matching must
    survive accent/case differences or snapshots are silently lost."""
    seed_match(session)  # stores 'Flamengo' / 'Palmeiras'
    provider = FakeOddsProvider(
        [event_odds((h2h_quote("HOME", "2.10"),), home="FLAMENGO", away="palmeiras ")]
    )
    result = OddsIngestionService(session, provider).ingest_current_odds(
        "soccer_brazil_campeonato", "eu", "h2h"
    )

    assert result.events_matched == 1
    assert result.snapshots_inserted == 1


def test_unmatched_event_is_skipped_and_counted_without_autocreate(
    session: Session,
) -> None:
    seed_match(session)
    provider = FakeOddsProvider(
        [event_odds((h2h_quote("HOME", "2.10"),), home="Unknown FC", away="Mystery United")]
    )
    result = OddsIngestionService(session, provider).ingest_current_odds(
        "soccer_brazil_campeonato", "eu", "h2h"
    )

    assert result.events_unmatched == 1
    assert result.snapshots_inserted == 0
    assert session.scalar(select(func.count(OddsSnapshot.id))) == 0


def test_autocreate_builds_match_from_odds_event(session: Session) -> None:
    """ADR-0004: with no fixtures provider for the current season, the odds
    event itself becomes the match."""
    from src.models.competition import League, Team
    from src.models.match import Match

    provider = FakeOddsProvider(
        [event_odds((h2h_quote("HOME", "2.10"), h2h_quote("AWAY", "3.40")))]
    )
    service = OddsIngestionService(session, provider, autocreate_matches=True, season="2026")
    result = service.ingest_current_odds("soccer_brazil_campeonato", "eu", "h2h")

    assert result.matches_autocreated == 1
    assert result.snapshots_inserted == 2
    match = session.scalar(select(Match))
    assert match is not None
    assert match.provider_id == "toa:abc123"
    league = session.scalar(select(League))
    assert league is not None
    assert league.provider_id == "toa:soccer_brazil_campeonato"
    assert league.season == "2026"
    assert session.scalar(select(func.count(Team.id))) == 2

    # re-run: same event resolves by provider_id, nothing new is created
    second = service.ingest_current_odds("soccer_brazil_campeonato", "eu", "h2h")
    assert second.matches_autocreated == 0
    assert session.scalar(select(func.count(Match.id))) == 1
    assert session.scalar(select(func.count(OddsSnapshot.id))) == 4  # append-only
