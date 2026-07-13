"""Internal job routes (spec §8) — triggered by the scheduler or manually.

All of them mutate state, so they sit behind the API key (spec §11.1).
Provider failures surface as 502 (upstream), not opaque 500s.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.config.security import require_api_key
from src.config.settings import Settings, get_settings
from src.database.database import get_db
from src.providers.api_football import ApiFootballProvider
from src.providers.http import ProviderError
from src.providers.the_odds_api import TheOddsApiProvider
from src.schemas.jobs import (
    ClosingMarkOut,
    FixtureIngestionOut,
    OddsIngestionOut,
    ResultsIngestionOut,
)
from src.services.closing_service import ClosingService
from src.services.fixture_ingestion_service import (
    FixtureIngestionResult,
    FixtureIngestionService,
)
from src.services.odds_ingestion_service import OddsIngestionResult, OddsIngestionService
from src.services.results_ingestion_service import (
    ResultsIngestionResult,
    ResultsIngestionService,
)

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_api_key)])

_UPSTREAM_ERRORS = (ProviderError, httpx.HTTPError)


@router.post("/ingest/fixtures", response_model=FixtureIngestionOut)
def ingest_fixtures(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FixtureIngestionResult:
    service = FixtureIngestionService(db, ApiFootballProvider(settings))
    try:
        return service.ingest_league_season(
            settings.ingest_league_provider_id, settings.ingest_season
        )
    except _UPSTREAM_ERRORS as exc:
        raise HTTPException(status_code=502, detail="Fixture provider error.") from exc


@router.post("/ingest/odds", response_model=OddsIngestionOut)
def ingest_odds(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OddsIngestionResult:
    service = OddsIngestionService(
        db,
        TheOddsApiProvider(settings),
        settings.sharp_bookmaker_set,
        autocreate_matches=settings.odds_autocreate_matches,
        season=settings.ingest_season,
    )
    try:
        return service.ingest_current_odds(
            settings.odds_sport_key, settings.odds_regions, settings.odds_markets
        )
    except _UPSTREAM_ERRORS as exc:
        raise HTTPException(status_code=502, detail="Odds provider error.") from exc


@router.post("/ingest/scores", response_model=ResultsIngestionOut)
def ingest_scores(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ResultsIngestionResult:
    service = ResultsIngestionService(db, TheOddsApiProvider(settings))
    try:
        return service.ingest_scores(settings.odds_sport_key, settings.scores_days_from)
    except _UPSTREAM_ERRORS as exc:
        raise HTTPException(status_code=502, detail="Scores provider error.") from exc


@router.post("/mark-closing", response_model=ClosingMarkOut)
def mark_closing(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ClosingMarkOut:
    result = ClosingService(db, settings.closing_lookback_days).mark_closing_lines()
    return ClosingMarkOut.model_validate(result)
