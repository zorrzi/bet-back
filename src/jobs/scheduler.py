"""Periodic ingestion jobs (APScheduler — spec §2 MVP choice).

Runs inside the API process, gated by SCHEDULER_ENABLED so local dev and
tests never fire real provider calls by accident. Each job run gets its own
session (always closed) and never lets an exception kill the scheduler.
"""

import logging
from collections.abc import Callable
from decimal import Decimal

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from src.config.settings import Settings
from src.database.database import get_session_factory
from src.providers.api_football import ApiFootballProvider
from src.providers.the_odds_api import TheOddsApiProvider
from src.services.bet_service import BetService
from src.services.closing_service import ClosingService
from src.services.fixture_ingestion_service import FixtureIngestionService
from src.services.odds_ingestion_service import OddsIngestionService
from src.services.results_ingestion_service import ResultsIngestionService
from src.services.value_bet_service import ValueBetService

logger = logging.getLogger(__name__)


def _run_job(name: str, work: Callable[[Session], object]) -> None:
    session = get_session_factory()()
    try:
        work(session)
    except Exception:
        logger.exception(f"scheduler.{name}_failed")
        session.rollback()
    finally:
        session.close()


def _ingest_fixtures(settings: Settings) -> None:
    _run_job(
        "ingest_fixtures",
        lambda session: FixtureIngestionService(
            session, ApiFootballProvider(settings)
        ).ingest_league_season(settings.ingest_league_provider_id, settings.ingest_season),
    )


def _ingest_odds(settings: Settings) -> None:
    _run_job(
        "ingest_odds",
        lambda session: OddsIngestionService(
            session,
            TheOddsApiProvider(settings),
            settings.sharp_bookmaker_set,
            autocreate_matches=settings.odds_autocreate_matches,
            season=settings.ingest_season,
        ).ingest_current_odds(
            settings.odds_sport_key, settings.odds_regions, settings.odds_markets
        ),
    )


def _ingest_scores(settings: Settings) -> None:
    _run_job(
        "ingest_scores",
        lambda session: ResultsIngestionService(
            session, TheOddsApiProvider(settings)
        ).ingest_scores(settings.odds_sport_key, settings.scores_days_from),
    )


def _mark_closing(settings: Settings) -> None:
    _run_job(
        "mark_closing",
        lambda session: ClosingService(
            session, settings.closing_lookback_days
        ).mark_closing_lines(),
    )


def _generate_signals(settings: Settings) -> None:
    _run_job(
        "generate_signals",
        lambda session: ValueBetService(
            session,
            min_edge=settings.min_edge,
            kelly_multiplier=settings.kelly_multiplier,
            max_stake_pct=settings.max_stake_pct,
            devig_method=settings.devig_method,
            initial_bankroll=Decimal(str(settings.initial_bankroll)),
            blend_weight=settings.model_blend_weight,
        ).generate_signals(),
    )


def _settle(settings: Settings) -> None:
    _run_job(
        "settle",
        lambda session: BetService(
            session, initial_bankroll=Decimal(str(settings.initial_bankroll))
        ).settle_finished(),
    )


def build_scheduler(settings: Settings) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    if not settings.odds_autocreate_matches:
        # with autocreate on, The Odds API is the fixture source and polling
        # API-Football (blind to current seasons on the free plan) would just
        # fail every run (ADR-0004)
        scheduler.add_job(
            _ingest_fixtures,
            "interval",
            minutes=settings.fixtures_poll_minutes,
            args=[settings],
            id="ingest_fixtures",
        )
    scheduler.add_job(
        _ingest_odds,
        "interval",
        minutes=settings.odds_poll_minutes,
        args=[settings],
        id="ingest_odds",
    )
    scheduler.add_job(
        _ingest_scores,
        "interval",
        minutes=settings.scores_poll_minutes,
        args=[settings],
        id="ingest_scores",
    )
    scheduler.add_job(
        _mark_closing,
        "interval",
        minutes=settings.closing_poll_minutes,
        args=[settings],
        id="mark_closing",
    )
    scheduler.add_job(
        _generate_signals,
        "interval",
        minutes=settings.odds_poll_minutes,  # refresh signals at odds cadence
        args=[settings],
        id="generate_signals",
    )
    scheduler.add_job(
        _settle,
        "interval",
        minutes=settings.settle_poll_minutes,
        args=[settings],
        id="settle",
    )
    return scheduler
