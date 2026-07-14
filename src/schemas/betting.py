"""Request/response schemas for value bets, bets and bankroll."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ValueBetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    match_id: int
    market_id: int
    bookmaker_id: int
    selection: str
    line: Decimal | None
    model_prob: Decimal
    fair_prob: Decimal
    offered_odds: Decimal
    edge: Decimal
    kelly_fraction: Decimal
    suggested_stake: Decimal
    model_version: str
    status: str
    created_at: datetime


class PaginatedValueBets(BaseModel):
    items: list[ValueBetOut]
    limit: int
    offset: int


class SignalGenerationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    matches_scanned: int
    signals_created: int
    candidates_expired: int


class BetPlaceIn(BaseModel):
    value_bet_id: int
    stake: Decimal | None = Field(default=None, gt=0)
    is_paper: bool = True


class BetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    value_bet_id: int | None
    match_id: int
    market_id: int
    bookmaker_id: int
    selection: str
    line: Decimal | None
    taken_odds: Decimal
    stake: Decimal
    is_paper: bool
    placed_at: datetime
    result: str | None
    pnl: Decimal | None
    closing_odds: Decimal | None
    clv: Decimal | None
    settled_at: datetime | None


class PaginatedBets(BaseModel):
    items: list[BetOut]
    limit: int
    offset: int


class SettlementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bets_settled: int
    bets_skipped: int


class BankrollPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    balance: Decimal
    reason: str
    bet_id: int | None
    created_at: datetime


class BankrollOut(BaseModel):
    balance: Decimal
    is_paper: bool
    history: list[BankrollPointOut]
