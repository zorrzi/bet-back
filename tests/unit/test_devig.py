"""De-vig math validated against hand-calculated cases (spec §11.3: no
financial formula ships without one)."""

import pytest

from src.services.devig import (
    devig,
    devig_multiplicative,
    devig_power,
    devig_shin,
    implied_probs,
    overround,
)

# Hand-calculated: odds 1.80/3.60/3.60
#   raw = 1/1.8, 1/3.6, 1/3.6 = 0.55556, 0.27778, 0.27778 -> booksum = 1.11111
#   multiplicative fair = raw / booksum = 0.50, 0.25, 0.25
HAND_ODDS = [1.80, 3.60, 3.60]
HAND_FAIR = [0.50, 0.25, 0.25]


def test_implied_probs_hand_case() -> None:
    probs = implied_probs(HAND_ODDS)
    assert probs[0] == pytest.approx(0.555556, abs=1e-6)
    assert probs[1] == pytest.approx(0.277778, abs=1e-6)


def test_overround_hand_case() -> None:
    # booksum 1.11111 -> margin 11.111%
    assert overround(HAND_ODDS) == pytest.approx(0.111111, abs=1e-6)


def test_multiplicative_hand_case() -> None:
    fair = devig_multiplicative(HAND_ODDS)
    assert fair == pytest.approx(HAND_FAIR, abs=1e-9)
    assert sum(fair) == pytest.approx(1.0)


def test_multiplicative_two_way_even_odds() -> None:
    # 1.90/1.90: symmetric coin flip once the margin is removed
    assert devig_multiplicative([1.90, 1.90]) == pytest.approx([0.5, 0.5])


def test_no_vig_odds_are_identity_for_all_methods() -> None:
    # 2.0/4.0/4.0 sums exactly to 1: nothing to remove
    odds = [2.0, 4.0, 4.0]
    for method_fair in (devig_multiplicative(odds), devig_power(odds), devig_shin(odds)):
        assert method_fair == pytest.approx([0.5, 0.25, 0.25], abs=1e-6)


@pytest.mark.parametrize("method_devig", [devig_power, devig_shin])
def test_bias_correcting_methods_sum_to_one(method_devig) -> None:  # type: ignore[no-untyped-def]
    fair = method_devig([1.30, 5.50, 11.0])
    assert sum(fair) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("method_devig", [devig_power, devig_shin])
def test_bias_correcting_methods_shift_margin_onto_longshots(method_devig) -> None:  # type: ignore[no-untyped-def]
    """Shin/power correct the favourite-longshot bias: relative to the
    multiplicative method they give the favourite MORE probability and the
    longshot LESS."""
    odds = [1.30, 5.50, 11.0]
    mult = devig_multiplicative(odds)
    fair = method_devig(odds)
    assert fair[0] > mult[0]  # favourite
    assert fair[-1] < mult[-1]  # longshot


def test_symmetric_odds_stay_symmetric_for_all_methods() -> None:
    for fair in (
        devig_multiplicative([1.90, 1.90]),
        devig_power([1.90, 1.90]),
        devig_shin([1.90, 1.90]),
    ):
        assert fair[0] == pytest.approx(fair[1], abs=1e-9)
        assert sum(fair) == pytest.approx(1.0, abs=1e-9)


def test_devig_dispatch_and_unknown_method() -> None:
    assert devig(HAND_ODDS, "multiplicative") == pytest.approx(HAND_FAIR, abs=1e-9)
    with pytest.raises(ValueError, match="unknown de-vig method"):
        devig(HAND_ODDS, "nope")


def test_invalid_odds_raise() -> None:
    with pytest.raises(ValueError, match="must be > 1"):
        implied_probs([2.0, 1.0])


@pytest.mark.parametrize("method_devig", [devig_multiplicative, devig_power, devig_shin])
def test_incomplete_market_is_refused(method_devig) -> None:  # type: ignore[no-untyped-def]
    """Two selections of a 3-way market (booksum < 1) must raise, never
    silently fabricate a 'fair' distribution."""
    with pytest.raises(ValueError, match="incomplete market"):
        method_devig([2.5, 4.0])
