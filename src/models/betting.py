"""Bets (paper or real), bankroll history and backtest runs (spec §4.3).

`bets.placed_at` must be before the match kickoff — enforced at the service
layer; a bet recorded after kickoff would poison every CLV number downstream.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from src.database.database import Base


class BetResult:
    WIN = "win"
    LOSS = "loss"
    PUSH = "push"
    VOID = "void"


class Bet(Base):
    __tablename__ = "bets"

    id: Mapped[int] = mapped_column(primary_key=True)
    value_bet_id: Mapped[int | None] = mapped_column(ForeignKey("value_bets.id"))
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"))
    bookmaker_id: Mapped[int] = mapped_column(ForeignKey("bookmakers.id"))
    selection: Mapped[str] = mapped_column(Text)
    line: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    # the odds actually taken when the bet was recorded
    taken_odds: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    stake: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # settled after the result is known:
    result: Mapped[str | None] = mapped_column(Text)
    pnl: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    # closing odds of the SAME selection (basis for CLV, spec §6.2)
    closing_odds: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    clv: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BankrollHistory(Base):
    __tablename__ = "bankroll_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True)
    # 'bet_placed' | 'bet_settled' | 'deposit' | ...
    reason: Mapped[str] = mapped_column(Text)
    bet_id: Mapped[int | None] = mapped_column(ForeignKey("bets.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(Text)
    # kelly_fraction, min_edge, leagues, de-vig method, ...
    params: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(postgresql.JSONB(), "postgresql")
    )
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    # summary metrics — CLV first, profit second (spec §6.2):
    n_bets: Mapped[int | None] = mapped_column(Integer)
    avg_clv: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    pct_positive_clv: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    roi: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    total_pnl: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    sharpe: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
