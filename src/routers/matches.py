"""Match routes: listing, odds history and model predictions (spec §8)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config.security import require_api_key
from src.config.settings import Settings, get_settings
from src.database.database import get_db
from src.models.odds import Bookmaker, Market
from src.repositories.match_repository import MatchRepository
from src.repositories.odds_repository import OddsRepository
from src.repositories.prediction_repository import PredictionRepository
from src.schemas.matches import (
    BookmakerOut,
    MarketOut,
    MatchOddsOut,
    MatchOut,
    OddsSnapshotOut,
    PaginatedMatches,
)
from src.schemas.predictions import MatchPredictionsOut, PredictionOut
from src.services.modeling.dixon_coles import NotEnoughDataError
from src.services.prediction_service import PredictionService, UnknownTeamsError

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("", response_model=PaginatedMatches)
def list_matches(
    league_id: int | None = None,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PaginatedMatches:
    matches = MatchRepository(db).list_matches(
        league_id=league_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return PaginatedMatches(
        items=[MatchOut.model_validate(m) for m in matches], limit=limit, offset=offset
    )


@router.get("/{match_id}", response_model=MatchOut)
def get_match(match_id: int, db: Session = Depends(get_db)) -> MatchOut:
    match = MatchRepository(db).get(match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found.")
    return MatchOut.model_validate(match)


def _predictions_out(db: Session, match_id: int) -> MatchPredictionsOut:
    rows = PredictionRepository(db).list_for_match(match_id)
    market_ids = {r.market_id for r in rows}
    codes = {m.id: m.code for m in db.scalars(select(Market).where(Market.id.in_(market_ids)))}
    return MatchPredictionsOut(
        match_id=match_id,
        predictions=[
            PredictionOut(
                id=r.id,
                market_id=r.market_id,
                market_code=codes.get(r.market_id, "?"),
                selection=r.selection,
                line=r.line,
                model_prob=r.model_prob,
                model_version=r.model_version,
                created_at=r.created_at,
            )
            for r in rows
        ],
    )


@router.post(
    "/{match_id}/predict",
    response_model=MatchPredictionsOut,
    dependencies=[Depends(require_api_key)],
)
def predict_match(
    match_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MatchPredictionsOut:
    match = MatchRepository(db).get(match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found.")
    service = PredictionService(
        db,
        xi=settings.dc_xi,
        max_goals=settings.dc_max_goals,
        training_window_days=settings.dc_training_window_days,
    )
    try:
        model = service.fit(datetime.now(UTC))
        service.predict_match(match, model)
    except NotEnoughDataError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UnknownTeamsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _predictions_out(db, match_id)


@router.get("/{match_id}/predictions", response_model=MatchPredictionsOut)
def get_match_predictions(match_id: int, db: Session = Depends(get_db)) -> MatchPredictionsOut:
    if MatchRepository(db).get(match_id) is None:
        raise HTTPException(status_code=404, detail="Match not found.")
    return _predictions_out(db, match_id)


@router.get("/{match_id}/odds", response_model=MatchOddsOut)
def get_match_odds(match_id: int, db: Session = Depends(get_db)) -> MatchOddsOut:
    match = MatchRepository(db).get(match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found.")
    snapshots = OddsRepository(db).list_snapshots_for_match(match_id)
    bookmaker_ids = {s.bookmaker_id for s in snapshots}
    market_ids = {s.market_id for s in snapshots}
    bookmakers = db.scalars(
        select(Bookmaker).where(Bookmaker.id.in_(bookmaker_ids)).order_by(Bookmaker.id)
    )
    markets = db.scalars(select(Market).where(Market.id.in_(market_ids)).order_by(Market.id))
    return MatchOddsOut(
        match_id=match_id,
        bookmakers=[BookmakerOut.model_validate(b) for b in bookmakers],
        markets=[MarketOut.model_validate(m) for m in markets],
        snapshots=[OddsSnapshotOut.model_validate(s) for s in snapshots],
    )
