"""Model predictions and value-bet signals (spec §4.3).

A value bet only exists when the model's probability beats the de-vigged
market probability with positive EV (edge > 0). No value → no bet.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database.database import Base


class ModelPrediction(Base):
    __tablename__ = "model_predictions"
    __table_args__ = (Index("ix_model_predictions_match_market", "match_id", "market_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"))
    selection: Mapped[str] = mapped_column(Text)
    line: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    model_prob: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    # always versioned, e.g. 'dixoncoles_v1' — backtests compare versions
    model_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ValueBetStatus:
    CANDIDATE = "candidate"
    PLACED = "placed"
    SKIPPED = "skipped"
    EXPIRED = "expired"


class ValueBet(Base):
    __tablename__ = "value_bets"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"))
    bookmaker_id: Mapped[int] = mapped_column(ForeignKey("bookmakers.id"))
    selection: Mapped[str] = mapped_column(Text)
    line: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    model_prob: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    # market probability after de-vig of the sharp line
    fair_prob: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    offered_odds: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    # EV per unit staked: model_prob * offered_odds - 1
    edge: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    kelly_fraction: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    suggested_stake: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    model_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(Text, default=ValueBetStatus.CANDIDATE)
