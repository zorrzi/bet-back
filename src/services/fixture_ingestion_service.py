"""Fixture/result ingestion (Phase 1).

Pulls a league season from the fixture provider and upserts leagues, teams
and matches. Idempotent: re-running never duplicates rows (provider ids are
the keys); finished matches get their result and status updated in place —
results are facts, not history like odds.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.providers.base import FixtureData, FixtureProvider
from src.repositories.competition_repository import CompetitionRepository
from src.repositories.match_repository import MatchRepository
from src.repositories.odds_repository import OddsRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FixtureIngestionResult:
    fixtures_seen: int
    matches_created: int
    matches_updated: int  # counts real changes only, not touched rows


class FixtureIngestionService:
    def __init__(self, session: Session, provider: FixtureProvider) -> None:
        self._session = session
        self._provider = provider
        self._competitions = CompetitionRepository(session)
        self._matches = MatchRepository(session)
        self._odds = OddsRepository(session)

    def ingest_league_season(
        self, league_provider_id: str, season: str
    ) -> FixtureIngestionResult:
        fixtures = self._provider.fetch_fixtures(league_provider_id, season)
        created = 0
        updated = 0
        for fixture in fixtures:
            outcome = self._ingest_one(fixture)
            if outcome == "created":
                created += 1
            elif outcome == "changed":
                updated += 1
        self._session.commit()
        result = FixtureIngestionResult(
            fixtures_seen=len(fixtures), matches_created=created, matches_updated=updated
        )
        logger.info(
            "fixture_ingestion.completed",
            extra={
                "league_provider_id": league_provider_id,
                "season": season,
                "seen": result.fixtures_seen,
                "created": result.matches_created,
                "updated": result.matches_updated,
            },
        )
        return result

    def _ingest_one(self, fixture: FixtureData) -> str:
        league = self._competitions.upsert_league(
            provider_id=fixture.league_provider_id,
            season=fixture.season,
            name=fixture.league_name,
            country=fixture.league_country,
        )
        home = self._competitions.upsert_team(
            fixture.home_team_provider_id, fixture.home_team_name, league.id
        )
        away = self._competitions.upsert_team(
            fixture.away_team_provider_id, fixture.away_team_name, league.id
        )
        outcome = self._matches.upsert(
            provider_id=fixture.provider_id,
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_utc=fixture.kickoff_utc,
            status=fixture.status,
            home_goals=fixture.home_goals,
            away_goals=fixture.away_goals,
        )
        if outcome.kickoff_changed:
            # rescheduled match: whatever was flagged as closing no longer is
            cleared = self._odds.clear_closing_flags(outcome.match.id)
            if cleared:
                logger.info(
                    "fixture_ingestion.closing_flags_cleared",
                    extra={"match_id": outcome.match.id, "cleared": cleared},
                )
        if outcome.created:
            return "created"
        return "changed" if outcome.changed else "unchanged"
