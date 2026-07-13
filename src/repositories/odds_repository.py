"""Data access for bookmakers, markets and odds snapshots.

`odds_snapshots` is append-only: this repository exposes INSERT and the
single sanctioned mutation (flagging `is_closing`). There is deliberately no
update method for prices (spec §4.2, golden rule).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.models.odds import Bookmaker, Market, OddsSnapshot
from src.repositories.base import get_or_create


class OddsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_bookmaker(self, provider_id: str, name: str, is_sharp: bool) -> Bookmaker:
        bookmaker, created = get_or_create(
            self._session,
            Bookmaker,
            {"provider_id": provider_id},
            {"name": name, "is_sharp": is_sharp},
        )
        if not created and bookmaker.is_sharp != is_sharp:
            # sharp set is config (settings.sharp_bookmakers); keep rows in sync
            bookmaker.is_sharp = is_sharp
        return bookmaker

    def upsert_market(self, code: str, name: str, category: str, n_selections: int) -> Market:
        market, _ = get_or_create(
            self._session,
            Market,
            {"code": code},
            {"name": name, "category": category, "n_selections": n_selections},
        )
        return market

    def insert_snapshot(
        self,
        *,
        match_id: int,
        bookmaker_id: int,
        market_id: int,
        selection: str,
        line: Decimal | None,
        price_decimal: Decimal,
        captured_at: datetime,
    ) -> OddsSnapshot:
        snapshot = OddsSnapshot(
            match_id=match_id,
            bookmaker_id=bookmaker_id,
            market_id=market_id,
            selection=selection,
            line=line,
            price_decimal=price_decimal,
            captured_at=captured_at,
        )
        self._session.add(snapshot)
        return snapshot

    def list_snapshots_for_match(self, match_id: int) -> list[OddsSnapshot]:
        return list(
            self._session.scalars(
                select(OddsSnapshot)
                .where(OddsSnapshot.match_id == match_id)
                .order_by(OddsSnapshot.captured_at)
            )
        )

    def mark_closing_snapshots(self, match_id: int, kickoff_utc: datetime) -> int:
        """Flag the latest pre-kickoff snapshot of every
        (bookmaker, market, selection, line) group as the closing line.
        Idempotent: re-running only ever selects the same rows."""
        snapshots = self._session.scalars(
            select(OddsSnapshot).where(
                OddsSnapshot.match_id == match_id,
                OddsSnapshot.captured_at < kickoff_utc,
            )
        )
        latest: dict[tuple[int, int, str, Decimal | None], OddsSnapshot] = {}
        for snap in snapshots:
            key = (snap.bookmaker_id, snap.market_id, snap.selection, snap.line)
            current = latest.get(key)
            if current is None or snap.captured_at > current.captured_at:
                latest[key] = snap
        ids = [snap.id for snap in latest.values()]
        if not ids:
            return 0
        self._session.execute(
            update(OddsSnapshot).where(OddsSnapshot.id.in_(ids)).values(is_closing=True)
        )
        return len(ids)

    def clear_closing_flags(self, match_id: int) -> int:
        """Un-flag closing snapshots — used when a match's kickoff moves
        (rescheduled game): the old 'closing' price is no longer the closing
        line of the real kickoff."""
        result = self._session.execute(
            update(OddsSnapshot)
            .where(OddsSnapshot.match_id == match_id, OddsSnapshot.is_closing.is_(True))
            .values(is_closing=False)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]  # CursorResult at runtime
