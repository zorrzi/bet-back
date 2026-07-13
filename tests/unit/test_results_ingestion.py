from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.match import Match, MatchStatus
from src.providers.base import ScoreData
from src.services.results_ingestion_service import ResultsIngestionService
from tests.helpers import KICKOFF, seed_match


def _score(
    *,
    event_id: str = "abc123",
    home: str = "Flamengo",
    away: str = "Palmeiras",
    kickoff: datetime = KICKOFF,
    completed: bool = True,
    home_score: int | None = 2,
    away_score: int | None = 1,
) -> ScoreData:
    return ScoreData(
        event_provider_id=event_id,
        home_team_name=home,
        away_team_name=away,
        kickoff_utc=kickoff,
        completed=completed,
        home_score=home_score,
        away_score=away_score,
    )


class FakeScoresProvider:
    def __init__(self, scores: list[ScoreData]) -> None:
        self.scores = scores

    def fetch_scores(self, sport_key: str, days_from: int) -> list[ScoreData]:
        return self.scores


def test_completed_score_finishes_match_by_name_match(session: Session) -> None:
    seed_match(session)
    service = ResultsIngestionService(session, FakeScoresProvider([_score()]))
    result = service.ingest_scores("soccer_brazil_campeonato", 3)

    assert result.results_applied == 1
    match = session.scalar(select(Match))
    assert match is not None
    assert match.status == MatchStatus.FINISHED
    assert (match.home_goals, match.away_goals) == (2, 1)


def test_incomplete_scores_are_ignored(session: Session) -> None:
    seed_match(session)
    provider = FakeScoresProvider(
        [
            _score(completed=False),  # still playing
            _score(completed=True, home_score=None, away_score=None),  # no data
        ]
    )
    result = ResultsIngestionService(session, provider).ingest_scores(
        "soccer_brazil_campeonato", 3
    )

    assert result.results_applied == 0
    match = session.scalar(select(Match))
    assert match is not None
    assert match.status == MatchStatus.SCHEDULED


def test_unmatched_score_is_counted_not_guessed(session: Session) -> None:
    seed_match(session)
    provider = FakeScoresProvider(
        [_score(event_id="zzz", home="Unknown FC", away="Mystery United")]
    )
    result = ResultsIngestionService(session, provider).ingest_scores(
        "soccer_brazil_campeonato", 3
    )

    assert result.results_applied == 0
    assert result.events_unmatched == 1


def test_score_resolves_by_provider_id_first(session: Session) -> None:
    """Autocreated matches carry 'toa:<event id>' — the scores endpoint uses
    the same ids, so resolution must not depend on names at all."""
    match = seed_match(session)
    match.provider_id = "toa:abc123"
    session.commit()

    provider = FakeScoresProvider(
        [
            _score(
                home="Renamed FC", away="Also Renamed", kickoff=datetime(2030, 1, 1, tzinfo=UTC)
            )
        ]
    )
    result = ResultsIngestionService(session, provider).ingest_scores(
        "soccer_brazil_campeonato", 3
    )

    assert result.results_applied == 1
    session.expire_all()
    assert match.status == MatchStatus.FINISHED
