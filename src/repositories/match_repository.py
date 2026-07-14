"""Data access for matches."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from src.models.match import Match, MatchStatus
from src.models.odds import OddsSnapshot
from src.utils.text import canonical_team_key


def _as_utc(value: datetime) -> datetime:
    """DB values are UTC by convention but SQLite returns them naive while
    Postgres returns them aware; normalize before comparing."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@dataclass(frozen=True)
class MatchUpsertOutcome:
    match: Match
    created: bool
    changed: bool
    kickoff_changed: bool


class MatchRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, match_id: int) -> Match | None:
        return self._session.get(Match, match_id)

    def get_by_provider_id(self, provider_id: str) -> Match | None:
        return self._session.scalar(select(Match).where(Match.provider_id == provider_id))

    def upsert(
        self,
        *,
        provider_id: str,
        league_id: int,
        home_team_id: int,
        away_team_id: int,
        kickoff_utc: datetime,
        status: str,
        home_goals: int | None,
        away_goals: int | None,
    ) -> MatchUpsertOutcome:
        match = self.get_by_provider_id(provider_id)
        if match is None:
            match = Match(
                provider_id=provider_id,
                league_id=league_id,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                kickoff_utc=kickoff_utc,
                status=status,
                home_goals=home_goals,
                away_goals=away_goals,
            )
            self._session.add(match)
            self._session.flush()
            return MatchUpsertOutcome(match, created=True, changed=True, kickoff_changed=False)

        kickoff_changed = _as_utc(match.kickoff_utc) != _as_utc(kickoff_utc)
        changed = kickoff_changed or match.status != status
        match.kickoff_utc = kickoff_utc
        match.status = status
        # Never erase a stored result with provider nulls: a transient feed
        # glitch on a finished match would corrupt settled data downstream.
        if home_goals is not None or away_goals is not None or match.home_goals is None:
            changed = changed or (match.home_goals, match.away_goals) != (
                home_goals,
                away_goals,
            )
            match.home_goals = home_goals
            match.away_goals = away_goals
        return MatchUpsertOutcome(
            match, created=False, changed=changed, kickoff_changed=kickoff_changed
        )

    def list_matches(
        self,
        *,
        league_id: int | None = None,
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Match]:
        query = select(Match).order_by(Match.kickoff_utc)
        if league_id is not None:
            query = query.where(Match.league_id == league_id)
        if status is not None:
            query = query.where(Match.status == status)
        if date_from is not None:
            query = query.where(Match.kickoff_utc >= date_from)
        if date_to is not None:
            query = query.where(Match.kickoff_utc <= date_to)
        return list(self._session.scalars(query.limit(limit).offset(offset)))

    def find_by_teams_and_kickoff(
        self,
        home_team_name: str,
        away_team_name: str,
        kickoff_utc: datetime,
    ) -> Match | None:
        """Resolve an odds-provider event onto a match: exact kickoff, then
        accent-insensitive normalized team-name comparison. Conservative on
        purpose — an unmatched event is logged and skipped, never guessed."""
        wanted_home = canonical_team_key(home_team_name)
        wanted_away = canonical_team_key(away_team_name)
        matches = self._session.scalars(select(Match).where(Match.kickoff_utc == kickoff_utc))
        for match in matches:  # teams come along via joined-eager relationships
            if (
                canonical_team_key(match.home_team.name) == wanted_home
                and canonical_team_key(match.away_team.name) == wanted_away
            ):
                return match
        return None

    def list_closing_candidates(self, now: datetime, lookback_days: int) -> list[Match]:
        """Matches whose kickoff passed recently, that HAVE pre-kickoff
        snapshots and have NO closing flag yet. Bounded so the periodic job
        does not rescan the whole season forever."""
        has_snapshot = exists().where(
            OddsSnapshot.match_id == Match.id,
            OddsSnapshot.captured_at < Match.kickoff_utc,
        )
        already_marked = exists().where(
            OddsSnapshot.match_id == Match.id,
            OddsSnapshot.is_closing.is_(True),
        )
        query = select(Match).where(
            Match.kickoff_utc <= now,
            Match.kickoff_utc >= now - timedelta(days=lookback_days),
            Match.status != MatchStatus.POSTPONED,
            has_snapshot,
            ~already_marked,
        )
        return list(self._session.scalars(query))
