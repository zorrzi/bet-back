from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.betting import BankrollHistory, BetResult
from src.models.match import MatchStatus
from src.models.odds import Bookmaker, Market, OddsSnapshot
from src.models.signals import ValueBet, ValueBetStatus
from src.services.bet_service import (
    BetPlacementError,
    BetService,
    compute_pnl,
    resolve_result,
)
from tests.helpers import KICKOFF, seed_match

NOW = KICKOFF - timedelta(hours=2)


# --- pure settlement math, hand-calculated (spec §11.3) ---


def test_resolve_result_1x2() -> None:
    assert resolve_result("1X2", "HOME", None, 2, 1) == BetResult.WIN
    assert resolve_result("1X2", "DRAW", None, 1, 1) == BetResult.WIN
    assert resolve_result("1X2", "AWAY", None, 2, 1) == BetResult.LOSS


def test_resolve_result_totals_with_push() -> None:
    assert resolve_result("OU_2_5", "OVER", Decimal("2.5"), 2, 1) == BetResult.WIN
    assert resolve_result("OU_2_5", "UNDER", Decimal("2.5"), 1, 0) == BetResult.WIN
    assert resolve_result("OU_3", "OVER", Decimal("3"), 2, 1) == BetResult.PUSH
    assert resolve_result("OU_3", "UNDER", Decimal("3"), 1, 0) == BetResult.WIN


def test_resolve_result_btts() -> None:
    assert resolve_result("BTTS", "YES", None, 1, 1) == BetResult.WIN
    assert resolve_result("BTTS", "NO", None, 2, 0) == BetResult.WIN
    assert resolve_result("BTTS", "YES", None, 2, 0) == BetResult.LOSS


def test_resolve_result_unsupported_market_raises() -> None:
    with pytest.raises(ValueError, match="unsupported market"):
        resolve_result("AH_-0_5", "HOME", Decimal("-0.5"), 1, 0)


def test_compute_pnl_hand_cases() -> None:
    # win: 20 @ 2.20 -> +24.00 ; loss -> -20 ; push -> 0
    assert compute_pnl(BetResult.WIN, Decimal("20"), Decimal("2.20")) == Decimal("24.00")
    assert compute_pnl(BetResult.LOSS, Decimal("20"), Decimal("2.20")) == Decimal("-20")
    assert compute_pnl(BetResult.PUSH, Decimal("20"), Decimal("2.20")) == Decimal("0.00")


# --- placement + settlement flow ---


def _seed_signal(session: Session) -> ValueBet:
    match = seed_match(session)
    pinnacle = Bookmaker(provider_id="pinnacle", name="Pinnacle", is_sharp=True)
    market = Market(code="1X2", name="Match Result", category="match_result", n_selections=3)
    session.add_all([pinnacle, market])
    session.flush()
    signal = ValueBet(
        match_id=match.id,
        market_id=market.id,
        bookmaker_id=pinnacle.id,
        selection="HOME",
        line=None,
        model_prob=Decimal("0.52"),
        fair_prob=Decimal("0.4864"),
        offered_odds=Decimal("2.20"),
        edge=Decimal("0.144"),
        kelly_fraction=Decimal("0.12"),
        suggested_stake=Decimal("20.00"),
        model_version="dixoncoles_v1",
        status=ValueBetStatus.CANDIDATE,
    )
    session.add(signal)
    session.commit()
    return signal


def _service(session: Session) -> BetService:
    return BetService(session, initial_bankroll=Decimal("1000"))


def test_place_bet_debits_bankroll_and_marks_signal(session: Session) -> None:
    signal = _seed_signal(session)
    bet = _service(session).place_from_value_bet(signal.id, now=NOW)

    assert bet.taken_odds == Decimal("2.20")
    assert bet.stake == Decimal("20.00")
    assert signal.status == ValueBetStatus.PLACED
    last = list(session.scalars(select(BankrollHistory).order_by(BankrollHistory.id)))[-1]
    assert last.reason == "bet_placed"
    assert Decimal(last.balance) == Decimal("980.00")


def test_place_bet_after_kickoff_is_refused(session: Session) -> None:
    signal = _seed_signal(session)
    with pytest.raises(BetPlacementError, match="kickoff already passed"):
        _service(session).place_from_value_bet(signal.id, now=KICKOFF + timedelta(minutes=1))


def test_place_bet_twice_is_refused(session: Session) -> None:
    signal = _seed_signal(session)
    service = _service(session)
    service.place_from_value_bet(signal.id, now=NOW)
    with pytest.raises(BetPlacementError, match="not a candidate"):
        service.place_from_value_bet(signal.id, now=NOW)


def test_settle_win_computes_pnl_clv_and_credits_bankroll(session: Session) -> None:
    signal = _seed_signal(session)
    service = _service(session)
    bet = service.place_from_value_bet(signal.id, now=NOW)

    # closing snapshot at the same bookmaker: 2.05 -> clv = 2.20/2.05 - 1
    session.add(
        OddsSnapshot(
            match_id=signal.match_id,
            bookmaker_id=signal.bookmaker_id,
            market_id=signal.market_id,
            selection="HOME",
            price_decimal=Decimal("2.05"),
            captured_at=KICKOFF - timedelta(minutes=5),
            is_closing=True,
        )
    )
    from src.models.match import Match

    match = session.get(Match, signal.match_id)
    assert match is not None
    match.status = MatchStatus.FINISHED
    match.home_goals, match.away_goals = 2, 0
    session.commit()

    result = service.settle_finished(now=KICKOFF + timedelta(hours=2))

    assert result.bets_settled == 1
    session.expire_all()
    assert bet.result == BetResult.WIN
    assert bet.pnl == Decimal("24.00")
    assert bet.closing_odds == Decimal("2.05")
    assert float(bet.clv) == pytest.approx(2.20 / 2.05 - 1, abs=1e-6)
    last = list(session.scalars(select(BankrollHistory).order_by(BankrollHistory.id)))[-1]
    assert last.reason == "bet_settled"
    assert Decimal(last.balance) == Decimal("1024.00")  # 980 + stake 20 + pnl 24


def test_settle_loss_debits_nothing_more(session: Session) -> None:
    signal = _seed_signal(session)
    service = _service(session)
    service.place_from_value_bet(signal.id, now=NOW)
    from src.models.match import Match

    match = session.get(Match, signal.match_id)
    assert match is not None
    match.status = MatchStatus.FINISHED
    match.home_goals, match.away_goals = 0, 1
    session.commit()

    service.settle_finished(now=KICKOFF + timedelta(hours=2))

    last = list(session.scalars(select(BankrollHistory).order_by(BankrollHistory.id)))[-1]
    assert Decimal(last.balance) == Decimal("980.00")  # stake lost, no credit
