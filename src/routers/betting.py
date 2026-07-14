"""Value-bet feed, paper bets and bankroll routes (spec §8, Fase 3)."""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.config.security import require_api_key
from src.config.settings import Settings, get_settings
from src.database.database import get_db
from src.repositories.betting_repository import (
    BankrollRepository,
    BetRepository,
    ValueBetRepository,
)
from src.schemas.betting import (
    BankrollOut,
    BankrollPointOut,
    BetOut,
    BetPlaceIn,
    PaginatedBets,
    PaginatedValueBets,
    ValueBetOut,
)
from src.services.bet_service import BetPlacementError, BetService

router = APIRouter(tags=["betting"])


@router.get("/value-bets", response_model=PaginatedValueBets)
def list_value_bets(
    status: str | None = "candidate",
    min_edge: float | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PaginatedValueBets:
    rows = ValueBetRepository(db).list_value_bets(
        status=status,
        min_edge=min_edge,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return PaginatedValueBets(
        items=[ValueBetOut.model_validate(r) for r in rows], limit=limit, offset=offset
    )


@router.post("/bets", response_model=BetOut, dependencies=[Depends(require_api_key)])
def place_bet(
    body: BetPlaceIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BetOut:
    service = BetService(db, initial_bankroll=Decimal(str(settings.initial_bankroll)))
    try:
        bet = service.place_from_value_bet(
            body.value_bet_id, stake=body.stake, is_paper=body.is_paper
        )
    except BetPlacementError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BetOut.model_validate(bet)


@router.get("/bets", response_model=PaginatedBets)
def list_bets(
    is_paper: bool | None = None,
    settled: bool | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PaginatedBets:
    rows = BetRepository(db).list_bets(
        is_paper=is_paper, settled=settled, limit=limit, offset=offset
    )
    return PaginatedBets(
        items=[BetOut.model_validate(r) for r in rows], limit=limit, offset=offset
    )


@router.get("/bankroll", response_model=BankrollOut)
def get_bankroll(
    is_paper: bool = True,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BankrollOut:
    repo = BankrollRepository(db, Decimal(str(settings.initial_bankroll)))
    balance = repo.current_balance(is_paper=is_paper)
    db.commit()  # persists the lazy initial deposit on first access
    return BankrollOut(
        balance=balance,
        is_paper=is_paper,
        history=[BankrollPointOut.model_validate(h) for h in repo.history(is_paper)],
    )
