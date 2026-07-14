from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.competition import Team
from src.models.match import Match, MatchStatus
from src.models.odds import OddsSnapshot
from src.providers.football_data_co_uk import HistoricalMatch
from src.services.history_import_service import HistoryImportService
from tests.helpers import seed_match


def _row(
    *,
    home: str = "Corinthians",
    away: str = "Gremio",
    season: str = "2024",
    kickoff: datetime = datetime(2024, 5, 12, 19, 0, tzinfo=UTC),
    home_goals: int = 2,
    away_goals: int = 0,
    odds: tuple[str, str, str] | None = ("1.85", "3.60", "4.50"),
) -> HistoricalMatch:
    closing = tuple(Decimal(o) for o in odds) if odds else (None, None, None)
    return HistoricalMatch(
        season=season,
        kickoff_utc=kickoff,
        home_team_name=home,
        away_team_name=away,
        home_goals=home_goals,
        away_goals=away_goals,
        closing_home=closing[0],
        closing_draw=closing[1],
        closing_away=closing[2],
    )


class FakeHistoryProvider:
    def __init__(self, rows: list[HistoricalMatch]) -> None:
        self.rows = rows

    def fetch_history(self, csv_url: str) -> list[HistoricalMatch]:
        return self.rows


def test_import_creates_finished_match_with_closing_snapshots(session: Session) -> None:
    service = HistoryImportService(session, FakeHistoryProvider([_row()]))  # type: ignore[arg-type]
    result = service.import_history("http://example/bra.csv")

    assert result.matches_created == 1
    assert result.snapshots_inserted == 3
    match = session.scalar(select(Match))
    assert match is not None
    assert match.status == MatchStatus.FINISHED
    assert (match.home_goals, match.away_goals) == (2, 0)
    snapshots = list(session.scalars(select(OddsSnapshot)))
    assert len(snapshots) == 3
    assert all(s.is_closing for s in snapshots)
    # synthetic timestamp sits just before kickoff (ADR-0005)
    assert all(s.captured_at < match.kickoff_utc for s in snapshots)


def test_reimport_is_idempotent(session: Session) -> None:
    provider = FakeHistoryProvider([_row()])
    service = HistoryImportService(session, provider)  # type: ignore[arg-type]
    service.import_history("http://example/bra.csv")
    second = HistoryImportService(session, provider)  # type: ignore[arg-type]
    result = second.import_history("http://example/bra.csv")

    assert result.matches_created == 0
    assert result.snapshots_inserted == 0  # closing already present
    assert session.scalar(select(func.count(Match.id))) == 1
    assert session.scalar(select(func.count(OddsSnapshot.id))) == 3


def test_rows_without_odds_still_import_results(session: Session) -> None:
    service = HistoryImportService(session, FakeHistoryProvider([_row(odds=None)]))  # type: ignore[arg-type]
    result = service.import_history("http://example/bra.csv")

    assert result.matches_created == 1
    assert result.snapshots_inserted == 0


def test_existing_live_match_gets_result_but_never_synthetic_odds(
    session: Session,
) -> None:
    """A CSV row for a match we track live (autocreated from odds events)
    must update the result and must NOT inject synthetic closing odds."""
    live = seed_match(session)  # Flamengo x Palmeiras, kickoff 2026-07-20 16:00
    live.provider_id = "toa:abc123"
    session.commit()

    row = _row(
        home="Flamengo",
        away="Palmeiras",
        season="2026",
        kickoff=datetime(2026, 7, 20, 20, 0, tzinfo=UTC),  # clock differs, same day
        home_goals=3,
        away_goals=1,
    )
    service = HistoryImportService(session, FakeHistoryProvider([row]))  # type: ignore[arg-type]
    result = service.import_history("http://example/bra.csv")

    assert result.matches_created == 0
    assert result.results_updated == 1
    assert result.snapshots_inserted == 0  # no synthetic odds on live matches
    session.expire_all()
    assert live.status == MatchStatus.FINISHED
    assert (live.home_goals, live.away_goals) == (3, 1)
    assert session.scalar(select(func.count(Match.id))) == 1  # no duplicate


def test_teams_bridge_across_providers_by_normalized_name(session: Session) -> None:
    """'Sao Paulo' from the CSV and 'São Paulo' from another provider must
    resolve to one team row."""
    from src.models.competition import League

    league = League(provider_id="toa:x", season="2026", name="x", country=None)
    session.add(league)
    session.flush()
    session.add(Team(provider_id="toa:sao paulo", name="São Paulo", league_id=league.id))
    session.commit()

    row = _row(home="Sao Paulo", away="Cruzeiro")
    HistoryImportService(session, FakeHistoryProvider([row])).import_history("http://x")  # type: ignore[arg-type]

    names = sorted(t.name for t in session.scalars(select(Team)))
    assert names == ["Cruzeiro", "São Paulo"]  # bridged, not duplicated


def test_teams_bridge_through_alias_table(session: Session) -> None:
    """'Atletico-MG' (CSV) must land on the existing 'Atletico Mineiro'
    (The Odds API) team row — the case that orphaned 7 teams on the first
    real import."""
    from src.models.competition import League

    league = League(provider_id="toa:x", season="2026", name="x", country=None)
    session.add(league)
    session.flush()
    session.add(
        Team(provider_id="toa:atletico mineiro", name="Atletico Mineiro", league_id=league.id)
    )
    session.commit()

    row = _row(home="Atletico-MG", away="Fortaleza")
    HistoryImportService(session, FakeHistoryProvider([row])).import_history("http://x")  # type: ignore[arg-type]

    names = sorted(t.name for t in session.scalars(select(Team)))
    assert names == ["Atletico Mineiro", "Fortaleza"]  # no duplicate Atletico
