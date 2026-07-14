"""Bookmakers, markets and odds snapshots — the heart of the system (spec §4.2).

GOLDEN RULE: `odds_snapshots` is APPEND-ONLY. Prices are never updated in
place; every capture inserts a new row with its own `captured_at`. This is
what makes CLV computable honestly. The only permitted mutation is flipping
`is_closing` on the latest pre-kickoff snapshot (mark-closing job).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.database.database import Base


class Bookmaker(Base):
    __tablename__ = "bookmakers"
    __table_args__ = (UniqueConstraint("provider_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    # sharp book (Pinnacle): reference line for de-vig and CLV
    is_sharp: Mapped[bool] = mapped_column(Boolean, default=False)


class MarketCategory:
    MATCH_RESULT = "match_result"
    TOTALS = "totals"
    HANDICAP = "handicap"
    BTTS = "btts"
    PLAYER_PROP = "player_prop"


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(primary_key=True)
    # e.g. '1X2', 'OU_2_5', 'AH_-0_5' — the line is part of the code
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    # number of selections in the market, needed for de-vig (1X2=3, OU=2)
    n_selections: Mapped[int] = mapped_column(Integer)


class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"
    __table_args__ = (
        Index(
            "ix_odds_snapshots_lookup",
            "match_id",
            "market_id",
            "bookmaker_id",
            "captured_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    bookmaker_id: Mapped[int] = mapped_column(ForeignKey("bookmakers.id"))
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"))
    # 'HOME' | 'DRAW' | 'AWAY' | 'OVER' | 'UNDER' | player_id as text | ...
    selection: Mapped[str] = mapped_column(Text)
    line: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    price_decimal: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_closing: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
