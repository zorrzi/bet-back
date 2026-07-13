"""Closing-line marking (Phase 1).

After kickoff, the latest pre-kickoff snapshot of each
(bookmaker, market, selection, line) group becomes the closing line —
the reference every CLV calculation depends on (spec §6.2). Runs on a short
schedule; skips matches already marked, so it is idempotent.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.repositories.match_repository import MatchRepository
from src.repositories.odds_repository import OddsRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClosingMarkResult:
    matches_processed: int
    snapshots_marked: int


class ClosingService:
    def __init__(self, session: Session, lookback_days: int = 7) -> None:
        self._session = session
        self._lookback_days = lookback_days
        self._matches = MatchRepository(session)
        self._odds = OddsRepository(session)

    def mark_closing_lines(self, now: datetime | None = None) -> ClosingMarkResult:
        now = now or datetime.now(UTC)
        processed = 0
        marked = 0
        # single bounded query: recently kicked-off matches that have
        # pre-kickoff snapshots and no closing flag yet — the job stays a
        # cheap no-op once everything is marked
        for match in self._matches.list_closing_candidates(now, self._lookback_days):
            count = self._odds.mark_closing_snapshots(match.id, match.kickoff_utc)
            if count:
                processed += 1
                marked += count
        self._session.commit()
        result = ClosingMarkResult(matches_processed=processed, snapshots_marked=marked)
        logger.info(
            "closing_marker.completed",
            extra={
                "matches_processed": result.matches_processed,
                "snapshots_marked": result.snapshots_marked,
            },
        )
        return result
