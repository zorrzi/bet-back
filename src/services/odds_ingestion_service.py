"""Odds snapshot ingestion (Phase 1) — append-only by construction.

Each run captures the provider's current prices and INSERTS one snapshot row
per quote. `captured_at` is stamped AFTER the provider responds: stamping
before the call would let slow/retried fetches record post-kickoff prices as
pre-kickoff, poisoning closing lines and CLV. Events that cannot be resolved
onto a known match are counted and logged, never guessed.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.models.odds import Bookmaker, Market
from src.providers.base import EventOdds, OddsProvider, OddsQuote
from src.repositories.match_repository import MatchRepository
from src.repositories.odds_repository import OddsRepository

logger = logging.getLogger(__name__)

DEFAULT_SHARP_BOOKMAKERS = frozenset({"pinnacle"})


@dataclass(frozen=True)
class OddsIngestionResult:
    events_seen: int
    events_matched: int
    events_unmatched: int
    snapshots_inserted: int
    captured_at: datetime


class OddsIngestionService:
    def __init__(
        self,
        session: Session,
        provider: OddsProvider,
        sharp_bookmakers: frozenset[str] | set[str] = DEFAULT_SHARP_BOOKMAKERS,
    ) -> None:
        self._session = session
        self._provider = provider
        self._sharp_bookmakers = sharp_bookmakers
        self._matches = MatchRepository(session)
        self._odds = OddsRepository(session)
        # per-run reference caches: bookmakers/markets repeat per quote and
        # would otherwise cost one SELECT each
        self._bookmaker_cache: dict[str, Bookmaker] = {}
        self._market_cache: dict[str, Market] = {}

    def ingest_current_odds(
        self, sport_key: str, regions: str, markets: str
    ) -> OddsIngestionResult:
        events = self._provider.fetch_odds(sport_key, regions, markets)
        captured_at = datetime.now(UTC)
        matched = 0
        inserted = 0
        for event in events:
            count = self._ingest_event(event, captured_at)
            if count is None:
                continue
            matched += 1
            inserted += count
        self._session.commit()
        result = OddsIngestionResult(
            events_seen=len(events),
            events_matched=matched,
            events_unmatched=len(events) - matched,
            snapshots_inserted=inserted,
            captured_at=captured_at,
        )
        logger.info(
            "odds_ingestion.completed",
            extra={
                "sport_key": sport_key,
                "events_seen": result.events_seen,
                "events_matched": result.events_matched,
                "events_unmatched": result.events_unmatched,
                "snapshots_inserted": result.snapshots_inserted,
            },
        )
        return result

    def _ingest_event(self, event: EventOdds, captured_at: datetime) -> int | None:
        """Insert all quotes of one event. Returns rows inserted, or None if
        the event could not be resolved onto a match."""
        match = self._matches.find_by_teams_and_kickoff(
            event.home_team_name, event.away_team_name, event.kickoff_utc
        )
        if match is None:
            logger.warning(
                "odds_ingestion.event_unmatched",
                extra={
                    "home": event.home_team_name,
                    "away": event.away_team_name,
                    "kickoff": event.kickoff_utc.isoformat(),
                },
            )
            return None
        inserted = 0
        for quote in event.quotes:
            bookmaker = self._get_bookmaker(quote.bookmaker_provider_id, quote.bookmaker_name)
            market = self._get_market(quote)
            self._odds.insert_snapshot(
                match_id=match.id,
                bookmaker_id=bookmaker.id,
                market_id=market.id,
                selection=quote.selection,
                line=quote.line,
                price_decimal=quote.price_decimal,
                captured_at=captured_at,
            )
            inserted += 1
        return inserted

    def _get_bookmaker(self, provider_id: str, name: str) -> Bookmaker:
        bookmaker = self._bookmaker_cache.get(provider_id)
        if bookmaker is None:
            bookmaker = self._odds.upsert_bookmaker(
                provider_id, name, is_sharp=provider_id in self._sharp_bookmakers
            )
            self._bookmaker_cache[provider_id] = bookmaker
        return bookmaker

    def _get_market(self, quote: OddsQuote) -> Market:
        market = self._market_cache.get(quote.market_code)
        if market is None:
            market = self._odds.upsert_market(
                quote.market_code,
                quote.market_name,
                quote.market_category,
                quote.n_selections,
            )
            self._market_cache[quote.market_code] = market
        return market
