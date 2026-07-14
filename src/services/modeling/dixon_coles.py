"""Dixon-Coles goal model (spec §5.2) — the canonical football baseline.

Each team gets an attack and a defense strength; a global home advantage
and the Dixon-Coles low-score correction (rho) complete the model:

    lambda_home = exp(home_adv + attack_home + defense_away)
    lambda_away = exp(attack_away + defense_home)

Scores follow independent Poissons adjusted by the DC tau correction on the
{0,1}x{0,1} corner (pure Poisson underestimates 0-0/1-0/0-1/1-1). Fitting
maximizes the time-decayed log-likelihood (recent matches weigh more,
weight = exp(-xi * days_before_cutoff)) with a small L2 penalty on the
strengths so teams with little history do not blow up.

The `cutoff` argument is the anti-leakage guard: matches at or after it are
excluded from the fit, so backtests can honestly refit "as of" any date.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

logger = logging.getLogger(__name__)

MODEL_VERSION = "dixoncoles_v1"

_RHO_BOUNDS = (-0.2, 0.2)
_L2_PENALTY = 1e-3
_MIN_MATCHES = 30


@dataclass(frozen=True)
class TrainingMatch:
    home_team_id: int
    away_team_id: int
    home_goals: int
    away_goals: int
    kickoff_utc: datetime


class NotEnoughDataError(ValueError):
    """Raised when the training window has too few matches to fit."""


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _tau_matrix_corner(lam: float, mu: float, rho: float) -> np.ndarray:
    """DC correction factors for scores (0,0), (0,1), (1,0), (1,1)."""
    return np.array(
        [
            [1.0 - lam * mu * rho, 1.0 + lam * rho],
            [1.0 + mu * rho, 1.0 - rho],
        ]
    )


@dataclass
class DixonColesModel:
    attack: dict[int, float]
    defense: dict[int, float]
    home_advantage: float
    rho: float
    xi: float
    cutoff: datetime
    n_matches: int
    converged: bool = True
    version: str = field(default=MODEL_VERSION)

    def knows(self, team_id: int) -> bool:
        return team_id in self.attack

    def expected_goals(self, home_team_id: int, away_team_id: int) -> tuple[float, float]:
        lam = float(
            np.exp(self.home_advantage + self.attack[home_team_id] + self.defense[away_team_id])
        )
        mu = float(np.exp(self.attack[away_team_id] + self.defense[home_team_id]))
        return lam, mu

    def score_matrix(
        self, home_team_id: int, away_team_id: int, max_goals: int = 10
    ) -> np.ndarray:
        """P[x, y] = probability of the score home x - y away, renormalized
        over the truncated (max_goals+1)^2 grid."""
        lam, mu = self.expected_goals(home_team_id, away_team_id)
        goals = np.arange(max_goals + 1)
        home_pmf = np.exp(goals * np.log(lam) - lam - gammaln(goals + 1))
        away_pmf = np.exp(goals * np.log(mu) - mu - gammaln(goals + 1))
        matrix = np.asarray(np.outer(home_pmf, away_pmf), dtype=float)
        # clamp: tau(0,0)=1-lam*mu*rho can go negative for high-scoring
        # pairings at the rho bound; a probability may never be < 0
        matrix[:2, :2] *= np.maximum(_tau_matrix_corner(lam, mu, self.rho), 0.0)
        return np.asarray(matrix / matrix.sum())


def match_result_probs(matrix: np.ndarray) -> tuple[float, float, float]:
    """(home win, draw, away win) from a score matrix."""
    home = float(np.tril(matrix, -1).sum())
    draw = float(np.trace(matrix))
    away = float(np.triu(matrix, 1).sum())
    return home, draw, away


def over_under_probs(matrix: np.ndarray, line: float) -> tuple[float, float, float]:
    """(over wins, under wins, push) for a total-goals line. Integer lines
    (e.g. 2.0) leave push mass on P(total == line); half lines have none."""
    size = matrix.shape[0]
    totals = np.add.outer(np.arange(size), np.arange(size))
    over = float(matrix[totals > line].sum())
    under = float(matrix[totals < line].sum())
    push = float(matrix[totals == line].sum())
    return over, under, push


def btts_probs(matrix: np.ndarray) -> tuple[float, float]:
    """(both teams score, not both) from a score matrix."""
    yes = float(matrix[1:, 1:].sum())
    return yes, 1.0 - yes


def fit_dixon_coles(
    matches: list[TrainingMatch],
    *,
    cutoff: datetime,
    xi: float,
    warm_start: DixonColesModel | None = None,
) -> DixonColesModel:
    cutoff = _as_utc(cutoff)
    usable = [m for m in matches if _as_utc(m.kickoff_utc) < cutoff]
    if len(usable) < _MIN_MATCHES:
        raise NotEnoughDataError(
            f"need at least {_MIN_MATCHES} finished matches before "
            f"{cutoff.isoformat()}, got {len(usable)}"
        )

    team_ids = sorted({m.home_team_id for m in usable} | {m.away_team_id for m in usable})
    index = {team_id: i for i, team_id in enumerate(team_ids)}
    n = len(team_ids)
    # 2n+1 free parameters need enough observations per team, not just a
    # global floor — otherwise single-appearance teams fit pure noise
    required = max(_MIN_MATCHES, 3 * n)
    if len(usable) < required:
        raise NotEnoughDataError(
            f"need at least {required} matches for {n} teams "
            f"(2n+1 parameters), got {len(usable)}"
        )

    home_idx = np.array([index[m.home_team_id] for m in usable])
    away_idx = np.array([index[m.away_team_id] for m in usable])
    home_goals = np.array([m.home_goals for m in usable], dtype=float)
    away_goals = np.array([m.away_goals for m in usable], dtype=float)
    days_ago = np.array(
        [(cutoff - _as_utc(m.kickoff_utc)).total_seconds() / 86400.0 for m in usable]
    )
    weights = np.exp(-xi * days_ago)

    log_fact_home = gammaln(home_goals + 1)
    log_fact_away = gammaln(away_goals + 1)
    is_corner = (home_goals <= 1) & (away_goals <= 1)

    # params: attack[0..n-2] (last attack = -sum, identifiability),
    #         defense[0..n-1], home_adv, rho
    def unpack(params: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
        attack = np.append(params[: n - 1], -params[: n - 1].sum())
        defense = params[n - 1 : 2 * n - 1]
        return attack, defense, params[-2], params[-1]

    def negative_log_likelihood(params: np.ndarray) -> float:
        attack, defense, home_adv, rho = unpack(params)
        lam = np.exp(home_adv + attack[home_idx] + defense[away_idx])
        mu = np.exp(attack[away_idx] + defense[home_idx])
        log_pois = (
            home_goals * np.log(lam)
            - lam
            - log_fact_home
            + away_goals * np.log(mu)
            - mu
            - log_fact_away
        )
        tau = np.ones_like(lam)
        corner_h = home_goals[is_corner]
        corner_a = away_goals[is_corner]
        corner_lam = lam[is_corner]
        corner_mu = mu[is_corner]
        tau_corner = np.select(
            [
                (corner_h == 0) & (corner_a == 0),
                (corner_h == 0) & (corner_a == 1),
                (corner_h == 1) & (corner_a == 0),
            ],
            [
                1.0 - corner_lam * corner_mu * rho,
                1.0 + corner_lam * rho,
                1.0 + corner_mu * rho,
            ],
            default=1.0 - rho,
        )
        tau[is_corner] = np.maximum(tau_corner, 1e-10)
        log_likelihood = float((weights * (np.log(tau) + log_pois)).sum())
        penalty = _L2_PENALTY * float((attack**2).sum() + (defense**2).sum())
        value = -log_likelihood + penalty
        # wild line-search steps can overflow exp() into inf/nan; a large
        # finite value steers L-BFGS-B away instead of aborting the fit
        return value if np.isfinite(value) else 1e12

    initial = np.zeros(2 * n + 1)
    initial[-2] = 0.25  # typical home advantage
    if warm_start is not None:
        # sequential refits (backtest loop) converge in far fewer iterations
        # when seeded from the previous window's parameters
        attack0 = np.array([warm_start.attack.get(t, 0.0) for t in team_ids])
        attack0 -= attack0.mean()  # respect the sum-zero constraint
        initial[: n - 1] = attack0[: n - 1]
        initial[n - 1 : 2 * n - 1] = [warm_start.defense.get(t, 0.0) for t in team_ids]
        initial[-2] = warm_start.home_advantage
        initial[-1] = min(max(warm_start.rho, _RHO_BOUNDS[0]), _RHO_BOUNDS[1])
    bounds: list[tuple[float | None, float | None]] = [(None, None)] * (2 * n - 1)
    bounds += [(None, None), _RHO_BOUNDS]

    result = minimize(
        negative_log_likelihood,
        initial,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxfun": 200_000, "maxiter": 1_000},
    )
    if not result.success:
        # NB: 'message' is reserved on LogRecord — never use it as an extra key
        logger.warning("dixon_coles.fit_not_converged", extra={"detail": str(result.message)})

    attack, defense, home_adv, rho = unpack(result.x)
    model = DixonColesModel(
        attack={team_id: float(attack[i]) for team_id, i in index.items()},
        defense={team_id: float(defense[i]) for team_id, i in index.items()},
        home_advantage=float(home_adv),
        rho=float(rho),
        xi=xi,
        cutoff=cutoff,
        n_matches=len(usable),
        converged=bool(result.success),
    )
    logger.info(
        "dixon_coles.fitted",
        extra={
            "n_matches": len(usable),
            "n_teams": n,
            "home_advantage": round(model.home_advantage, 4),
            "rho": round(model.rho, 4),
            "converged": bool(result.success),
        },
    )
    return model
