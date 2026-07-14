"""Dixon-Coles model: hand-calculated market derivations, directional
effect of the low-score correction, synthetic parameter recovery and the
anti-leakage cutoff (spec §11.3)."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from src.services.modeling.dixon_coles import (
    DixonColesModel,
    NotEnoughDataError,
    TrainingMatch,
    btts_probs,
    fit_dixon_coles,
    match_result_probs,
    over_under_probs,
)

CUTOFF = datetime(2026, 7, 1, tzinfo=UTC)

# Hand-built 2x2 "score matrix" (only scores 0 and 1), rows = home goals:
#   P(0-0)=0.2  P(0-1)=0.1
#   P(1-0)=0.3  P(1-1)=0.4
HAND_MATRIX = np.array([[0.2, 0.1], [0.3, 0.4]])


def test_match_result_probs_hand_case() -> None:
    home, draw, away = match_result_probs(HAND_MATRIX)
    assert home == pytest.approx(0.3)  # only 1-0
    assert draw == pytest.approx(0.6)  # 0-0 + 1-1
    assert away == pytest.approx(0.1)  # only 0-1
    assert home + draw + away == pytest.approx(1.0)


def test_over_under_probs_hand_cases() -> None:
    # totals: 0-0 -> 0, 0-1/1-0 -> 1, 1-1 -> 2
    over, under, push = over_under_probs(HAND_MATRIX, 0.5)
    assert (over, under, push) == pytest.approx((0.8, 0.2, 0.0))
    # integer line 1.0: totals == 1 are a push
    over, under, push = over_under_probs(HAND_MATRIX, 1.0)
    assert (over, under, push) == pytest.approx((0.4, 0.2, 0.4))


def test_btts_probs_hand_case() -> None:
    yes, no = btts_probs(HAND_MATRIX)
    assert yes == pytest.approx(0.4)  # only 1-1
    assert no == pytest.approx(0.6)


def _model(rho: float = 0.0) -> DixonColesModel:
    return DixonColesModel(
        attack={1: 0.3, 2: -0.3},
        defense={1: -0.2, 2: 0.2},
        home_advantage=0.25,
        rho=rho,
        xi=0.0,
        cutoff=CUTOFF,
        n_matches=0,
    )


def test_expected_goals_formula_hand_case() -> None:
    """lambda_home = exp(home_adv + attack_home + defense_away)."""
    lam, mu = _model().expected_goals(1, 2)
    assert lam == pytest.approx(np.exp(0.25 + 0.3 + 0.2))  # ~2.117
    assert mu == pytest.approx(np.exp(-0.3 + -0.2))  # ~0.607


def test_score_matrix_is_a_distribution() -> None:
    matrix = _model(rho=-0.08).score_matrix(1, 2)
    assert matrix.sum() == pytest.approx(1.0)
    assert (matrix >= 0).all()


def test_negative_rho_boosts_low_draws_and_dampens_low_wins() -> None:
    """DC correction with rho < 0 (the typical fit): more 0-0/1-1, fewer
    1-0/0-1 than independent Poisson."""
    base = _model(rho=0.0).score_matrix(1, 2)
    corrected = _model(rho=-0.1).score_matrix(1, 2)
    assert corrected[0, 0] > base[0, 0]
    assert corrected[1, 1] > base[1, 1]
    assert corrected[1, 0] < base[1, 0]
    assert corrected[0, 1] < base[0, 1]


def _synthetic_matches(
    attack: dict[int, float],
    defense: dict[int, float],
    home_adv: float,
    rounds: int,
    seed: int = 42,
) -> list[TrainingMatch]:
    rng = np.random.default_rng(seed)
    teams = sorted(attack)
    matches = []
    day = 0
    for _ in range(rounds):
        for home in teams:
            for away in teams:
                if home == away:
                    continue
                lam = np.exp(home_adv + attack[home] + defense[away])
                mu = np.exp(attack[away] + defense[home])
                matches.append(
                    TrainingMatch(
                        home_team_id=home,
                        away_team_id=away,
                        home_goals=int(rng.poisson(lam)),
                        away_goals=int(rng.poisson(mu)),
                        kickoff_utc=CUTOFF - timedelta(days=400 - day % 365),
                    )
                )
                day += 1
    return matches


def test_fit_recovers_synthetic_parameters() -> None:
    true_attack = {1: 0.4, 2: 0.1, 3: -0.1, 4: -0.4, 5: 0.2, 6: -0.2}
    true_defense = {1: -0.3, 2: 0.0, 3: 0.1, 4: 0.3, 5: -0.1, 6: 0.0}
    matches = _synthetic_matches(true_attack, true_defense, home_adv=0.3, rounds=20)

    model = fit_dixon_coles(matches, cutoff=CUTOFF, xi=0.0)

    assert model.home_advantage == pytest.approx(0.3, abs=0.08)
    # attack ordering must be preserved and values close (identifiability
    # constraint means only differences are meaningful; compare centered)
    fitted = np.array([model.attack[t] for t in sorted(true_attack)])
    truth = np.array([true_attack[t] for t in sorted(true_attack)])
    # 600 synthetic matches leave real MLE noise; what matters is that the
    # fitted strengths track the true ones closely, not exact recovery
    assert np.corrcoef(fitted, truth)[0, 1] > 0.9
    assert np.abs((fitted - fitted.mean()) - (truth - truth.mean())).max() < 0.2
    # independent Poisson data has no low-score excess: rho stays near 0
    assert abs(model.rho) < 0.06


def test_cutoff_excludes_future_matches() -> None:
    matches = _synthetic_matches({1: 0.2, 2: -0.2}, {1: 0.0, 2: 0.0}, 0.25, rounds=30)
    early_cutoff = min(m.kickoff_utc for m in matches)  # nothing strictly before
    with pytest.raises(NotEnoughDataError):
        fit_dixon_coles(matches, cutoff=early_cutoff, xi=0.0)


def test_fit_requires_minimum_history() -> None:
    matches = _synthetic_matches({1: 0.1, 2: -0.1}, {1: 0.0, 2: 0.0}, 0.25, rounds=1)
    with pytest.raises(NotEnoughDataError):
        fit_dixon_coles(matches, cutoff=CUTOFF, xi=0.0)
