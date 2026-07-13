from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.odds import Bookmaker, Market, OddsSnapshot
from src.services.closing_service import ClosingService
from tests.helpers import KICKOFF, seed_match


def _insert_snapshot(
    session: Session,
    match_id: int,
    bookmaker_id: int,
    market_id: int,
    selection: str,
    price: str,
    captured_at: datetime,
) -> OddsSnapshot:
    snap = OddsSnapshot(
        match_id=match_id,
        bookmaker_id=bookmaker_id,
        market_id=market_id,
        selection=selection,
        line=None,
        price_decimal=Decimal(price),
        captured_at=captured_at,
    )
    session.add(snap)
    return snap


def _seed_reference(session: Session) -> tuple[int, int]:
    bookmaker = Bookmaker(provider_id="pinnacle", name="Pinnacle", is_sharp=True)
    market = Market(code="1X2", name="Match Result", category="match_result", n_selections=3)
    session.add_all([bookmaker, market])
    session.flush()
    return bookmaker.id, market.id


def test_marks_only_latest_pre_kickoff_snapshot_per_selection(session: Session) -> None:
    match = seed_match(session)
    bookmaker_id, market_id = _seed_reference(session)
    early = _insert_snapshot(
        session,
        match.id,
        bookmaker_id,
        market_id,
        "HOME",
        "2.30",
        KICKOFF - timedelta(hours=6),
    )
    late = _insert_snapshot(
        session,
        match.id,
        bookmaker_id,
        market_id,
        "HOME",
        "2.10",
        KICKOFF - timedelta(minutes=10),
    )
    other_selection = _insert_snapshot(
        session,
        match.id,
        bookmaker_id,
        market_id,
        "AWAY",
        "3.60",
        KICKOFF - timedelta(hours=6),
    )
    session.commit()

    result = ClosingService(session).mark_closing_lines(now=KICKOFF + timedelta(minutes=1))

    assert result.matches_processed == 1
    assert result.snapshots_marked == 2  # one per (bookmaker, market, selection)
    session.expire_all()
    assert late.is_closing is True
    assert early.is_closing is False
    assert other_selection.is_closing is True


def test_does_not_mark_before_kickoff(session: Session) -> None:
    match = seed_match(session)
    bookmaker_id, market_id = _seed_reference(session)
    _insert_snapshot(
        session,
        match.id,
        bookmaker_id,
        market_id,
        "HOME",
        "2.10",
        KICKOFF - timedelta(hours=1),
    )
    session.commit()

    result = ClosingService(session).mark_closing_lines(now=KICKOFF - timedelta(minutes=30))

    assert result.matches_processed == 0
    assert result.snapshots_marked == 0


def test_mark_closing_is_idempotent(session: Session) -> None:
    match = seed_match(session)
    bookmaker_id, market_id = _seed_reference(session)
    _insert_snapshot(
        session,
        match.id,
        bookmaker_id,
        market_id,
        "HOME",
        "2.10",
        KICKOFF - timedelta(minutes=10),
    )
    session.commit()

    service = ClosingService(session)
    first = service.mark_closing_lines(now=KICKOFF + timedelta(minutes=1))
    second = service.mark_closing_lines(now=KICKOFF + timedelta(minutes=2))

    assert first.snapshots_marked == 1
    assert second.snapshots_marked == 0  # already marked; nothing re-flagged
    marked = list(
        session.scalars(select(OddsSnapshot).where(OddsSnapshot.is_closing.is_(True)))
    )
    assert len(marked) == 1
