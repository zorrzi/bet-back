"""Data access for value bets, bets and the bankroll ledger.

The bankroll is an append-only ledger (bankroll_history): the current
balance is the latest row's balance; every movement writes a new row with
its reason. Money is Decimal end to end.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.models.betting import BankrollHistory, Bet
from src.models.match import Match
from src.models.signals import ValueBet, ValueBetStatus


class ValueBetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, value_bet: ValueBet) -> ValueBet:
        self._session.add(value_bet)
        return value_bet

    def get(self, value_bet_id: int) -> ValueBet | None:
        return self._session.get(ValueBet, value_bet_id)

    def expire_candidates_for_match(self, match_id: int) -> int:
        """Supersede previous open signals before regenerating."""
        result = self._session.execute(
            update(ValueBet)
            .where(
                ValueBet.match_id == match_id,
                ValueBet.status == ValueBetStatus.CANDIDATE,
            )
            .values(status=ValueBetStatus.EXPIRED)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def list_value_bets(
        self,
        *,
        status: str | None = None,
        min_edge: float | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ValueBet]:
        query = (
            select(ValueBet)
            .join(Match, Match.id == ValueBet.match_id)
            .order_by(ValueBet.edge.desc())
        )
        if status is not None:
            query = query.where(ValueBet.status == status)
        if min_edge is not None:
            query = query.where(ValueBet.edge >= Decimal(str(min_edge)))
        if date_from is not None:
            query = query.where(Match.kickoff_utc >= date_from)
        if date_to is not None:
            query = query.where(Match.kickoff_utc <= date_to)
        return list(self._session.scalars(query.limit(limit).offset(offset)))


class BetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, bet: Bet) -> Bet:
        self._session.add(bet)
        self._session.flush()
        return bet

    def list_bets(
        self,
        *,
        is_paper: bool | None = None,
        settled: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Bet]:
        query = select(Bet).order_by(Bet.placed_at.desc())
        if is_paper is not None:
            query = query.where(Bet.is_paper.is_(is_paper))
        if settled is True:
            query = query.where(Bet.result.is_not(None))
        elif settled is False:
            query = query.where(Bet.result.is_(None))
        return list(self._session.scalars(query.limit(limit).offset(offset)))

    def list_unsettled_for_finished_matches(self) -> list[Bet]:
        from src.models.match import MatchStatus

        return list(
            self._session.scalars(
                select(Bet)
                .join(Match, Match.id == Bet.match_id)
                .where(Bet.result.is_(None), Match.status == MatchStatus.FINISHED)
            )
        )


class BankrollRepository:
    def __init__(self, session: Session, initial_bankroll: Decimal) -> None:
        self._session = session
        self._initial = initial_bankroll

    def current_balance(self, is_paper: bool = True) -> Decimal:
        latest = self._session.scalar(
            select(BankrollHistory)
            .where(BankrollHistory.is_paper.is_(is_paper))
            .order_by(BankrollHistory.id.desc())
            .limit(1)
        )
        if latest is None:
            seeded = BankrollHistory(balance=self._initial, is_paper=is_paper, reason="deposit")
            self._session.add(seeded)
            self._session.flush()
            return Decimal(seeded.balance)
        return Decimal(latest.balance)

    def append_movement(
        self, *, balance: Decimal, is_paper: bool, reason: str, bet_id: int | None
    ) -> BankrollHistory:
        row = BankrollHistory(balance=balance, is_paper=is_paper, reason=reason, bet_id=bet_id)
        self._session.add(row)
        self._session.flush()
        return row

    def history(self, is_paper: bool = True, limit: int = 500) -> list[BankrollHistory]:
        return list(
            self._session.scalars(
                select(BankrollHistory)
                .where(BankrollHistory.is_paper.is_(is_paper))
                .order_by(BankrollHistory.id)
                .limit(limit)
            )
        )
