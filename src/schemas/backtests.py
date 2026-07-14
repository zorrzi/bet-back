"""Request/response schemas for backtests. CLV fields lead the summary."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BacktestCreateIn(BaseModel):
    name: str = "backtest"
    date_from: date
    date_to: date
    min_edge: float | None = Field(default=None, ge=0)
    kelly_multiplier: float | None = Field(default=None, gt=0, le=1)
    max_stake_pct: float | None = Field(default=None, gt=0, le=1)
    devig_method: str | None = None
    initial_bankroll: float | None = Field(default=None, gt=0)
    refit_days: int = Field(default=30, ge=1, le=365)
    # market shrinkage weight: 1.0 = raw model (v1), lower = closer to market
    blend_weight: float | None = Field(default=None, ge=0, le=1)
    # run in-request instead of in a background thread (tests / small ranges)
    synchronous: bool = False


class BacktestSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    model_version: str
    date_from: date
    date_to: date
    # CLV first (spec §6.2) — profit metrics after
    avg_clv: Decimal | None
    pct_positive_clv: Decimal | None
    n_bets: int | None
    roi: Decimal | None
    total_pnl: Decimal | None
    max_drawdown: Decimal | None
    sharpe: Decimal | None
    params: dict[str, Any]
    created_at: datetime


class BacktestDetailOut(BacktestSummaryOut):
    detail: dict[str, Any] | None
