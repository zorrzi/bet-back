"""Backtest routes (spec §8). POST is asynchronous by default: it creates
the run (status=running), spawns a worker thread with its own session, and
returns immediately; GET polls status and results."""

import logging
import threading

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config.security import require_api_key
from src.config.settings import Settings, get_settings
from src.database.database import get_db, get_session_factory
from src.models.betting import BacktestRun
from src.schemas.backtests import BacktestCreateIn, BacktestDetailOut, BacktestSummaryOut
from src.services.backtest_service import BacktestParams, BacktestService
from src.services.modeling.dixon_coles import MODEL_VERSION

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtests", tags=["backtests"])


def _params_from(body: BacktestCreateIn, settings: Settings) -> BacktestParams:
    return BacktestParams(
        name=body.name,
        date_from=body.date_from,
        date_to=body.date_to,
        min_edge=body.min_edge if body.min_edge is not None else settings.min_edge,
        kelly_multiplier=body.kelly_multiplier or settings.kelly_multiplier,
        max_stake_pct=body.max_stake_pct or settings.max_stake_pct,
        devig_method=body.devig_method or settings.devig_method,
        initial_bankroll=body.initial_bankroll or settings.initial_bankroll,
        refit_days=body.refit_days,
        xi=settings.dc_xi,
        training_window_days=settings.dc_training_window_days,
    )


def _run_in_thread(run_id: int, params: BacktestParams) -> None:
    session = get_session_factory()()
    try:
        BacktestService(session).execute(run_id, params)
    finally:
        session.close()


@router.post(
    "",
    response_model=BacktestSummaryOut,
    dependencies=[Depends(require_api_key)],
    status_code=202,
)
def create_backtest(
    body: BacktestCreateIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BacktestRun:
    if body.date_from >= body.date_to:
        raise HTTPException(status_code=422, detail="date_from must precede date_to.")
    params = _params_from(body, settings)
    service = BacktestService(db)
    run = service.create_run(params, MODEL_VERSION)
    if body.synchronous:
        return service.execute(run.id, params)
    thread = threading.Thread(
        target=_run_in_thread, args=(run.id, params), daemon=True, name=f"backtest-{run.id}"
    )
    thread.start()
    logger.info("backtest.started", extra={"run_id": run.id, "async": True})
    return run


@router.get("", response_model=list[BacktestSummaryOut])
def list_backtests(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[BacktestRun]:
    return list(
        db.scalars(
            select(BacktestRun).order_by(BacktestRun.id.desc()).limit(limit).offset(offset)
        )
    )


@router.get("/{run_id}", response_model=BacktestDetailOut)
def get_backtest(run_id: int, db: Session = Depends(get_db)) -> BacktestRun:
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest not found.")
    return run
