"""API-Football (api-sports.io) fixture provider.

Docs: https://www.api-football.com/documentation-v3
Auth: `x-apisports-key` header. One call returns a league season's fixtures
including live status and final scores, which is what Phase 1 ingestion needs.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from src.config.settings import Settings
from src.models.match import MatchStatus
from src.providers.base import FixtureData
from src.providers.http import ProviderError, get_json

logger = logging.getLogger(__name__)

# API-Football short status -> our normalized MatchStatus
_STATUS_MAP = {
    "TBD": MatchStatus.SCHEDULED,
    "NS": MatchStatus.SCHEDULED,
    "1H": MatchStatus.LIVE,
    "HT": MatchStatus.LIVE,
    "2H": MatchStatus.LIVE,
    "ET": MatchStatus.LIVE,
    "BT": MatchStatus.LIVE,
    "P": MatchStatus.LIVE,
    "SUSP": MatchStatus.LIVE,
    "INT": MatchStatus.LIVE,
    "LIVE": MatchStatus.LIVE,
    "FT": MatchStatus.FINISHED,
    "AET": MatchStatus.FINISHED,
    "PEN": MatchStatus.FINISHED,
    "PST": MatchStatus.POSTPONED,
    "CANC": MatchStatus.POSTPONED,
    "ABD": MatchStatus.POSTPONED,
    "AWD": MatchStatus.FINISHED,
    "WO": MatchStatus.FINISHED,
}


class ApiFootballProvider:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.api_football_base_url.rstrip("/")
        self._headers = {"x-apisports-key": settings.api_football_key}
        self._timeout = settings.provider_timeout_seconds

    def fetch_fixtures(self, league_provider_id: str, season: str) -> list[FixtureData]:
        payload = get_json(
            f"{self._base_url}/fixtures",
            headers=self._headers,
            params={"league": league_provider_id, "season": season},
            timeout=self._timeout,
        )
        errors = payload.get("errors")
        if errors:
            raise ProviderError(f"API-Football returned errors: {errors}")
        fixtures = [
            fixture
            for raw in payload.get("response", [])
            if (fixture := self._parse_fixture(raw, season)) is not None
        ]
        logger.info(
            "api_football.fixtures_fetched",
            extra={"league": league_provider_id, "season": season, "count": len(fixtures)},
        )
        return fixtures

    def _parse_fixture(self, raw: dict[str, Any], season: str) -> FixtureData | None:
        try:
            fixture = raw["fixture"]
            league = raw["league"]
            teams = raw["teams"]
            goals = raw.get("goals", {})
            kickoff = datetime.fromisoformat(fixture["date"]).astimezone(UTC)
            status_short = fixture.get("status", {}).get("short", "NS")
            return FixtureData(
                provider_id=str(fixture["id"]),
                league_provider_id=str(league["id"]),
                league_name=league.get("name", ""),
                league_country=league.get("country"),
                season=str(league.get("season", season)),
                home_team_provider_id=str(teams["home"]["id"]),
                home_team_name=teams["home"]["name"],
                away_team_provider_id=str(teams["away"]["id"]),
                away_team_name=teams["away"]["name"],
                kickoff_utc=kickoff,
                status=_STATUS_MAP.get(status_short, MatchStatus.SCHEDULED),
                home_goals=goals.get("home"),
                away_goals=goals.get("away"),
            )
        except (KeyError, TypeError, ValueError):
            logger.warning(
                "api_football.fixture_parse_failed", extra={"raw_id": str(raw)[:200]}
            )
            return None
