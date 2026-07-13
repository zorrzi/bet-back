"""Response schemas for match and odds routes."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    league_id: int
    home_team: TeamOut
    away_team: TeamOut
    kickoff_utc: datetime
    status: str
    home_goals: int | None
    away_goals: int | None


class PaginatedMatches(BaseModel):
    items: list[MatchOut]
    limit: int
    offset: int


class OddsSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bookmaker_id: int
    market_id: int
    selection: str
    line: Decimal | None
    price_decimal: Decimal
    captured_at: datetime
    is_closing: bool


class MarketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    category: str
    n_selections: int


class BookmakerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_sharp: bool


class MatchOddsOut(BaseModel):
    match_id: int
    bookmakers: list[BookmakerOut]
    markets: list[MarketOut]
    snapshots: list[OddsSnapshotOut]
