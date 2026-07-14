"""Response schemas for model predictions."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PredictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market_id: int
    market_code: str
    selection: str
    line: Decimal | None
    model_prob: Decimal
    model_version: str
    created_at: datetime


class MatchPredictionsOut(BaseModel):
    match_id: int
    predictions: list[PredictionOut]


class PredictionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_version: str
    training_matches: int
    matches_predicted: int
    matches_skipped: int
    predictions_written: int
