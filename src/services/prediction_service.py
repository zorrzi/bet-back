"""Prediction generation (Phase 2): fit Dixon-Coles on everything finished
before `now` (anti-leakage) and write versioned model_predictions.

Markets predicted per match:
- 1X2 (always)
- OU_<line> for every total-goals line the match actually has odds for
  (fallback: 2.5) — stored probabilities are P(bet WINS), so on integer
  lines the pair does not sum to 1 (push mass is real, not an error)
- BTTS (always)
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.match import Match, MatchStatus
from src.models.odds import Market, MarketCategory, OddsSnapshot
from src.models.signals import ModelPrediction
from src.repositories.odds_repository import OddsRepository
from src.repositories.prediction_repository import PredictionRepository
from src.services.modeling.dixon_coles import (
    DixonColesModel,
    TrainingMatch,
    btts_probs,
    fit_dixon_coles,
    match_result_probs,
    over_under_probs,
)
from src.utils.text import format_market_line

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PredictionRunResult:
    model_version: str
    training_matches: int
    matches_predicted: int
    matches_skipped: int
    predictions_written: int


class UnknownTeamsError(ValueError):
    """The model has no history for one of the match's teams."""


class PredictionService:
    def __init__(
        self,
        session: Session,
        *,
        xi: float,
        max_goals: int = 10,
        training_window_days: int = 1460,
    ) -> None:
        self._session = session
        self._xi = xi
        self._max_goals = max_goals
        self._training_window = timedelta(days=training_window_days)
        self._odds = OddsRepository(session)
        self._predictions = PredictionRepository(session)

    def fit(self, now: datetime | None = None) -> DixonColesModel:
        now = now or datetime.now(UTC)
        training = []
        for m in self._session.scalars(
            select(Match).where(
                Match.status == MatchStatus.FINISHED,
                Match.home_goals.is_not(None),
                Match.away_goals.is_not(None),
                Match.kickoff_utc >= now - self._training_window,
            )
        ):
            if m.home_goals is None or m.away_goals is None:  # type narrowing
                continue
            training.append(
                TrainingMatch(
                    home_team_id=m.home_team_id,
                    away_team_id=m.away_team_id,
                    home_goals=m.home_goals,
                    away_goals=m.away_goals,
                    kickoff_utc=m.kickoff_utc,
                )
            )
        return fit_dixon_coles(training, cutoff=now, xi=self._xi)

    def predict_match(self, match: Match, model: DixonColesModel) -> list[ModelPrediction]:
        if not (model.knows(match.home_team_id) and model.knows(match.away_team_id)):
            raise UnknownTeamsError(
                f"model {model.version} has no history for match {match.id} teams"
            )
        matrix = model.score_matrix(match.home_team_id, match.away_team_id, self._max_goals)
        rows: list[ModelPrediction] = []

        market_1x2 = self._odds.upsert_market(
            "1X2", "Match Result", MarketCategory.MATCH_RESULT, 3
        )
        for selection, prob in zip(
            ("HOME", "DRAW", "AWAY"), match_result_probs(matrix), strict=True
        ):
            rows.append(self._row(match.id, market_1x2.id, selection, None, prob, model))

        for line in self._ou_lines_for(match.id):
            market = self._odds.upsert_market(
                f"OU_{format_market_line(line)}",
                f"Over/Under {line}",
                MarketCategory.TOTALS,
                2,
            )
            over, under, _push = over_under_probs(matrix, float(line))
            rows.append(self._row(match.id, market.id, "OVER", line, over, model))
            rows.append(self._row(match.id, market.id, "UNDER", line, under, model))

        market_btts = self._odds.upsert_market(
            "BTTS", "Both Teams To Score", MarketCategory.BTTS, 2
        )
        yes, no = btts_probs(matrix)
        rows.append(self._row(match.id, market_btts.id, "YES", None, yes, model))
        rows.append(self._row(match.id, market_btts.id, "NO", None, no, model))

        self._predictions.replace_for_match(match.id, model.version, rows)
        return rows

    def predict_upcoming(self, now: datetime | None = None) -> PredictionRunResult:
        now = now or datetime.now(UTC)
        model = self.fit(now)
        upcoming = list(
            self._session.scalars(
                select(Match).where(
                    Match.status == MatchStatus.SCHEDULED,
                    Match.kickoff_utc > now,
                )
            )
        )
        predicted = 0
        skipped = 0
        written = 0
        for match in upcoming:
            try:
                written += len(self.predict_match(match, model))
                predicted += 1
            except UnknownTeamsError:
                logger.warning(
                    "prediction.match_skipped_unknown_teams",
                    extra={"match_id": match.id},
                )
                skipped += 1
        self._session.commit()
        result = PredictionRunResult(
            model_version=model.version,
            training_matches=model.n_matches,
            matches_predicted=predicted,
            matches_skipped=skipped,
            predictions_written=written,
        )
        logger.info(
            "prediction.run_completed",
            extra={
                "model_version": result.model_version,
                "training_matches": result.training_matches,
                "matches_predicted": result.matches_predicted,
                "matches_skipped": result.matches_skipped,
                "predictions_written": result.predictions_written,
            },
        )
        return result

    def _ou_lines_for(self, match_id: int) -> list[Decimal]:
        # quarter lines (2.25/2.75) are SPLIT bets (half stake on each
        # adjacent half-line); a single P(bet wins) misrepresents them, so
        # they are excluded here — Phase 3 prices them by decomposition
        lines = sorted(
            {
                line
                for line in self._session.scalars(
                    select(OddsSnapshot.line)
                    .join(Market, Market.id == OddsSnapshot.market_id)
                    .where(
                        OddsSnapshot.match_id == match_id,
                        Market.category == MarketCategory.TOTALS,
                        OddsSnapshot.line.is_not(None),
                    )
                    .distinct()
                )
                if line is not None and line % Decimal("0.5") == 0
            }
        )
        return lines or [Decimal("2.5")]

    def _row(
        self,
        match_id: int,
        market_id: int,
        selection: str,
        line: Decimal | None,
        probability: float,
        model: DixonColesModel,
    ) -> ModelPrediction:
        return PredictionRepository.build_row(
            match_id=match_id,
            market_id=market_id,
            selection=selection,
            line=line,
            probability=probability,
            model_version=model.version,
        )
