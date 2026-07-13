"""Match results via the odds provider's scores endpoint (ADR-0004).

With API-Football's free plan blind to current seasons, finished scores for
the live league come from The Odds API `/scores`. Only completed events
update a match; in-progress ones are left alone (their result is not a fact
yet).
"""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.models.match import MatchStatus
from src.providers.base import ScoreData, ScoresProvider
from src.repositories.match_repository import MatchRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResultsIngestionResult:
    events_seen: int
    results_applied: int
    events_unmatched: int


class ResultsIngestionService:
    def __init__(self, session: Session, provider: ScoresProvider) -> None:
        self._session = session
        self._provider = provider
        self._matches = MatchRepository(session)

    def ingest_scores(self, sport_key: str, days_from: int) -> ResultsIngestionResult:
        scores = self._provider.fetch_scores(sport_key, days_from)
        applied = 0
        unmatched = 0
        for score in scores:
            if not score.completed or score.home_score is None or score.away_score is None:
                continue
            if self._apply_result(score):
                applied += 1
            else:
                unmatched += 1
        self._session.commit()
        result = ResultsIngestionResult(
            events_seen=len(scores), results_applied=applied, events_unmatched=unmatched
        )
        logger.info(
            "results_ingestion.completed",
            extra={
                "sport_key": sport_key,
                "events_seen": result.events_seen,
                "results_applied": result.results_applied,
                "events_unmatched": result.events_unmatched,
            },
        )
        return result

    def _apply_result(self, score: ScoreData) -> bool:
        match = self._matches.get_by_provider_id(f"toa:{score.event_provider_id}")
        if match is None:
            match = self._matches.find_by_teams_and_kickoff(
                score.home_team_name, score.away_team_name, score.kickoff_utc
            )
        if match is None:
            logger.warning(
                "results_ingestion.event_unmatched",
                extra={
                    "home": score.home_team_name,
                    "away": score.away_team_name,
                    "kickoff": score.kickoff_utc.isoformat(),
                },
            )
            return False
        match.status = MatchStatus.FINISHED
        match.home_goals = score.home_score
        match.away_goals = score.away_score
        return True
