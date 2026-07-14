"""Data access for model predictions.

Predictions are derived data (unlike odds, which are history): re-running a
model version for a match REPLACES its previous rows, keeping downstream
consumers free of duplicates. Backtests refit and regenerate their own
predictions, so nothing is lost by replacing."""

from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.models.signals import ModelPrediction


class PredictionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_for_match(
        self, match_id: int, model_version: str, rows: list[ModelPrediction]
    ) -> int:
        self._session.execute(
            delete(ModelPrediction).where(
                ModelPrediction.match_id == match_id,
                ModelPrediction.model_version == model_version,
            )
        )
        self._session.add_all(rows)
        return len(rows)

    def list_for_match(self, match_id: int) -> list[ModelPrediction]:
        return list(
            self._session.scalars(
                select(ModelPrediction)
                .where(ModelPrediction.match_id == match_id)
                .order_by(ModelPrediction.market_id, ModelPrediction.selection)
            )
        )

    @staticmethod
    def build_row(
        *,
        match_id: int,
        market_id: int,
        selection: str,
        line: Decimal | None,
        probability: float,
        model_version: str,
    ) -> ModelPrediction:
        return ModelPrediction(
            match_id=match_id,
            market_id=market_id,
            selection=selection,
            line=line,
            model_prob=Decimal(f"{probability:.6f}"),
            model_version=model_version,
        )
