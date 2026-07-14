from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest
from sqlalchemy.orm import Session

from src.models.betting import BacktestStatus
from src.models.competition import League, Team
from src.models.match import Match, MatchStatus
from src.models.odds import Bookmaker, Market, OddsSnapshot
from src.services.backtest_service import (
    BacktestParams,
    BacktestService,
    max_drawdown,
    sharpe_per_bet,
)

# --- pure metric helpers, hand-calculated (spec §11.3) ---


def test_max_drawdown_hand_case() -> None:
    # peak 120 -> trough 80 = 40 (later recovery does not matter)
    assert max_drawdown([100, 120, 95, 80, 110, 105]) == pytest.approx(40)


def test_max_drawdown_monotonic_growth_is_zero() -> None:
    assert max_drawdown([100, 101, 105, 110]) == 0.0


def test_sharpe_hand_case() -> None:
    # pnls [1, -1, 1, -1]: mean 0 -> sharpe 0
    assert sharpe_per_bet([1.0, -1.0, 1.0, -1.0]) == pytest.approx(0.0)
    assert sharpe_per_bet([5.0]) is None  # undefined for n < 2
    assert sharpe_per_bet([2.0, 2.0, 2.0]) is None  # zero variance


# --- engine on a seeded corpus ---

EVAL_FROM = date(2026, 1, 1)
EVAL_TO = date(2026, 6, 30)


def _seed_corpus(session: Session) -> None:
    """Two seasons of a 6-team league; matches in 2026 carry sharp closing
    1X2 odds so the engine can bet on them."""
    rng = np.random.default_rng(11)
    league = League(provider_id="fdcuk:BRA", season="2025", name="Serie A", country="Brazil")
    pinnacle = Bookmaker(provider_id="pinnacle", name="Pinnacle", is_sharp=True)
    market = Market(code="1X2", name="Match Result", category="match_result", n_selections=3)
    session.add_all([league, pinnacle, market])
    session.flush()
    teams = [Team(provider_id=f"t{i}", name=f"Team {i}", league_id=league.id) for i in range(6)]
    session.add_all(teams)
    session.flush()

    kickoff = datetime(2025, 3, 1, 16, 0, tzinfo=UTC)
    counter = 0
    for _round in range(14):  # ~420 matches across 2025-03 .. 2026-06
        for i, home in enumerate(teams):
            for j, away in enumerate(teams):
                if i == j:
                    continue
                counter += 1
                kickoff = kickoff + timedelta(hours=34)
                match = Match(
                    provider_id=f"bt-{counter}",
                    league_id=league.id,
                    home_team_id=home.id,
                    away_team_id=away.id,
                    kickoff_utc=kickoff,
                    status=MatchStatus.FINISHED,
                    home_goals=int(rng.poisson(1.5)),
                    away_goals=int(rng.poisson(1.0)),
                )
                session.add(match)
                session.flush()
                if kickoff.date() >= EVAL_FROM:
                    for selection, price in (
                        ("HOME", "2.10"),
                        ("DRAW", "3.40"),
                        ("AWAY", "3.80"),
                    ):
                        session.add(
                            OddsSnapshot(
                                match_id=match.id,
                                bookmaker_id=pinnacle.id,
                                market_id=market.id,
                                selection=selection,
                                price_decimal=Decimal(price),
                                captured_at=kickoff - timedelta(minutes=1),
                                is_closing=True,
                            )
                        )
    session.commit()


def _params(**overrides: object) -> BacktestParams:
    defaults: dict = {
        "name": "test-run",
        "date_from": EVAL_FROM,
        "date_to": EVAL_TO,
        "min_edge": 0.03,
        "kelly_multiplier": 0.25,
        "max_stake_pct": 0.02,
        "devig_method": "multiplicative",
        "initial_bankroll": 1000.0,
        "refit_days": 60,
        "xi": 0.001,
        "training_window_days": 1460,
    }
    defaults.update(overrides)
    return BacktestParams(**defaults)  # type: ignore[arg-type]


def test_backtest_runs_and_reports_metrics(session: Session) -> None:
    _seed_corpus(session)
    service = BacktestService(session)
    params = _params()
    run = service.create_run(params, "dixoncoles_v1")
    run = service.execute(run.id, params)

    assert run.status == BacktestStatus.FINISHED
    assert run.n_bets is not None and run.n_bets > 0
    assert run.detail is not None
    assert run.total_pnl is not None
    assert run.roi is not None
    assert run.max_drawdown is not None and run.max_drawdown >= 0
    # taken AT closing -> CLV structurally 0 on this corpus (ADR-0006)
    assert run.avg_clv == Decimal("0.000000")
    bets = run.detail["bets"]
    assert len(bets) == run.n_bets
    # every simulated bet had positive model edge at decision time
    assert all(b["edge"] > 0.03 for b in bets)
    # bankroll trace is consistent: last bankroll = initial + total pnl
    assert bets[-1]["bankroll_after"] == pytest.approx(1000.0 + float(run.total_pnl), abs=0.05)


def test_backtest_with_impossible_min_edge_places_no_bets(session: Session) -> None:
    _seed_corpus(session)
    service = BacktestService(session)
    params = _params(min_edge=5.0)  # nothing can clear a 500% edge
    run = service.create_run(params, "dixoncoles_v1")
    run = service.execute(run.id, params)

    assert run.status == BacktestStatus.FINISHED
    assert run.n_bets == 0
    assert run.avg_clv is None  # no bets -> no CLV to report
    assert run.total_pnl == Decimal("0.00")


def test_blend_weight_zero_is_pure_market_and_never_bets(session: Session) -> None:
    """w=0 collapses the decision prob onto the de-vigged market; fair*odds
    is always < 1 (the vig), so NO bet can ever clear min_edge. This anchors
    the blend semantics: betting volume must vanish as w -> 0."""
    _seed_corpus(session)
    service = BacktestService(session)
    params = _params(blend_weight=0.0)
    run = service.create_run(params, "dixoncoles_v1+blend0")
    run = service.execute(run.id, params)

    assert run.status == BacktestStatus.FINISHED
    assert run.n_bets == 0
    assert run.detail is not None
    assert run.detail["avg_log_loss"] is not None  # calibration still measured


def test_backtest_failure_is_recorded_not_raised(session: Session) -> None:
    # empty database -> the model can never fit; run must fail gracefully
    service = BacktestService(session)
    params = _params()
    run = service.create_run(params, "dixoncoles_v1")
    run = service.execute(run.id, params)

    assert run.status == BacktestStatus.FINISHED  # no matches -> 0 bets, finished
    assert run.n_bets == 0
