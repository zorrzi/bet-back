"""Data access for leagues and teams. Upserts are keyed on provider ids
(idempotent ingestion, spec §11.5)."""

from sqlalchemy.orm import Session

from src.models.competition import League, Team
from src.repositories.base import get_or_create


class CompetitionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_league(
        self, provider_id: str, season: str, name: str, country: str | None
    ) -> League:
        league, created = get_or_create(
            self._session,
            League,
            {"provider_id": provider_id, "season": season},
            {"name": name, "country": country},
        )
        if not created:
            league.name = name
            league.country = country
        return league

    def upsert_team(self, provider_id: str, name: str, league_id: int) -> Team:
        team, created = get_or_create(
            self._session,
            Team,
            {"provider_id": provider_id},
            {"name": name, "league_id": league_id},
        )
        if not created:
            team.name = name
        return team
