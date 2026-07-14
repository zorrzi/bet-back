"""Paper-bet placement and settlement (Fase 3 / spec §6.2).

Placement: `placed_at` MUST precede kickoff — a bet recorded after kickoff
would poison every CLV number downstream (spec §4.3). The stake is debited
from the bankroll ledger immediately.

Settlement: for finished matches, resolve win/loss/push from the final
score, credit `stake + pnl` back to the ledger, and compute CLV against the
closing odds of the SAME selection (same bookmaker when available, any
sharp book otherwise).
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.betting import Bet, BetResult
from src.models.match import Match
from src.models.odds import Bookmaker, Market, OddsSnapshot
from src.models.signals import ValueBet, ValueBetStatus
from src.repositories.betting_repository import BankrollRepository, BetRepository

logger = logging.getLogger(__name__)


class BetPlacementError(ValueError):
    """Invalid bet placement (late, unknown signal, insufficient funds)."""


@dataclass(frozen=True)
class SettlementResult:
    bets_settled: int
    bets_skipped: int


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def resolve_result(
    market_code: str,
    selection: str,
    line: Decimal | None,
    home_goals: int,
    away_goals: int,
) -> str:
    """win/loss/push from the final score. Raises on unsupported markets."""
    if market_code == "1X2":
        winner = (
            "HOME" if home_goals > away_goals else "AWAY" if away_goals > home_goals else "DRAW"
        )
        return BetResult.WIN if selection == winner else BetResult.LOSS
    if market_code.startswith("OU_") and line is not None:
        total = home_goals + away_goals
        if Decimal(total) == line:
            return BetResult.PUSH
        over = Decimal(total) > line
        if (selection == "OVER" and over) or (selection == "UNDER" and not over):
            return BetResult.WIN
        return BetResult.LOSS
    if market_code == "BTTS":
        both = home_goals > 0 and away_goals > 0
        if (selection == "YES" and both) or (selection == "NO" and not both):
            return BetResult.WIN
        return BetResult.LOSS
    raise ValueError(f"unsupported market for settlement: {market_code}")


def compute_pnl(result: str, stake: Decimal, taken_odds: Decimal) -> Decimal:
    if result == BetResult.WIN:
        return (stake * (taken_odds - 1)).quantize(Decimal("0.01"))
    if result == BetResult.LOSS:
        return -stake
    return Decimal("0.00")  # push / void: stake returned


class BetService:
    def __init__(self, session: Session, *, initial_bankroll: Decimal) -> None:
        self._session = session
        self._bets = BetRepository(session)
        self._bankroll = BankrollRepository(session, initial_bankroll)

    def place_from_value_bet(
        self,
        value_bet_id: int,
        *,
        stake: Decimal | None = None,
        is_paper: bool = True,
        now: datetime | None = None,
    ) -> Bet:
        now = now or datetime.now(UTC)
        value_bet = self._session.get(ValueBet, value_bet_id)
        if value_bet is None:
            raise BetPlacementError(f"value bet {value_bet_id} not found")
        if value_bet.status != ValueBetStatus.CANDIDATE:
            raise BetPlacementError(
                f"value bet {value_bet_id} is {value_bet.status}, not a candidate"
            )
        match = self._session.get(Match, value_bet.match_id)
        assert match is not None
        if _as_utc(match.kickoff_utc) <= now:
            raise BetPlacementError("kickoff already passed — a late bet would corrupt CLV")
        stake = stake if stake is not None else Decimal(value_bet.suggested_stake)
        if stake <= 0:
            raise BetPlacementError("stake must be positive")
        balance = self._bankroll.current_balance(is_paper=is_paper)
        if stake > balance:
            raise BetPlacementError(f"stake {stake} exceeds bankroll {balance}")

        bet = self._bets.add(
            Bet(
                value_bet_id=value_bet.id,
                match_id=value_bet.match_id,
                market_id=value_bet.market_id,
                bookmaker_id=value_bet.bookmaker_id,
                selection=value_bet.selection,
                line=value_bet.line,
                taken_odds=value_bet.offered_odds,
                stake=stake,
                is_paper=is_paper,
                placed_at=now,
            )
        )
        value_bet.status = ValueBetStatus.PLACED
        self._bankroll.append_movement(
            balance=balance - stake, is_paper=is_paper, reason="bet_placed", bet_id=bet.id
        )
        self._session.commit()
        logger.info(
            "bets.placed",
            extra={
                "bet_id": bet.id,
                "value_bet_id": value_bet.id,
                "stake": str(stake),
                "odds": str(bet.taken_odds),
                "is_paper": is_paper,
            },
        )
        return bet

    def settle_finished(self, now: datetime | None = None) -> SettlementResult:
        now = now or datetime.now(UTC)
        settled = 0
        skipped = 0
        for bet in self._bets.list_unsettled_for_finished_matches():
            match = self._session.get(Match, bet.match_id)
            market = self._session.get(Market, bet.market_id)
            assert match is not None and market is not None
            if match.home_goals is None or match.away_goals is None:
                skipped += 1
                continue
            try:
                result = resolve_result(
                    market.code, bet.selection, bet.line, match.home_goals, match.away_goals
                )
            except ValueError:
                logger.warning(
                    "bets.settle_unsupported_market",
                    extra={"bet_id": bet.id, "market_code": market.code},
                )
                skipped += 1
                continue
            bet.result = result
            bet.pnl = compute_pnl(result, Decimal(bet.stake), Decimal(bet.taken_odds))
            bet.settled_at = now
            closing = self._closing_odds_for(bet)
            if closing is not None:
                bet.closing_odds = closing
                bet.clv = (Decimal(bet.taken_odds) / closing - 1).quantize(Decimal("0.000001"))
            balance = self._bankroll.current_balance(is_paper=bool(bet.is_paper))
            credit = Decimal(bet.stake) + Decimal(bet.pnl)
            self._bankroll.append_movement(
                balance=balance + credit,
                is_paper=bool(bet.is_paper),
                reason="bet_settled",
                bet_id=bet.id,
            )
            settled += 1
        self._session.commit()
        result_summary = SettlementResult(bets_settled=settled, bets_skipped=skipped)
        logger.info(
            "bets.settlement_completed",
            extra={"settled": settled, "skipped": skipped},
        )
        return result_summary

    def _closing_odds_for(self, bet: Bet) -> Decimal | None:
        """Closing odds of the SAME selection: same bookmaker first, any
        sharp book as fallback (spec §6.2)."""
        base = select(OddsSnapshot).where(
            OddsSnapshot.match_id == bet.match_id,
            OddsSnapshot.market_id == bet.market_id,
            OddsSnapshot.selection == bet.selection,
            OddsSnapshot.is_closing.is_(True),
        )
        if bet.line is not None:
            base = base.where(OddsSnapshot.line == bet.line)
        same_book = self._session.scalar(
            base.where(OddsSnapshot.bookmaker_id == bet.bookmaker_id).limit(1)
        )
        if same_book is not None:
            return Decimal(same_book.price_decimal)
        sharp = self._session.scalar(
            base.join(Bookmaker, Bookmaker.id == OddsSnapshot.bookmaker_id)
            .where(Bookmaker.is_sharp.is_(True))
            .limit(1)
        )
        return Decimal(sharp.price_decimal) if sharp is not None else None
