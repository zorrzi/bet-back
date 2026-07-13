from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.competition import League, Team
from src.models.match import Match, MatchStatus
from src.providers.base import FixtureData
from src.services.fixture_ingestion_service import FixtureIngestionService


def _fixture(
    status: str = MatchStatus.SCHEDULED,
    home_goals: int | None = None,
    away_goals: int | None = None,
) -> FixtureData:
    return FixtureData(
        provider_id="1234",
        league_provider_id="71",
        league_name="Serie A",
        league_country="Brazil",
        season="2026",
        home_team_provider_id="127",
        home_team_name="Flamengo",
        away_team_provider_id="121",
        away_team_name="Palmeiras",
        kickoff_utc=datetime(2026, 7, 20, 16, 0, tzinfo=UTC),
        status=status,
        home_goals=home_goals,
        away_goals=away_goals,
    )


class FakeFixtureProvider:
    def __init__(self, fixtures: list[FixtureData]) -> None:
        self.fixtures = fixtures

    def fetch_fixtures(self, league_provider_id: str, season: str) -> list[FixtureData]:
        return self.fixtures


def test_ingest_creates_league_teams_and_match(session: Session) -> None:
    service = FixtureIngestionService(session, FakeFixtureProvider([_fixture()]))
    result = service.ingest_league_season("71", "2026")

    assert result.fixtures_seen == 1
    assert result.matches_created == 1
    assert session.scalar(select(func.count(League.id))) == 1
    assert session.scalar(select(func.count(Team.id))) == 2
    match = session.scalar(select(Match))
    assert match is not None
    assert match.status == MatchStatus.SCHEDULED
    assert match.provider_id == "1234"


def test_reingest_is_idempotent_and_counts_no_phantom_updates(session: Session) -> None:
    provider = FakeFixtureProvider([_fixture()])
    service = FixtureIngestionService(session, provider)
    service.ingest_league_season("71", "2026")
    result = service.ingest_league_season("71", "2026")

    assert result.matches_created == 0
    assert result.matches_updated == 0  # nothing actually changed
    assert session.scalar(select(func.count(Match.id))) == 1
    assert session.scalar(select(func.count(Team.id))) == 2


def test_reingest_updates_result_after_full_time(session: Session) -> None:
    service = FixtureIngestionService(session, FakeFixtureProvider([_fixture()]))
    service.ingest_league_season("71", "2026")

    finished = FixtureIngestionService(
        session,
        FakeFixtureProvider([_fixture(MatchStatus.FINISHED, home_goals=2, away_goals=1)]),
    )
    finished.ingest_league_season("71", "2026")

    match = session.scalar(select(Match))
    assert match is not None
    assert match.status == MatchStatus.FINISHED
    assert (match.home_goals, match.away_goals) == (2, 1)


def test_provider_null_goals_never_erase_a_stored_result(session: Session) -> None:
    """A transient feed glitch (finished match reported with null goals) must
    not corrupt settled results."""
    service = FixtureIngestionService(
        session,
        FakeFixtureProvider([_fixture(MatchStatus.FINISHED, home_goals=2, away_goals=1)]),
    )
    service.ingest_league_season("71", "2026")

    glitched = FixtureIngestionService(
        session, FakeFixtureProvider([_fixture(MatchStatus.FINISHED)])
    )
    glitched.ingest_league_season("71", "2026")

    match = session.scalar(select(Match))
    assert match is not None
    assert (match.home_goals, match.away_goals) == (2, 1)


def test_kickoff_reschedule_clears_stale_closing_flags(session: Session) -> None:
    from datetime import timedelta
    from decimal import Decimal

    from src.models.odds import Bookmaker, Market, OddsSnapshot

    service = FixtureIngestionService(session, FakeFixtureProvider([_fixture()]))
    service.ingest_league_season("71", "2026")
    match = session.scalar(select(Match))
    assert match is not None

    bookmaker = Bookmaker(provider_id="pinnacle", name="Pinnacle", is_sharp=True)
    market = Market(code="1X2", name="Match Result", category="match_result", n_selections=3)
    session.add_all([bookmaker, market])
    session.flush()
    session.add(
        OddsSnapshot(
            match_id=match.id,
            bookmaker_id=bookmaker.id,
            market_id=market.id,
            selection="HOME",
            price_decimal=Decimal("2.10"),
            captured_at=match.kickoff_utc - timedelta(hours=1),
            is_closing=True,
        )
    )
    session.commit()

    moved = _fixture()
    rescheduled = FixtureData(
        **{**moved.__dict__, "kickoff_utc": moved.kickoff_utc + timedelta(days=1)}
    )
    FixtureIngestionService(session, FakeFixtureProvider([rescheduled])).ingest_league_season(
        "71", "2026"
    )

    snapshot = session.scalar(select(OddsSnapshot))
    assert snapshot is not None
    assert snapshot.is_closing is False  # stale closing flag was cleared
