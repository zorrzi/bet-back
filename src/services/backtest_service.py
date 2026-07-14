"""Chronological backtest with CLV-first reporting (spec §6, Fase 4).

The three rules of §6.1, enforced by construction:

1. **No future information.** The model is refit "as of" each decision date
   (fit cutoff = the match's kickoff; only earlier matches enter), and the
   only prices used are that match's own closing snapshots.
2. **Out-of-sample by design.** The evaluated window [date_from, date_to]
   never trains the model that bets on it — each match's fit saw only
   matches strictly before its kickoff.
3. **Profit is secondary.** Metrics are reported CLV first. NOTE (ADR-0006):
   the historical corpus carries CLOSING odds only, so simulated bets are
   taken AT the closing price and their CLV is structurally 0 — the
   discriminating number for THIS dataset is ROI against the closing line
   (a stricter test: profiting at the sharpest price). CLV becomes a live
   metric in paper trading, where pre-closing captures exist.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.betting import BacktestRun, BacktestStatus
from src.models.match import Match, MatchStatus
from src.models.odds import Bookmaker, Market, OddsSnapshot
from src.services.bet_service import compute_pnl, resolve_result
from src.services.devig import devig
from src.services.modeling.dixon_coles import (
    DixonColesModel,
    NotEnoughDataError,
    TrainingMatch,
    fit_dixon_coles,
    match_result_probs,
)
from src.services.staking import edge as edge_of
from src.services.staking import kelly_fraction, suggested_stake

logger = logging.getLogger(__name__)

_DETAIL_BET_CAP = 3000


# --- pure metric helpers (hand-tested) ---


def max_drawdown(equity: list[float]) -> float:
    """Largest peak-to-trough drop of the equity sequence (>= 0)."""
    peak = float("-inf")
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        worst = max(worst, peak - value)
    return worst


def sharpe_per_bet(pnls: list[float]) -> float | None:
    """Mean/std of per-bet P&L, scaled by sqrt(n). None if undefined."""
    n = len(pnls)
    if n < 2:
        return None
    mean = sum(pnls) / n
    variance = sum((p - mean) ** 2 for p in pnls) / (n - 1)
    if variance <= 0:
        return None
    return mean / math.sqrt(variance) * math.sqrt(n)


@dataclass(frozen=True)
class BacktestParams:
    name: str
    date_from: date
    date_to: date
    min_edge: float
    kelly_multiplier: float
    max_stake_pct: float
    devig_method: str
    initial_bankroll: float
    refit_days: int
    xi: float
    training_window_days: int

    def as_json(self) -> dict[str, Any]:
        return {
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
            "min_edge": self.min_edge,
            "kelly_multiplier": self.kelly_multiplier,
            "max_stake_pct": self.max_stake_pct,
            "devig_method": self.devig_method,
            "initial_bankroll": self.initial_bankroll,
            "refit_days": self.refit_days,
            "xi": self.xi,
            "training_window_days": self.training_window_days,
            "markets": ["1X2"],
        }


@dataclass
class _SimBet:
    kickoff: str
    match_id: int
    selection: str
    model_prob: float
    fair_prob: float
    odds: float
    edge: float
    stake: float
    result: str
    pnl: float
    clv: float
    bankroll_after: float

    def as_json(self) -> dict[str, Any]:
        return self.__dict__


@dataclass
class _State:
    bankroll: float
    total_staked: float = 0.0
    bets: list[_SimBet] = field(default_factory=list)
    equity: list[float] = field(default_factory=list)


class BacktestService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_run(self, params: BacktestParams, model_version: str) -> BacktestRun:
        run = BacktestRun(
            name=params.name,
            status=BacktestStatus.RUNNING,
            model_version=model_version,
            params=params.as_json(),
            date_from=params.date_from,
            date_to=params.date_to,
        )
        self._session.add(run)
        self._session.commit()
        return run

    def execute(self, run_id: int, params: BacktestParams) -> BacktestRun:
        run = self._session.get(BacktestRun, run_id)
        assert run is not None
        try:
            self._execute(run, params)
        except Exception as exc:
            logger.exception("backtest.failed", extra={"run_id": run_id})
            run.status = BacktestStatus.FAILED
            run.detail = {"error": str(exc)}
            self._session.commit()
        return run

    def _execute(self, run: BacktestRun, params: BacktestParams) -> None:
        eval_matches = self._eval_matches(params)
        training_pool = self._training_pool()
        closing_by_match = self._closing_1x2(eval_matches)

        state = _State(bankroll=params.initial_bankroll)
        state.equity.append(state.bankroll)
        model: DixonColesModel | None = None
        next_refit: datetime | None = None
        skipped_no_odds = 0
        skipped_unknown_teams = 0

        for match in eval_matches:
            trio = closing_by_match.get(match.id)
            if trio is None:
                skipped_no_odds += 1
                continue
            kickoff = _as_utc(match.kickoff_utc)
            if model is None or next_refit is None or kickoff >= next_refit:
                try:
                    model = fit_dixon_coles(
                        _window(training_pool, kickoff, params.training_window_days),
                        cutoff=kickoff,
                        xi=params.xi,
                        warm_start=model,
                    )
                except NotEnoughDataError:
                    model = None
                next_refit = kickoff + timedelta(days=params.refit_days)
            if model is None or not (
                model.knows(match.home_team_id) and model.knows(match.away_team_id)
            ):
                skipped_unknown_teams += 1
                continue
            self._bet_match(match, trio, model, params, state)

        self._finalize(run, params, state, skipped_no_odds, skipped_unknown_teams)

    def _bet_match(
        self,
        match: Match,
        trio: dict[str, Decimal],
        model: DixonColesModel,
        params: BacktestParams,
        state: _State,
    ) -> None:
        matrix = model.score_matrix(match.home_team_id, match.away_team_id)
        model_probs = dict(
            zip(("HOME", "DRAW", "AWAY"), match_result_probs(matrix), strict=True)
        )
        odds = [float(trio["HOME"]), float(trio["DRAW"]), float(trio["AWAY"])]
        try:
            fair = dict(
                zip(("HOME", "DRAW", "AWAY"), devig(odds, params.devig_method), strict=True)
            )
        except ValueError:
            return
        assert match.home_goals is not None and match.away_goals is not None

        for selection in ("HOME", "DRAW", "AWAY"):
            price = float(trio[selection])
            p_model = model_probs[selection]
            edge_value = edge_of(p_model, price)
            fraction = kelly_fraction(p_model, price)
            if edge_value <= params.min_edge or fraction <= 0.0:
                continue
            stake = suggested_stake(
                state.bankroll,
                p_model,
                price,
                kelly_multiplier=params.kelly_multiplier,
                max_stake_pct=params.max_stake_pct,
            )
            if stake <= 0 or stake > state.bankroll:
                continue
            result = resolve_result("1X2", selection, None, match.home_goals, match.away_goals)
            pnl = float(compute_pnl(result, Decimal(f"{stake:.2f}"), Decimal(f"{price:.3f}")))
            state.bankroll += pnl
            state.total_staked += stake
            state.equity.append(state.bankroll)
            state.bets.append(
                _SimBet(
                    kickoff=_as_utc(match.kickoff_utc).isoformat(),
                    match_id=match.id,
                    selection=selection,
                    model_prob=round(p_model, 6),
                    fair_prob=round(fair[selection], 6),
                    odds=price,
                    edge=round(edge_value, 6),
                    stake=round(stake, 2),
                    result=result,
                    pnl=round(pnl, 2),
                    # taken AT closing -> structurally 0 on this corpus
                    clv=0.0,
                    bankroll_after=round(state.bankroll, 2),
                )
            )

    def _finalize(
        self,
        run: BacktestRun,
        params: BacktestParams,
        state: _State,
        skipped_no_odds: int,
        skipped_unknown_teams: int,
    ) -> None:
        pnls = [b.pnl for b in state.bets]
        clvs = [b.clv for b in state.bets]
        total_pnl = sum(pnls)
        run.n_bets = len(state.bets)
        run.avg_clv = Decimal(f"{sum(clvs) / len(clvs):.6f}") if clvs else None
        run.pct_positive_clv = (
            Decimal(f"{sum(1 for c in clvs if c > 0) / len(clvs):.6f}") if clvs else None
        )
        run.roi = (
            Decimal(f"{total_pnl / state.total_staked:.6f}") if state.total_staked > 0 else None
        )
        run.total_pnl = Decimal(f"{total_pnl:.2f}")
        run.max_drawdown = Decimal(f"{max_drawdown(state.equity):.2f}")
        sharpe = sharpe_per_bet(pnls)
        run.sharpe = Decimal(f"{sharpe:.4f}") if sharpe is not None else None
        run.status = BacktestStatus.FINISHED
        run.detail = {
            "final_bankroll": round(state.bankroll, 2),
            "total_staked": round(state.total_staked, 2),
            "skipped_no_odds": skipped_no_odds,
            "skipped_unknown_teams": skipped_unknown_teams,
            "clv_note": (
                "bets simulated AT the closing price (historical corpus has "
                "closing odds only) -> CLV structurally 0; see ADR-0006"
            ),
            "bets": [b.as_json() for b in state.bets[:_DETAIL_BET_CAP]],
        }
        self._session.commit()
        logger.info(
            "backtest.finished",
            extra={
                "run_id": run.id,
                "n_bets": run.n_bets,
                "roi": str(run.roi),
                "total_pnl": str(run.total_pnl),
                "max_drawdown": str(run.max_drawdown),
            },
        )

    def _eval_matches(self, params: BacktestParams) -> list[Match]:
        start = datetime.combine(params.date_from, time.min, tzinfo=UTC)
        end = datetime.combine(params.date_to, time.max, tzinfo=UTC)
        return list(
            self._session.scalars(
                select(Match)
                .where(
                    Match.status == MatchStatus.FINISHED,
                    Match.home_goals.is_not(None),
                    Match.away_goals.is_not(None),
                    Match.kickoff_utc >= start,
                    Match.kickoff_utc <= end,
                )
                .order_by(Match.kickoff_utc)
            )
        )

    def _training_pool(self) -> list[TrainingMatch]:
        pool = []
        for m in self._session.scalars(
            select(Match).where(
                Match.status == MatchStatus.FINISHED,
                Match.home_goals.is_not(None),
                Match.away_goals.is_not(None),
            )
        ):
            if m.home_goals is None or m.away_goals is None:
                continue
            pool.append(
                TrainingMatch(
                    home_team_id=m.home_team_id,
                    away_team_id=m.away_team_id,
                    home_goals=m.home_goals,
                    away_goals=m.away_goals,
                    kickoff_utc=m.kickoff_utc,
                )
            )
        return pool

    def _closing_1x2(self, matches: list[Match]) -> dict[int, dict[str, Decimal]]:
        """Sharp closing 1X2 trio per match id (complete trios only)."""
        market = self._session.scalar(select(Market).where(Market.code == "1X2"))
        if market is None:
            return {}
        sharp_ids = set(
            self._session.scalars(select(Bookmaker.id).where(Bookmaker.is_sharp.is_(True)))
        )
        match_ids = [m.id for m in matches]
        trios: dict[int, dict[str, Decimal]] = {}
        for snap in self._session.scalars(
            select(OddsSnapshot).where(
                OddsSnapshot.match_id.in_(match_ids),
                OddsSnapshot.market_id == market.id,
                OddsSnapshot.is_closing.is_(True),
                OddsSnapshot.bookmaker_id.in_(sharp_ids),
            )
        ):
            trios.setdefault(snap.match_id, {})[snap.selection] = Decimal(snap.price_decimal)
        return {
            match_id: trio
            for match_id, trio in trios.items()
            if {"HOME", "DRAW", "AWAY"} <= set(trio)
        }


def _window(
    pool: list[TrainingMatch], cutoff: datetime, window_days: int
) -> list[TrainingMatch]:
    start = cutoff - timedelta(days=window_days)
    return [m for m in pool if start <= _as_utc(m.kickoff_utc) < cutoff]


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
