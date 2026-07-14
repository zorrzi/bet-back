"""Historical results + closing-odds import from football-data.co.uk
(ADR-0005) — the calibration corpus for the goal model and the closing-line
reference for backtests.

Rules that keep the data honest:

- Teams are bridged across providers by normalized name, so 'Sao Paulo'
  (CSV / The Odds API) and 'São Paulo' resolve to ONE team row.
- A CSV row that corresponds to an existing match (same teams, same day —
  e.g. one autocreated from live odds) UPDATES its result and gets no
  synthetic odds: imported closing snapshots (captured_at = kickoff - 1min,
  is_closing=true) are attached ONLY to matches this importer created.
  Mixing synthetic closings into live-captured odds would silently corrupt
  CLV.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from src.models.competition import Team
from src.models.match import Match, MatchStatus
from src.models.odds import OddsSnapshot
from src.providers.football_data_co_uk import FootballDataCoUkProvider, HistoricalMatch
from src.repositories.competition_repository import CompetitionRepository
from src.repositories.match_repository import MatchRepository
from src.repositories.odds_repository import OddsRepository
from src.utils.text import canonical_team_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HistoryImportResult:
    rows_seen: int
    matches_created: int
    results_updated: int
    snapshots_inserted: int


class HistoryImportService:
    def __init__(self, session: Session, provider: FootballDataCoUkProvider) -> None:
        self._session = session
        self._provider = provider
        self._competitions = CompetitionRepository(session)
        self._matches = MatchRepository(session)
        self._odds = OddsRepository(session)
        self._team_cache: dict[str, Team] = {}

    def import_history(self, csv_url: str) -> HistoryImportResult:
        rows = self._provider.fetch_history(csv_url)
        self._warm_team_cache()
        created = 0
        updated = 0
        snapshots = 0
        for row in rows:
            outcome, inserted = self._import_row(row)
            if outcome == "created":
                created += 1
            elif outcome == "updated":
                updated += 1
            snapshots += inserted
        self._session.commit()
        result = HistoryImportResult(
            rows_seen=len(rows),
            matches_created=created,
            results_updated=updated,
            snapshots_inserted=snapshots,
        )
        logger.info(
            "history_import.completed",
            extra={
                "url": csv_url,
                "rows_seen": result.rows_seen,
                "matches_created": result.matches_created,
                "results_updated": result.results_updated,
                "snapshots_inserted": result.snapshots_inserted,
            },
        )
        return result

    def _warm_team_cache(self) -> None:
        for team in self._session.scalars(select(Team)):
            self._team_cache.setdefault(canonical_team_key(team.name), team)

    def _get_team(self, name: str, league_id: int) -> Team:
        key = canonical_team_key(name)
        team = self._team_cache.get(key)
        if team is None:
            team = self._competitions.upsert_team(f"fdcuk:{key}", name, league_id)
            self._team_cache[key] = team
        return team

    def _import_row(self, row: HistoricalMatch) -> tuple[str, int]:
        league = self._competitions.upsert_league(
            provider_id="fdcuk:BRA", season=row.season, name="Serie A", country="Brazil"
        )
        home = self._get_team(row.home_team_name, league.id)
        away = self._get_team(row.away_team_name, league.id)

        existing = self._find_same_fixture(home.id, away.id, row)
        if existing is not None:
            changed = existing.status != MatchStatus.FINISHED or (
                existing.home_goals,
                existing.away_goals,
            ) != (row.home_goals, row.away_goals)
            existing.status = MatchStatus.FINISHED
            existing.home_goals = row.home_goals
            existing.away_goals = row.away_goals
            if existing.provider_id.startswith("fdcuk:"):
                inserted = self._import_closing_odds(existing, row)
                return ("updated" if changed else "unchanged"), inserted
            # live-tracked match: result only, never synthetic odds
            return ("updated" if changed else "unchanged"), 0

        key = (
            f"fdcuk:BRA:{row.season}:{row.kickoff_utc:%Y%m%d}:"
            f"{canonical_team_key(row.home_team_name)}:"
            f"{canonical_team_key(row.away_team_name)}"
        )
        outcome = self._matches.upsert(
            provider_id=key,
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_utc=row.kickoff_utc,
            status=MatchStatus.FINISHED,
            home_goals=row.home_goals,
            away_goals=row.away_goals,
        )
        inserted = self._import_closing_odds(outcome.match, row)
        return "created", inserted

    def _find_same_fixture(
        self, home_id: int, away_id: int, row: HistoricalMatch
    ) -> Match | None:
        """Same home/away teams within ±1 day = the same real-world fixture,
        whatever provider created it (kickoff clocks differ across sources)."""
        window = timedelta(days=1)
        return self._session.scalar(
            select(Match).where(
                Match.home_team_id == home_id,
                Match.away_team_id == away_id,
                Match.kickoff_utc >= row.kickoff_utc - window,
                Match.kickoff_utc <= row.kickoff_utc + window,
            )
        )

    def _import_closing_odds(self, match: Match, row: HistoricalMatch) -> int:
        if row.closing_home is None or row.closing_draw is None or row.closing_away is None:
            return 0
        already = self._session.scalar(
            select(
                exists().where(
                    OddsSnapshot.match_id == match.id,
                    OddsSnapshot.is_closing.is_(True),
                )
            )
        )
        if already:
            return 0
        bookmaker = self._odds.upsert_bookmaker("pinnacle", "Pinnacle", is_sharp=True)
        market = self._odds.upsert_market("1X2", "Match Result", "match_result", 3)
        captured_at = row.kickoff_utc - timedelta(minutes=1)  # synthetic, ADR-0005
        for selection, price in (
            ("HOME", row.closing_home),
            ("DRAW", row.closing_draw),
            ("AWAY", row.closing_away),
        ):
            snapshot = self._odds.insert_snapshot(
                match_id=match.id,
                bookmaker_id=bookmaker.id,
                market_id=market.id,
                selection=selection,
                line=None,
                price_decimal=price,
                captured_at=captured_at,
            )
            snapshot.is_closing = True
        return 3
